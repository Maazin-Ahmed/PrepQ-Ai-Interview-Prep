import asyncio
import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from agents import prepq_agent, retrieval
from db import supabase
from middleware.auth import require_auth
from middleware.security import _detect_violation
from models.schemas import ChatRequest

logger = logging.getLogger("prepq.router.chat")

router = APIRouter()


async def _save_messages_background(
    session_id: str,
    user_message: str,
    assistant_response: str,
) -> None:
    """Fire-and-forget DB writes — don't block the stream."""
    try:
        await supabase.save_message(session_id, "user", user_message)
        await supabase.save_message(session_id, "assistant", assistant_response)
    except Exception as exc:
        logger.warning(f"Failed to save messages for session {session_id}: {exc}")


async def _stream_generator(
    user_message: str,
    session_id: str,
    user_id: str,
    history: list[dict],
    context: Optional[str],
):
    """
    Wraps the agent stream and captures the full response for DB persistence.
    Yields SSE chunks, then saves the exchange in the background.
    """
    # Yield session_id as first metadata event
    yield f'data: {json.dumps({"type": "metadata", "session_id": session_id})}\n\n'

    full_response = []

    async for chunk in prepq_agent.stream_response(user_message, history, context):
        yield chunk
        # Parse chunk to accumulate text
        if '"type": "chunk"' in chunk:
            try:
                data = json.loads(chunk.replace("data: ", "").strip())
                if data.get("type") == "chunk":
                    full_response.append(data.get("text", ""))
            except Exception:
                pass

    # Fire-and-forget — don't await this so the stream closes cleanly
    asyncio.create_task(
        _save_messages_background(
            session_id,
            user_message,
            "".join(full_response),
        )
    )


@router.post("")
async def chat(
    body: ChatRequest,
    request: Request,
    user_id: str = Depends(require_auth),
):
    """
    Main streaming chat endpoint.
    - Creates a new session if session_id not provided
    - Fetches conversation history for context window
    - Fetches company intel on first message (if session has company/role)
    - Streams Groq response as SSE
    """
    # Security Scan
    is_violation, _ = _detect_violation(body.message)
    if is_violation:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Invalid input detected.")

    # Ensure user exists in DB (graceful — won't crash if Supabase is down)
    email = getattr(request.state, "user_email", "")
    await supabase.upsert_user(user_id, email)

    # Session management
    session_id = body.session_id
    session: Optional[dict] = None

    if not session_id:
        session = await supabase.create_session(user_id)
        session_id = session["id"]
    else:
        session = await supabase.get_session(session_id)
        if not session:
            # In offline mode, create a new session with the provided ID
            session = await supabase.create_session(user_id)
            session_id = session["id"]
        elif session.get("user_id") != user_id:
            from fastapi import HTTPException
            raise HTTPException(status_code=403, detail="Session not found or access denied.")

    # Fetch conversation history (last 20 messages for context window)
    history = await supabase.get_messages(session_id, limit=20)

    # Fetch company intel if this session has company/role set
    context: Optional[str] = None
    company = session.get("company", "") if session else ""
    role = session.get("role", "") if session else ""

    if company and role and len(history) <= 2:
        # Only fetch on early messages to avoid redundant calls
        try:
            context = await retrieval.fetch_company_intel(company, role)
        except Exception as exc:
            logger.warning(f"Company intel fetch failed: {exc}")

    # Stream the response
    return StreamingResponse(
        _stream_generator(body.message, session_id, user_id, history, context),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "X-Session-ID": session_id,
        },
    )


@router.get("/session/{session_id}")
async def get_session(
    session_id: str,
    user_id: str = Depends(require_auth),
):
    """Retrieve session details and message history."""
    session = await supabase.get_session(session_id)
    if not session:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Session not found.")

    messages = await supabase.get_messages(session_id, limit=50)
    return {"session": session, "messages": messages}


@router.get("/sessions")
async def list_sessions(
    user_id: str = Depends(require_auth),
):
    """List all sessions for the authenticated user."""
    sessions = await supabase.get_user_sessions(user_id, limit=10)
    return {"sessions": sessions}
