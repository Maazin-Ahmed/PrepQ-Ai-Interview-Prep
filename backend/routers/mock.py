import logging
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from agents import prepq_agent, scorer
from db import supabase
from middleware.auth import require_auth
from models.schemas import MockScoreRequest, MockQuestionRequest

logger = logging.getLogger("prepq.router.mock")

router = APIRouter()

MOCK_QUESTION_PROMPT = """
I'm ready for a mock interview for {company} {role}.
This is question {index_display} in the mock session.
Previous performance context: {performance_context}

Generate one interview question in the exact style and difficulty level used by {company} for {role} interviews.
Ask only the question — no explanations, no hints, no preamble.
Make it specific, not generic. It should match the actual pattern this company uses.
"""


def _build_performance_context(previous_scores: list[dict]) -> str:
    if not previous_scores:
        return "This is the first question — start at medium difficulty."

    avg_scores = [
        (s.get("clarity", 3) + s.get("correctness", 3) + s.get("depth", 3)) / 3
        for s in previous_scores
    ]
    avg = sum(avg_scores) / len(avg_scores) if avg_scores else 3.0

    if avg >= 4.5:
        return f"Candidate is performing excellently (avg {avg:.1f}/5). Escalate to senior-level difficulty."
    elif avg >= 3.5:
        return f"Candidate is performing well (avg {avg:.1f}/5). Maintain current difficulty, probe edge cases."
    elif avg >= 2.5:
        return f"Candidate is performing adequately (avg {avg:.1f}/5). Stay at current level, ask for clarification on gaps."
    else:
        return f"Candidate is struggling (avg {avg:.1f}/5). Return to fundamentals, test core concepts."


@router.post("/question")
async def get_mock_question(
    body: MockQuestionRequest,
    request: Request,
    user_id: str = Depends(require_auth),
):
    """
    Streams the next mock interview question.
    Adapts difficulty based on previous answer scores.
    """
    session = await supabase.get_session(body.session_id)

    company = "the target company"
    role = "the target role"

    if session:
        if session.get("user_id") != user_id:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Session not found.")
        company = session.get("company", company) or company
        role = session.get("role", role) or role

    # For now, performance context is based on question index
    performance_context = _build_performance_context([])

    prompt = MOCK_QUESTION_PROMPT.format(
        company=company,
        role=role,
        index_display=f"#{body.question_index + 1}",
        performance_context=performance_context,
    )

    return StreamingResponse(
        prepq_agent.stream_response(prompt, []),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/score")
async def score_mock_answer(
    body: MockScoreRequest,
    request: Request,
    user_id: str = Depends(require_auth),
):
    """
    Evaluates a mock interview answer.
    Returns structured score with clarity, correctness, depth, feedback, and a follow-up question.
    """
    session = await supabase.get_session(body.session_id)

    company = ""
    role = ""

    if session:
        if session.get("user_id") != user_id:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Session not found.")
        company = session.get("company", "")
        role = session.get("role", "")

    score_result = await scorer.score_answer(
        question=body.question,
        answer=body.answer,
        company=company,
        role=role,
    )

    # Attach question/answer to result for frontend convenience
    return {
        "question": body.question,
        "answer": body.answer,
        "session_id": body.session_id,
        "question_index": body.question_index,
        **score_result,
    }
