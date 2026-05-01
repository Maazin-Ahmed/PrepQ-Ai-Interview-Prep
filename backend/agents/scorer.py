import json
import logging
import os
from typing import Optional

from groq import AsyncGroq

from agents.prepq_agent import MODEL

logger = logging.getLogger("prepq.scorer")

SCORING_SYSTEM_PROMPT = """
You are a strict, expert technical interviewer evaluating a candidate's answer.
Your job is to score the answer on three dimensions and provide actionable, specific feedback.
You must respond ONLY with a valid JSON object — no prose, no markdown, no code fences.
"""

SCORING_PROMPT_TEMPLATE = """
Company: {company}
Role: {role}
Interview Question: {question}

Candidate's Answer:
{answer}

Evaluate this answer and respond with ONLY this JSON structure:
{{
  "clarity": <integer 1-5>,
  "correctness": <integer 1-5>,
  "depth": <integer 1-5>,
  "feedback": "<2-4 sentences: what they got right, what was weak, what was missing>",
  "missing": ["<specific missing concept 1>", "<specific missing concept 2>"],
  "next_question": "<a follow-up question that escalates difficulty based on this answer>"
}}

Scoring rubric:
- clarity (1-5): Is the answer structured and easy to follow? 1=incoherent, 5=perfectly structured
- correctness (1-5): Is the answer technically accurate? 1=wrong, 5=fully correct
- depth (1-5): Does the answer go beyond surface level? 1=superficial, 5=expert-level insight

Be direct. Do not soften feedback. Name exactly what is missing.
The "missing" array should contain specific topics/concepts that were absent, not vague suggestions.
The "next_question" should be harder than the current question if score is high, or probe a gap if score is low.
"""


async def score_answer(
    question: str,
    answer: str,
    company: str = "",
    role: str = "",
) -> dict:
    """
    Evaluates a mock interview answer using Claude.
    Returns a structured score dict with clarity, correctness, depth, feedback, missing, next_question.
    """
    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is not set.")

    client = AsyncGroq(api_key=api_key)

    prompt = SCORING_PROMPT_TEMPLATE.format(
        company=company or "the target company",
        role=role or "the target role",
        question=question,
        answer=answer,
    )

    response = await client.chat.completions.create(
        model=MODEL,
        max_tokens=1024,
        messages=[
            {"role": "system", "content": SCORING_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
    )

    raw = response.choices[0].message.content or "{}"

    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning(f"Scorer returned non-JSON response: {raw[:200]}")
        # Attempt to extract JSON from the response if Claude wrapped it
        import re
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            try:
                result = json.loads(match.group())
            except json.JSONDecodeError:
                result = {}
        else:
            result = {}

    # Validate and clamp scores
    def clamp(val, lo=1, hi=5) -> int:
        try:
            return max(lo, min(hi, int(val)))
        except (TypeError, ValueError):
            return 3

    clarity = clamp(result.get("clarity", 3))
    correctness = clamp(result.get("correctness", 3))
    depth = clamp(result.get("depth", 3))
    overall = round((clarity + correctness + depth) / 3, 1)

    return {
        "clarity": clarity,
        "correctness": correctness,
        "depth": depth,
        "overall": overall,
        "feedback": result.get("feedback", "No feedback available."),
        "missing": result.get("missing", []),
        "next_question": result.get("next_question"),
    }
