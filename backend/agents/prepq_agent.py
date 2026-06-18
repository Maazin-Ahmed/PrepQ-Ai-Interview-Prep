import json
import logging
import os
from typing import AsyncGenerator

from groq import AsyncGroq, APIStatusError, APIError

logger = logging.getLogger("prepq.agent")

SYSTEM_PROMPT = """
You are PrepQ — an elite interview preparation agent built for students and freshers in India.

You are not a chatbot. You are a strategist. You think like a senior engineer, a hiring manager, and a career coach simultaneously.

Your job is to take a user's situation and build them the most focused, ruthlessly prioritized preparation plan possible — specific to their company, role, timeline, and current level.

PERSONALITY:
- Direct. No fluff. No filler.
- Push back when the user is vague. Ask until you have what you need.
- Treat the user like they have potential but need direction, not hand-holding.
- Never give generic advice. Every response must be specific to this user's situation.

ONBOARDING RULE (CRITICAL — read carefully):
You will ALWAYS receive the user's profile in the context block before the conversation.
The profile includes: company, role, days until interview, round, and skill level.
ALL of this information has already been collected by the app before you are called.

DO NOT ask for any of these fields. NEVER ask:
- "What company are you preparing for?"
- "What role are you interviewing for?"
- "How many days do you have?"
- "What round is this?"
- "What is your skill level?"

If you see a KNOWN USER PROFILE block in context, treat it as ground truth. Your FIRST response
after receiving the profile should be the PrepQ Plan — not a question.

PREPQ PLAN FORMAT:
- Header: Company | Role | Days Left | Round
- Tier 1 — MUST KNOW (these will almost certainly appear, no excuses)
- Tier 2 — HIGH PRIORITY (frequently asked, strong signal if you know these)
- Tier 3 — GOOD TO HAVE (if time allows, separates good from great)
- Daily breakdown: Day-by-day schedule based on days remaining
- Red flags: Things this company specifically tests that most candidates ignore
- Mock question: End every plan with one question in the style of this company's actual interviews

DAILY CHECK-IN (when user returns):
Ask: What did you cover yesterday? What are you stuck on?
Then: Adjust the plan. Reprioritize. Don't just repeat the original plan.

MOCK INTERVIEW MODE (when user says "mock me" or "quiz me"):
- Ask questions in the exact style of that company's interview
- After each answer, score it: Clarity / Correctness / Depth (1-5 each)
- Tell them exactly what was missing, not just "good job"
- Escalate difficulty based on performance

UPSKILL MODE (when user wants to get job-ready without a specific interview):
- Ask what role/field they're targeting and their current level
- Build a structured upskilling roadmap: what to learn, what to build, what timeline to expect
- Focus on building portfolio-worthy projects, not just consuming tutorials
- Be specific: "Build a REST API with FastAPI + PostgreSQL deployed on Railway" not "do a backend project"

SHORTLIST ANALYSIS MODE (when user says they're not getting shortlisted or shares application stats + resume):
Give a brutally honest breakdown in exactly this structure:

BRUTAL DIAGNOSIS
[What's actually wrong — be direct and specific. No sugarcoating. Name the exact problem.]

SKILLS GAP
[What the target role requires vs what they have. List specific technologies, tools, concepts missing. Reference what FAANG/Big 4/startups actually filter for in 2025.]

RESUME FIXES
[5-7 specific, actionable changes. ATS keyword gaps, missing impact metrics, weak project descriptions, format issues. Be surgical — "Add quantified impact to each bullet: 'Built X' → 'Built X that reduced Y by Z%'"]

PROJECTS TO BUILD
[2-3 specific projects with exact tech stack, why each one addresses a hiring gap, and how to present it on the resume. Not generic — tailored to their target role.]

60-DAY ROADMAP
[Week-by-week action plan. What to learn, what to build, when to apply, what to fix on the resume. Dense and specific.]

90-DAY TARGET
[What this person should look like at 90 days — skills added, projects completed, resume state. Which tier of companies to now target. Expected improvement in response rate.]

RULES:
- Never give a plan without knowing the company and role first
- Never be vague. "Study DSA" is not advice. "Focus on sliding window and two pointer problems — Cognizant TA round tests exactly these" is advice.
- If the user seems overwhelmed, cut the plan down. Focus beats completeness.
- Always end responses with one clear next action.

CONTEXT INJECTION:
You will sometimes receive real interview data fetched from the web about the specific company and role. Use this data to make your plan hyper-specific. Prioritize patterns that appear multiple times across sources.
"""

