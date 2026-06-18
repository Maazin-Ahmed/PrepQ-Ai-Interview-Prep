import asyncio
import json
import logging
import os
import textwrap
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse, JSONResponse

from agents import prepq_agent, retrieval
from agents import onboarding_engine as ob
from agents.conversation_engine import (
    Stage, Intent,
    detect_intent,
    next_stage,
    build_stage_instruction,
    extract_day_number,
    is_duplicate_response,
    log_turn,
    make_empty_conv_state,
)
from db import supabase
from middleware.auth import require_auth
from middleware.security import _detect_violation
from models.schemas import ChatRequest

logger = logging.getLogger("prepq.router.chat")

# Force INFO-level logs even if root logger is set higher
logger.setLevel(logging.DEBUG)

router = APIRouter()

# ─── In-memory buffer for messages not yet flushed to DB ───────────────────
_pending_messages: dict[str, list[dict]] = {}

_DEV_MODE = os.environ.get("ENV", "development") != "production"


# ─────────────────────────────────────────────────────────────────────────────
# Structured log helper
# ─────────────────────────────────────────────────────────────────────────────

def _log_request_start(
    session_id: str,
    user_message: str,
    ob_state: dict,
    conv_state: dict,
    history_count: int,
    intent: Optional[str] = None,
    stage: Optional[str] = None,
) -> None:
    """Emit a single structured log block at the start of every request."""
    sep = "─" * 60
    logger.info(
        f"\n{sep}\n"
        f"[REQUEST START]\n"
        f"  session_id      : {session_id}\n"
        f"  user_message    : {textwrap.shorten(user_message, 80)!r}\n"
        f"  stage           : {stage or conv_state.get('stage', 'unknown')}\n"
        f"  intent          : {intent or 'not yet detected'}\n"
        f"  history_msgs    : {history_count}\n"
        f"  plan_generated  : {conv_state.get('plan_generated', False)}\n"
        f"  current_day     : {conv_state.get('current_day')}\n"
        f"  current_topic   : {conv_state.get('current_topic')}\n"
        f"  ob.company      : {ob_state.get('company')!r}\n"
        f"  ob.role         : {ob_state.get('role')!r}\n"
        f"  ob.days_left    : {ob_state.get('days_left')}\n"
        f"  ob.round        : {ob_state.get('round')!r}\n"
        f"  ob.level        : {ob_state.get('level')!r}\n"
        f"  ob.complete     : {ob.is_complete(ob_state)}\n"
        f"{sep}"
    )


def _log_extraction(session_id: str, extracted: dict, next_field: Optional[str], new_ob_state: dict) -> None:
    logger.info(
        f"[EXTRACTION] session={session_id[:8]}…\n"
        f"  extracted       : {extracted}\n"
        f"  next_field      : {next_field}\n"
        f"  ob_state_after  : {new_ob_state}"
    )


def _log_state_save(session_id: str, ob_state: dict, conv_state: dict) -> None:
    logger.info(
        f"[STATE SAVED] session={session_id[:8]}…\n"
        f"  ob_state        : {ob_state}\n"
        f"  conv_state.stage: {conv_state.get('stage')}\n"
        f"  conv_state.day  : {conv_state.get('current_day')}"
    )


