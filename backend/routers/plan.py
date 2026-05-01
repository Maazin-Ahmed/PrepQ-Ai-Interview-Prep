import json
import logging
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from agents import prepq_agent, retrieval
from db import supabase
from middleware.auth import require_auth
from middleware.security import _detect_violation
from models.schemas import PlanRequest

logger = logging.getLogger("prepq.router.plan")

router = APIRouter()

PLAN_GENERATION_PROMPT = """
Based on everything I've told you, generate my complete PrepQ Plan now.

Company: {company}
Role: {role}
Days Left: {days_left}
Round: {round}
Current Level: {level}
Already Prepared: {prepared}
Skipped / Weak Areas: {skipped}

Generate the full plan in exactly this format:
1. Header block (Company | Role | Days Left | Round)
2. Tier 1 — MUST KNOW (list topics with one-line reason each)
3. Tier 2 — HIGH PRIORITY (list topics with one-line reason each)
4. Tier 3 — GOOD TO HAVE (list topics with one-line reason each)
5. Daily Breakdown (Day-by-day schedule for all {days_left} days)
6. Red Flags (what this company specifically tests that people ignore)
7. Mock Question (end with one question in this company's exact interview style)

Be ruthlessly specific. No generic advice. Every topic must have a reason tied to this exact company and round.
"""


@router.post("")
async def generate_plan(
    body: PlanRequest,
    request: Request,
    user_id: str = Depends(require_auth),
):
    """
    Generates a PrepQ plan via streaming SSE.
    Saves onboarding data to session and stores the plan reference.
    """
    # Security Scan
    oa_data = body.onboarding.model_dump_json() if body.onboarding else ""
    is_violation, _ = _detect_violation(oa_data)
    if is_violation:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Invalid input detected.")

    email = getattr(request.state, "user_email", "")
    await supabase.upsert_user(user_id, email)

    # Session management
    session_id = body.session_id
    if not session_id:
        session = await supabase.create_session(user_id)
        session_id = session["id"]

    # Update session with onboarding data (graceful — won't crash if DB is down)
    oa = body.onboarding
    await supabase.update_session(session_id, {
        "company": oa.company or "",
        "role": oa.role or "",
        "days_left": oa.days_left,
        "round": oa.round or "",
        "level": oa.level or "",
    })

    # Fetch company intel (graceful)
    context: str = ""
    company = oa.company or "the target company"
    role = oa.role or "the target role"
    try:
        context = await retrieval.fetch_company_intel(company, role)
    except Exception as exc:
        logger.warning(f"Company intel fetch failed for plan: {exc}")

    # Build the plan generation prompt
    plan_prompt = PLAN_GENERATION_PROMPT.format(
        company=company,
        role=role,
        days_left=oa.days_left,
        round=oa.round or "Not specified",
        level=oa.level or "Not specified",
        prepared=oa.prepared or "Nothing specified",
        skipped=oa.skipped or "Nothing specified",
    )

    async def _plan_stream():
        # Yield session_id as first metadata event
        yield f'data: {json.dumps({"type": "metadata", "session_id": session_id})}\n\n'

        async for chunk in prepq_agent.stream_response(plan_prompt, [], context):
            yield chunk

    return StreamingResponse(
        _plan_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "X-Session-ID": session_id,
        },
    )


@router.get("/{session_id}")
async def get_plan(
    session_id: str,
    user_id: str = Depends(require_auth),
):
    """Retrieve the stored plan for a session."""
    session = await supabase.get_session(session_id)
    if not session:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Session not found.")

    plan = await supabase.get_plan(session_id)
    return {"session": session, "plan": plan}
