import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from agents import prepq_agent, retrieval
from db import supabase
from middleware.auth import require_auth
from middleware.security import _detect_violation
from models.schemas import ChatRequest

logger = logging.getLogger("prepq.router.chat")

router = APIRouter()

# ─── In-memory buffer for messages not yet flushed to DB ───────────────────
# Maps session_id → list of {role, content} dicts saved since last DB write.
# This guarantees that even with the async fire-and-forget save, a follow-up
# request in the same process can still access the latest messages.
_pending_messages: dict[str, list[dict]] = {}


async def _save_messages_to_db(
    session_id: str,
    user_message: str,
    assistant_response: str,
) -> None:
    """Persist both messages to the database."""
    try:
        await supabase.save_message(session_id, "user", user_message)
        await supabase.save_message(session_id, "assistant", assistant_response)
        logger.debug(
            f"[memory] Saved exchange to DB | session={session_id[:8]}… "
            f"| user={len(user_message)} chars | assistant={len(assistant_response)} chars"
        )
    except Exception as exc:
        logger.warning(f"Failed to save messages for session {session_id}: {exc}")
    finally:
        # Clear the in-memory pending buffer for this session now that DB is written
        _pending_messages.pop(session_id, None)


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

    KEY FIX: We immediately stage both messages in _pending_messages so that
    any follow-up request arriving before the DB write completes can still
    see the full history via get_messages (which now merges DB + pending).
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

    assistant_text = "".join(full_response)

    # Stage in memory immediately so the next request sees these messages
    # even if the DB write hasn't completed yet.
    now = datetime.now(timezone.utc).isoformat()
    _pending_messages[session_id] = [
        {"id": str(uuid4()), "session_id": session_id, "role": "user",
         "content": user_message, "created_at": now},
        {"id": str(uuid4()), "session_id": session_id, "role": "assistant",
         "content": assistant_text, "created_at": now},
    ]

    # Fire-and-forget DB write — doesn't block the stream
    asyncio.create_task(
        _save_messages_to_db(
            session_id,
            user_message,
            assistant_text,
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
    # Merge DB messages with any pending (not-yet-persisted) messages from
    # the previous exchange to eliminate the race condition.
    history_from_db = await supabase.get_messages(session_id, limit=40)
    pending = _pending_messages.get(session_id, [])

    if pending:
        # Filter out pending messages already present in DB (by role+content match)
        db_contents = {(m["role"], m["content"]) for m in history_from_db}
        new_pending = [p for p in pending if (p["role"], p["content"]) not in db_contents]
        history = (history_from_db + new_pending)[-20:]  # keep last 20, oldest-first
    else:
        history = history_from_db[-20:]

    logger.info(
        f"[memory] session={session_id[:8]}… | "
        f"db_msgs={len(history_from_db)} | pending_msgs={len(pending)} | "
        f"total_sent_to_llm={len(history) + 1}"  # +1 for current user message
    )

    # Fetch company intel if this session has company/role set
    context_parts: list[str] = []

    # 1. Onboarding context sent by the frontend (always available after onboarding)
    if body.onboarding_context and body.onboarding_context.strip():
        context_parts.append(
            "USER PROFILE (from onboarding — always remember this):\n"
            + body.onboarding_context.strip()
        )

    # 2. Live company intel (fetched on early messages only)
    company = session.get("company", "") if session else ""
    role = session.get("role", "") if session else ""

    if company and role and len(history) <= 2:
        try:
            intel = await retrieval.fetch_company_intel(company, role)
            if intel:
                context_parts.append(intel)
        except Exception as exc:
            logger.warning(f"Company intel fetch failed: {exc}")

    context: Optional[str] = "\n\n---\n\n".join(context_parts) if context_parts else None

    # Debug: log context and prompt size
    context_chars = len(context) if context else 0
    history_chars = sum(len(m.get("content", "")) for m in history)
    logger.info(
        f"[memory] context_chars={context_chars} | history_chars={history_chars} | "
        f"approx_prompt_tokens={(context_chars + history_chars + len(body.message)) // 4}"
    )

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
