import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from agents import prepq_agent, retrieval
from agents import onboarding_engine as ob
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

async def _stream_onboarding_question(question: str, session_id: str):
    """
    Stream a deterministic onboarding question as SSE without calling the LLM.
    Saves both the assistant question and (optionally) the user message to DB.
    """
    yield f'data: {json.dumps({"type": "metadata", "session_id": session_id})}\n\n'
    # Stream word-by-word for a natural feel
    for word in question.split(" "):
        yield f'data: {json.dumps({"type": "chunk", "text": word + " "})}\n\n'
    yield f'data: {json.dumps({"type": "done"})}\n\n'


@router.post("")
async def chat(
    body: ChatRequest,
    request: Request,
    user_id: str = Depends(require_auth),
):
    """
    Main streaming chat endpoint.

    Onboarding is handled deterministically — the LLM is NEVER asked to
    collect onboarding information. Instead:
      1. Load the structured onboarding state for this session.
      2. Run the extraction engine on the user message.
      3. Persist the updated state.
      4. If onboarding is still incomplete → stream the next question directly.
      5. If onboarding is complete → call the LLM with the profile injected.
    """
    # Security Scan
    is_violation, _ = _detect_violation(body.message)
    if is_violation:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Invalid input detected.")

    # Ensure user exists in DB (graceful — won't crash if Supabase is down)
    email = getattr(request.state, "user_email", "")
    await supabase.upsert_user(user_id, email)

    # ── Session management ───────────────────────────────────────────────────
    session_id = body.session_id
    session: Optional[dict] = None

    if not session_id:
        session = await supabase.create_session(user_id)
        session_id = session["id"]
    else:
        session = await supabase.get_session(session_id)
        if not session:
            session = await supabase.create_session(user_id)
            session_id = session["id"]
        elif session.get("user_id") != user_id:
            from fastapi import HTTPException
            raise HTTPException(status_code=403, detail="Session not found or access denied.")

    # ── Deterministic onboarding engine ─────────────────────────────────────
    # Check if the frontend already completed structured onboarding. If
    # onboarding_context is provided, the structured form was used and we
    # skip the conversational onboarding engine entirely.
    use_conversational_onboarding = (
        not body.onboarding_context or not body.onboarding_context.strip()
    )

    ob_state: dict = {}
    if use_conversational_onboarding:
        # Load current onboarding state for this session
        ob_state = await supabase.get_onboarding_state(session_id)

        # Extract any new fields from the user's message
        new_ob_state, extracted = ob.process_message(body.message, ob_state)

        # Always persist immediately (before any LLM call)
        if extracted:
            await supabase.save_onboarding_state(session_id, new_ob_state)
            ob_state = new_ob_state

        ob.log_state(
            session_id,
            ob_state,
            extracted,
            ob.next_missing_field(ob_state),
        )

        # Save the user message to history regardless of onboarding status
        # (so context is preserved even for the onboarding turns)
        asyncio.create_task(
            supabase.save_message(session_id, "user", body.message)
        )

        # If onboarding is not complete, return the next question deterministically
        if not ob.is_complete(ob_state):
            next_field = ob.next_missing_field(ob_state)
            question = ob.build_question(next_field)  # type: ignore[arg-type]

            logger.info(
                f"[onboarding] Asking next field={next_field} | session={session_id[:8]}…"
            )

            # Save the assistant question to history for continuity
            asyncio.create_task(
                supabase.save_message(session_id, "assistant", question)
            )

            # Also stage in pending buffer so follow-up sees it immediately
            now = datetime.now(timezone.utc).isoformat()
            _pending_messages[session_id] = [
                {"id": str(uuid4()), "session_id": session_id, "role": "user",
                 "content": body.message, "created_at": now},
                {"id": str(uuid4()), "session_id": session_id, "role": "assistant",
                 "content": question, "created_at": now},
            ]

            return StreamingResponse(
                _stream_onboarding_question(question, session_id),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "X-Accel-Buffering": "no",
                    "X-Session-ID": session_id,
                },
            )

    # ── Onboarding complete — proceed to LLM ────────────────────────────────

    # Fetch conversation history (last 20 messages for context window)
    history_from_db = await supabase.get_messages(session_id, limit=40)
    pending = _pending_messages.get(session_id, [])

    if pending:
        db_contents = {(m["role"], m["content"]) for m in history_from_db}
        new_pending = [p for p in pending if (p["role"], p["content"]) not in db_contents]
        history = (history_from_db + new_pending)[-20:]
    else:
        history = history_from_db[-20:]

    logger.info(
        f"[memory] session={session_id[:8]}… | "
        f"db_msgs={len(history_from_db)} | pending_msgs={len(pending)} | "
        f"total_sent_to_llm={len(history) + 1}"
    )

    # ── Build context ────────────────────────────────────────────────────────
    context_parts: list[str] = []

    # 1. Structured profile from the deterministic engine (if conversational flow)
    if use_conversational_onboarding and ob.is_complete(ob_state):
        profile_summary = ob.build_state_summary(ob_state)
        context_parts.append(profile_summary)

    # 2. Profile from frontend structured onboarding form
    if body.onboarding_context and body.onboarding_context.strip():
        context_parts.append(
            "USER PROFILE (from onboarding — always remember this):\n"
            + body.onboarding_context.strip()
        )

    # 3. Live company intel (fetched on early messages only)
    company = ob_state.get("company") or (session.get("company", "") if session else "")
    role = ob_state.get("role") or (session.get("role", "") if session else "")

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

    # Stream the LLM response
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