def _log_request_end(session_id: str, response_type: str, new_stage: str) -> None:
    logger.info(
        f"[REQUEST END] session={session_id[:8]}… | "
        f"response={response_type} | new_stage={new_stage}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

async def _save_messages_to_db(
    session_id: str,
    user_message: str,
    assistant_response: str,
) -> None:
    try:
        await supabase.save_message(session_id, "user", user_message)
        await supabase.save_message(session_id, "assistant", assistant_response)
        logger.debug(
            f"[DB WRITE] session={session_id[:8]}… | "
            f"user={len(user_message)}c | assistant={len(assistant_response)}c"
        )
    except Exception as exc:
        logger.warning(f"[DB WRITE FAILED] session={session_id}: {exc}")
    finally:
        _pending_messages.pop(session_id, None)
        logger.debug(f"[PENDING CLEARED] session={session_id[:8]}…")


async def _stream_generator(
    user_message: str,
    session_id: str,
    history: list[dict],
    context: Optional[str],
    conv_state: dict,
):
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

    # Stage in pending buffer immediately (race-condition fix)
    now = datetime.now(timezone.utc).isoformat()
    _pending_messages[session_id] = [
        {"id": str(uuid4()), "session_id": session_id, "role": "user",
         "content": user_message, "created_at": now},
        {"id": str(uuid4()), "session_id": session_id, "role": "assistant",
         "content": assistant_text, "created_at": now},
    ]

    conv_state["last_response_snippet"] = assistant_text[:300]

    logger.info(
        f"[LLM DONE] session={session_id[:8]}… | "
        f"response_chars={len(assistant_text)} | "
        f"saving stage={conv_state.get('stage')}"
    )

    asyncio.create_task(_save_messages_to_db(session_id, user_message, assistant_text))
    asyncio.create_task(supabase.save_conv_state(session_id, conv_state))


async def _stream_deterministic(text: str, session_id: str):
    yield f'data: {json.dumps({"type": "metadata", "session_id": session_id})}\n\n'
    for word in text.split(" "):
        yield f'data: {json.dumps({"type": "chunk", "text": word + " "})}\n\n'
    yield f'data: {json.dumps({"type": "done"})}\n\n'


def _merge_history(db_msgs: list[dict], pending: list[dict]) -> list[dict]:
    if not pending:
        return db_msgs[-20:]
    db_set = {(m["role"], m["content"]) for m in db_msgs}
    new_pending = [p for p in pending if (p["role"], p["content"]) not in db_set]
    merged = (db_msgs + new_pending)[-20:]
    logger.debug(
        f"[HISTORY MERGE] db={len(db_msgs)} pending={len(pending)} "
        f"new_pending={len(new_pending)} total={len(merged)}"
    )
    return merged


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
    Stateful streaming chat endpoint with full structured logging.

    Every request logs:
      [REQUEST START]  — session, message, loaded state, history count
      [EXTRACTION]     — what fields were extracted from the message
      [STATE SAVED]    — what was persisted
      [REQUEST END]    — response type, new stage
    """

    # ── 1. Security ─────────────────────────────────────────────────────────
    is_violation, _ = _detect_violation(body.message)
    if is_violation:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Invalid input detected.")

    email = getattr(request.state, "user_email", "")
    await supabase.upsert_user(user_id, email)

    # ── 2. Session management ────────────────────────────────────────────────
    incoming_session_id = body.session_id
    logger.info(
        f"[SESSION] incoming_session_id={incoming_session_id!r} | user_id={user_id[:8]}…"
    )

    session_id = incoming_session_id
    session: Optional[dict] = None

    if not session_id:
        session = await supabase.create_session(user_id)
        session_id = session["id"]
        logger.info(f"[SESSION] Created new session: {session_id}")
    else:
        session = await supabase.get_session(session_id)
        if not session:
            logger.warning(
                f"[SESSION] session_id={session_id[:8]}… not found in DB/memory — creating new"
            )
            session = await supabase.create_session(user_id)
            session_id = session["id"]
            logger.info(f"[SESSION] New session created (fallback): {session_id}")
        elif session.get("user_id") != user_id:
            from fastapi import HTTPException
            raise HTTPException(status_code=403, detail="Session not found or access denied.")
        else:
            logger.info(f"[SESSION] Existing session found: {session_id[:8]}…")

    # ── 3. Load both state objects in parallel ───────────────────────────────
    ob_state, conv_state = await asyncio.gather(
        supabase.get_onboarding_state(session_id),
        supabase.get_conv_state(session_id),
    )

    logger.info(
        f"[STATE LOADED] session={session_id[:8]}… | "
        f"ob_state={ob_state} | "
        f"conv_stage={conv_state.get('stage')}"
    )

    # ── 4. Log request start ─────────────────────────────────────────────────
    # Load history count for logging (actual load happens later)
    history_preview = await supabase.get_messages(session_id, limit=1)
    approx_history = len(history_preview)  # just to log whether any exist

    _log_request_start(
        session_id=session_id,
        user_message=body.message,
        ob_state=ob_state,
        conv_state=conv_state,
        history_count=approx_history,
    )

    # ── 5. Onboarding gate ───────────────────────────────────────────────────
    frontend_onboarding_done = bool(body.onboarding_context and body.onboarding_context.strip())

    logger.info(
        f"[ONBOARDING] frontend_done={frontend_onboarding_done} | "
        f"onboarding_context_present={bool(body.onboarding_context)} | "
        f"ob_complete={ob.is_complete(ob_state)}"
    )

    if not frontend_onboarding_done:
        new_ob_state, extracted = ob.process_message(body.message, ob_state)
        next_field = ob.next_missing_field(new_ob_state)

        _log_extraction(session_id, extracted, next_field, new_ob_state)

        if extracted:
            ob_state = new_ob_state
            await supabase.save_onboarding_state(session_id, ob_state)
            logger.info(
                f"[OB STATE SAVED] session={session_id[:8]}… | saved={ob_state}"
            )
        else:
            logger.info(
                f"[OB STATE] No new fields extracted — state unchanged: {ob_state}"
            )

        if not ob.is_complete(ob_state):
            question = ob.build_question(next_field)  # type: ignore[arg-type]

            logger.info(
                f"[ONBOARDING QUESTION] field={next_field} | "
                f"question={question!r} | session={session_id[:8]}…"
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

            _log_request_end(session_id, "onboarding_question", "onboarding")

            return StreamingResponse(
                _stream_deterministic(question, session_id),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no",
                         "X-Session-ID": session_id},
            )

    # ── 6. Intent detection ──────────────────────────────────────────────────
    intent = detect_intent(body.message)
    logger.info(f"[INTENT] {intent.value!r} ← {body.message!r}")

    # ── 7. Stage transition ──────────────────────────────────────────────────
    current_stage = Stage(conv_state.get("stage", Stage.ONBOARDING.value))

    if current_stage == Stage.ONBOARDING:
        current_stage = Stage.PLAN_GENERATION if not conv_state.get("plan_generated") else Stage.LEARNING

    new_stage = next_stage(current_stage, intent, conv_state)

    day_mentioned = extract_day_number(body.message)
    if day_mentioned and new_stage == Stage.LEARNING:
        conv_state["current_day"] = day_mentioned
        logger.info(f"[DAY] Set current_day={day_mentioned}")

    if new_stage != Stage.PLAN_GENERATION and current_stage == Stage.PLAN_GENERATION:
        conv_state["plan_generated"] = True

    if intent.value == "request_plan":
        conv_state["plan_generated"] = False
        new_stage = Stage.PLAN_GENERATION

    conv_state["stage"] = new_stage.value

    logger.info(
        f"[STAGE] {current_stage.value} → {new_stage.value} | "
        f"intent={intent.value} | plan_generated={conv_state.get('plan_generated')}"
    )

    # ── 8. History (full load now) ────────────────────────────────────────────
    history_from_db = await supabase.get_messages(session_id, limit=40)
    history = _merge_history(history_from_db, _pending_messages.get(session_id, []))

    logger.info(
        f"[HISTORY] session={session_id[:8]}… | "
        f"db_msgs={len(history_from_db)} | "
        f"pending={len(_pending_messages.get(session_id, []))} | "
        f"sent_to_llm={len(history)}"
    )

    log_turn(session_id, new_stage, intent, conv_state, len(history))

    # ── 9. Build context ─────────────────────────────────────────────────────
    context_parts: list[str] = []

    stage_instruction = build_stage_instruction(new_stage, conv_state)
    if stage_instruction:
        context_parts.append(stage_instruction)

    if not frontend_onboarding_done and ob.is_complete(ob_state):
        profile = ob.build_state_summary(ob_state)
        context_parts.append(profile)
        logger.info(f"[CONTEXT] Injected ob profile: {profile[:80]}…")
    elif frontend_onboarding_done:
        context_parts.append(
            "USER PROFILE (from onboarding — always remember this):\n"
            + body.onboarding_context.strip()
        )
        logger.info("[CONTEXT] Injected frontend onboarding context")

    company = ob_state.get("company") or (session.get("company", "") if session else "")
    role = ob_state.get("role") or (session.get("role", "") if session else "")

    if company and role and len(history) <= 4 and new_stage in (Stage.PLAN_GENERATION, Stage.LEARNING):
        try:
            intel = await retrieval.fetch_company_intel(company, role)
            if intel:
                context_parts.append(intel)
                logger.info(f"[CONTEXT] Company intel injected for {company}/{role}")
        except Exception as exc:
            logger.warning(f"[CONTEXT] Company intel failed: {exc}")

    context: Optional[str] = "\n\n---\n\n".join(context_parts) if context_parts else None

    # ── 10. Duplicate detection ───────────────────────────────────────────────
    last_snippet = conv_state.get("last_response_snippet", "")
    if last_snippet and new_stage not in (Stage.PLAN_GENERATION,):
        if is_duplicate_response(body.message[:200], last_snippet):
            logger.warning(f"[DUPLICATE] Adding anti-repeat override | session={session_id[:8]}…")
            override = (
                "\n⚠ IMPORTANT: Your previous response was very similar to this one."
                " Give a different, more specific response directly addressing the user's latest question.\n"
            )
            context = (context or "") + override

    ctx_chars = len(context) if context else 0
    hist_chars = sum(len(m.get("content", "")) for m in history)
    logger.info(
        f"[PROMPT] stage={new_stage.value} | ctx_chars={ctx_chars} | "
        f"hist_chars={hist_chars} | "
        f"approx_tokens={(ctx_chars + hist_chars + len(body.message)) // 4}"
    )

    # ── 11. Save state before streaming ──────────────────────────────────────
    await supabase.save_conv_state(session_id, conv_state)
    _log_state_save(session_id, ob_state, conv_state)
    _log_request_end(session_id, "llm_stream", new_stage.value)

    # ── 12. Stream LLM response ───────────────────────────────────────────────
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
# Debug endpoint
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/debug/{session_id}")
async def debug_session(
    session_id: str,
    request: Request,
    user_id: str = Depends(require_auth),
):
    """
    GET /chat/debug/{session_id}

    Returns the full live state of a session for debugging:
      sessionId, stage, onboarding_state, conv_state, messageCount, recentMessages
    """
    session = await supabase.get_session(session_id)
    if not session:
        return JSONResponse({"error": "Session not found", "session_id": session_id}, status_code=404)

    ob_state = await supabase.get_onboarding_state(session_id)
    conv_state = await supabase.get_conv_state(session_id)
    messages = await supabase.get_messages(session_id, limit=20)

    # Also check in-memory pending
    pending = _pending_messages.get(session_id, [])

    return JSONResponse({
        "session_id": session_id,
        "user_id": session.get("user_id"),
        "created_at": session.get("created_at"),
        "stage": conv_state.get("stage"),
        "plan_generated": conv_state.get("plan_generated"),
        "current_day": conv_state.get("current_day"),
        "current_topic": conv_state.get("current_topic"),
        "onboarding": {
            "company": ob_state.get("company"),
            "role": ob_state.get("role"),
            "days_left": ob_state.get("days_left"),
            "round": ob_state.get("round"),
            "level": ob_state.get("level"),
            "complete": ob.is_complete(ob_state),
        },
        "conv_state": conv_state,
        "message_count": len(messages),
        "pending_count": len(pending),
        "recent_messages": [
            {
                "role": m.get("role"),
                "content": m.get("content", "")[:120] + ("…" if len(m.get("content", "")) > 120 else ""),
                "created_at": m.get("created_at"),
            }
            for m in messages[-5:]
        ],
        "supabase_available": supabase.is_available(),
        "storage_mode": "supabase" if supabase.is_available() else "in_memory",
    })


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
