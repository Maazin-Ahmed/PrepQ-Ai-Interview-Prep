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
from agents.conversation_engine import (
    Stage, Intent,
    detect_intent,
    next_stage,
    build_stage_instruction,
    extract_day_number,
    extract_topic_from_plan,
    is_duplicate_response,
    log_turn,
    make_empty_conv_state,
)
from db import supabase
from middleware.auth import require_auth
from middleware.security import _detect_violation
from models.schemas import ChatRequest

logger = logging.getLogger("prepq.router.chat")

router = APIRouter()

# ─── In-memory buffer for messages not yet flushed to DB ───────────────────
# Maps session_id → list of {role, content} dicts saved since last DB write.
# Eliminates the race condition where the next request arrives before the
# fire-and-forget DB write has completed.
_pending_messages: dict[str, list[dict]] = {}


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

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
            f"[memory] Saved to DB | session={session_id[:8]}… "
            f"| user={len(user_message)}c | assistant={len(assistant_response)}c"
        )
    except Exception as exc:
        logger.warning(f"Failed to save messages for session {session_id}: {exc}")
    finally:
        _pending_messages.pop(session_id, None)


async def _stream_generator(
    user_message: str,
    session_id: str,
    history: list[dict],
    context: Optional[str],
    conv_state: dict,
):
    """
    Calls the LLM, streams SSE chunks, and saves the exchange in the background.
    Also updates conv_state with the last_response_snippet after completion.
    """
    yield f'data: {json.dumps({"type": "metadata", "session_id": session_id})}\n\n'

    full_response: list[str] = []

    async for chunk in prepq_agent.stream_response(user_message, history, context):
        yield chunk
        if '"type": "chunk"' in chunk:
            try:
                data = json.loads(chunk.replace("data: ", "").strip())
                if data.get("type") == "chunk":
                    full_response.append(data.get("text", ""))
            except Exception:
                pass

    assistant_text = "".join(full_response)

    # Stage in memory immediately (race-condition fix)
    now = datetime.now(timezone.utc).isoformat()
    _pending_messages[session_id] = [
        {"id": str(uuid4()), "session_id": session_id, "role": "user",
         "content": user_message, "created_at": now},
        {"id": str(uuid4()), "session_id": session_id, "role": "assistant",
         "content": assistant_text, "created_at": now},
    ]

    # Update last_response_snippet for duplicate detection
    conv_state["last_response_snippet"] = assistant_text[:300]

    # Fire-and-forget DB writes
    asyncio.create_task(
        _save_messages_to_db(session_id, user_message, assistant_text)
    )
    asyncio.create_task(
        supabase.save_conv_state(session_id, conv_state)
    )


async def _stream_deterministic(text: str, session_id: str):
    """
    Stream a fixed text (onboarding question, etc.) as SSE without calling the LLM.
    """
    yield f'data: {json.dumps({"type": "metadata", "session_id": session_id})}\n\n'
    for word in text.split(" "):
        yield f'data: {json.dumps({"type": "chunk", "text": word + " "})}\n\n'
    yield f'data: {json.dumps({"type": "done"})}\n\n'


def _merge_history(db_msgs: list[dict], pending: list[dict]) -> list[dict]:
    """Merge DB messages + pending buffer, de-dupe, keep last 20."""
    if not pending:
        return db_msgs[-20:]
    db_set = {(m["role"], m["content"]) for m in db_msgs}
    new_pending = [p for p in pending if (p["role"], p["content"]) not in db_set]
    return (db_msgs + new_pending)[-20:]


# ─────────────────────────────────────────────────────────────────────────────
# Main endpoint
# ─────────────────────────────────────────────────────────────────────────────