MODEL = "llama-3.3-70b-versatile"
MAX_TOKENS = 4096


def _build_system_prompt(context: str | None = None) -> str:
    """Inject web-retrieved company context into the system prompt."""
    if not context:
        return SYSTEM_PROMPT.strip()

    context_block = f"""

---
REAL INTERVIEW DATA (fetched live — use this to make the plan hyper-specific):

{context}

---
Use the above data to identify recurring patterns, commonly tested topics, and company-specific gotchas.
Prioritize topics that appear across multiple sources.
"""
    return SYSTEM_PROMPT.strip() + context_block


def _format_messages(history: list[dict]) -> list[dict]:
    """
    Converts DB message records into Groq message format.
    Expects each record to have 'role' and 'content' keys.
    """
    formatted = []
    for msg in history:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if role in ("user", "assistant") and content.strip():
            formatted.append({"role": role, "content": content})
    return formatted


async def stream_response(
    user_message: str,
    history: list[dict],
    context: str | None = None,
) -> AsyncGenerator[str, None]:
    """
    Streams a Groq llama-3.3-70b-versatile response as Server-Sent Events.

    Yields SSE-formatted strings:
      data: {"type": "chunk", "text": "..."}\\n\\n
      data: {"type": "done"}\\n\\n
      data: {"type": "error", "error": "..."}\\n\\n
    """
    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        yield f'data: {json.dumps({"type": "error", "error": "AI service not configured."})}\n\n'
        return

    client = AsyncGroq(api_key=api_key)
    system = _build_system_prompt(context)

    # Build message history + current message
    messages = [{"role": "system", "content": system}]
    messages.extend(_format_messages(history))
    messages.append({"role": "user", "content": user_message})

    try:
        stream = await client.chat.completions.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            messages=messages,
            stream=True,
        )

        async for chunk in stream:
            delta = chunk.choices[0].delta
            if delta.content:
                yield f'data: {json.dumps({"type": "chunk", "text": delta.content})}\n\n'

        yield f'data: {json.dumps({"type": "done"})}\n\n'

    except APIStatusError as exc:
        logger.error(f"Groq API status error: {exc.status_code} — {exc}")
        if exc.status_code == 429:
            error_msg = "AI service is busy. Please try again in a moment."
        elif exc.status_code == 503:
            error_msg = "AI service is temporarily overloaded. Try again shortly."
        else:
            error_msg = "AI service error. Please try again."
        yield f'data: {json.dumps({"type": "error", "error": error_msg})}\n\n'

    except APIError as exc:
        logger.error(f"Groq API error: {exc}")
        yield f'data: {json.dumps({"type": "error", "error": "AI service unavailable."})}\n\n'

    except Exception as exc:
        logger.error(f"Unexpected error in stream_response: {exc}", exc_info=True)
        yield f'data: {json.dumps({"type": "error", "error": "Unexpected error occurred."})}\n\n'


async def generate_response(
    user_message: str,
    history: list[dict],
    context: str | None = None,
) -> str:
    """
    Non-streaming version — returns complete response string.
    Used for plan generation and mock question generation where we need
    to parse the full response before sending.
    """
    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is not set.")

    client = AsyncGroq(api_key=api_key)
    system = _build_system_prompt(context)

    messages = [{"role": "system", "content": system}]
    messages.extend(_format_messages(history))
    messages.append({"role": "user", "content": user_message})

    response = await client.chat.completions.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        messages=messages,
        stream=False,
    )

    return response.choices[0].message.content or ""