@router.post("")
async def chat(
    body: ChatRequest,
    request: Request,
    user_id: str = Depends(require_auth),
):
    """
    Stateful streaming chat endpoint.

    Every request runs through:
      1. Security scan
      2. Session management
      3. Onboarding engine  (if profile not yet complete)
      4. Intent detection
      5. Stage transition
      6. State persistence
      7. Duplicate check
      8. Stage-specific LLM prompt assembly
      9. SSE stream
    """

    # ── 1. Security ─────────────────────────────────────────────────────────
    is_violation, _ = _detect_violation(body.message)
    if is_violation:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Invalid input detected.")

    email = getattr(request.state, "user_email", "")
    await supabase.upsert_user(user_id, email)

    # ── 2. Session management ────────────────────────────────────────────────
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

    # ── 3. Load both state objects in parallel ───────────────────────────────
    ob_state, conv_state = await asyncio.gather(
        supabase.get_onboarding_state(session_id),
        supabase.get_conv_state(session_id),
    )

    # ── 4. Onboarding gate ───────────────────────────────────────────────────
    # If the frontend sent a complete onboarding_context (structured form),
    # mark onboarding done immediately. Otherwise run the conversational engine.
    frontend_onboarding_done = bool(body.onboarding_context and body.onboarding_context.strip())

    if not frontend_onboarding_done:
        # Conversational onboarding path
        new_ob_state, extracted = ob.process_message(body.message, ob_state)

        if extracted:
            ob_state = new_ob_state
            await supabase.save_onboarding_state(session_id, ob_state)

        ob.log_state(session_id, ob_state, extracted, ob.next_missing_field(ob_state))

        if not ob.is_complete(ob_state):
            # Still collecting profile — return deterministic question, skip LLM
            next_field = ob.next_missing_field(ob_state)
            question = ob.build_question(next_field)  # type: ignore[arg-type]

            logger.info(
                f"[onboarding] field={next_field} | session={session_id[:8]}…"
            )

            now = datetime.now(timezone.utc).isoformat()
            _pending_messages[session_id] = [
                {"id": str(uuid4()), "session_id": session_id, "role": "user",
                 "content": body.message, "created_at": now},
                {"id": str(uuid4()), "session_id": session_id, "role": "assistant",
                 "content": question, "created_at": now},
            ]
            asyncio.create_task(supabase.save_message(session_id, "user", body.message))
            asyncio.create_task(supabase.save_message(session_id, "assistant", question))

            return StreamingResponse(
                _stream_deterministic(question, session_id),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no",
                         "X-Session-ID": session_id},
            )

    # ── 5. Intent detection ──────────────────────────────────────────────────
    intent = detect_intent(body.message)

    # ── 6. Stage transition ──────────────────────────────────────────────────
    current_stage = Stage(conv_state.get("stage", Stage.ONBOARDING.value))

    # If onboarding just completed this turn (or frontend provided it), jump to
    # plan generation if no plan exists yet; otherwise learning.
    if current_stage == Stage.ONBOARDING:
        current_stage = Stage.PLAN_GENERATION if not conv_state.get("plan_generated") else Stage.LEARNING

    new_stage = next_stage(current_stage, intent, conv_state)

    # Track day number if user mentioned one
    day_mentioned = extract_day_number(body.message)
    if day_mentioned and new_stage == Stage.LEARNING:
        conv_state["current_day"] = day_mentioned

    # Mark plan as generated once we leave plan generation stage
    if new_stage != Stage.PLAN_GENERATION and current_stage == Stage.PLAN_GENERATION:
        conv_state["plan_generated"] = True

    if intent == Intent.REQUEST_PLAN:
        # Reset so fresh plan is always generated when explicitly requested
        conv_state["plan_generated"] = False
        new_stage = Stage.PLAN_GENERATION

    conv_state["stage"] = new_stage.value

    # ── 7. History ───────────────────────────────────────────────────────────
    history_from_db = await supabase.get_messages(session_id, limit=40)
    history = _merge_history(history_from_db, _pending_messages.get(session_id, []))

    log_turn(session_id, new_stage, intent, conv_state, len(history))

    # ── 8. Build context ─────────────────────────────────────────────────────
    context_parts: list[str] = []

    # a) Stage-specific instruction (highest priority — tells LLM what to do)
    stage_instruction = build_stage_instruction(new_stage, conv_state)
    if stage_instruction:
        context_parts.append(stage_instruction)

    # b) User profile (from deterministic engine or frontend form)
    if not frontend_onboarding_done and ob.is_complete(ob_state):
        context_parts.append(ob.build_state_summary(ob_state))
    elif frontend_onboarding_done:
        context_parts.append(
            "USER PROFILE (from onboarding — always remember this):\n"
            + body.onboarding_context.strip()
        )

    # c) Live company intel (first 2 turns after plan generation only)
    company = ob_state.get("company") or (session.get("company", "") if session else "")
    role = ob_state.get("role") or (session.get("role", "") if session else "")

    if company and role and len(history) <= 4 and new_stage in (Stage.PLAN_GENERATION, Stage.LEARNING):
        try:
            intel = await retrieval.fetch_company_intel(company, role)
            if intel:
                context_parts.append(intel)
        except Exception as exc:
            logger.warning(f"Company intel fetch failed: {exc}")

    context: Optional[str] = "\n\n---\n\n".join(context_parts) if context_parts else None

    # ── 9. Duplicate detection ───────────────────────────────────────────────
    last_snippet = conv_state.get("last_response_snippet", "")
    if last_snippet and new_stage not in (Stage.PLAN_GENERATION,):
        # Only check for duplicates in non-plan stages (plans can legitimately be long/similar)
        # If duplicate detected, add an explicit anti-repeat instruction
        score_check_text = body.message[:200]
        if is_duplicate_response(score_check_text, last_snippet):
            logger.warning(f"[duplicate] Adding anti-repeat override | session={session_id[:8]}…")
            override = (
                "\n⚠ IMPORTANT: Your previous response was very similar to this one."
                " Do NOT repeat it. Give a different, more specific response"
                " that directly addresses the user's latest question.\n"
            )
            context = (context or "") + override

    # ── Debug logging ─────────────────────────────────────────────────────────
    ctx_chars = len(context) if context else 0
    hist_chars = sum(len(m.get("content", "")) for m in history)
    logger.info(
        f"[prompt] stage={new_stage.value} | intent={intent.value} | "
        f"ctx_chars={ctx_chars} | hist_chars={hist_chars} | "
        f"approx_tokens={(ctx_chars + hist_chars + len(body.message)) // 4}"
    )

    # ── 10. Stream LLM response ───────────────────────────────────────────────
    return StreamingResponse(
        _stream_generator(body.message, session_id, history, context, conv_state),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "X-Session-ID": session_id,
        },
    )


# ─────────────────────────────────────────────────────────────────────────────
# Utility endpoints
# ─────────────────────────────────────────────────────────────────────────────

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
