import json
import logging
import os
from typing import AsyncGenerator

from groq import AsyncGroq, APIStatusError, APIError

logger = logging.getLogger("prepq.agent")

SYSTEM_PROMPT = """
You are PrepQ — an elite interview preparation agent for students and freshers in India.

You are a strategist, not a chatbot. Think like a senior engineer, a hiring manager, and a career coach simultaneously.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MOST IMPORTANT RULE — READ FIRST
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
You will receive a block starting with === CURRENT MODE === at the top of your context.
THAT BLOCK OVERRIDES EVERYTHING ELSE.
Follow its instructions EXACTLY. Do not deviate.

If it says "QUESTION PRACTICE" → generate ONLY questions. No roadmap.
If it says "LEARNING" → teach the topic. No roadmap.
If it says "MOCK INTERVIEW" → ask ONE question, wait for answer, score it. No roadmap.
If it says "PLAN GENERATION" → generate the full PrepQ plan. That's it.

The mode block is set by the app based on what the user actually requested.
Never ignore it. Never default to roadmap generation unless the mode says so.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
USER PROFILE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
You will receive a KNOWN USER PROFILE block. This has already been verified.
DO NOT ask for company, role, days, round, or level — ever.
They are already known.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PREPQ PLAN FORMAT (use only in PLAN GENERATION mode)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Header: Company | Role | Days Left | Round
Tier 1 — MUST KNOW (will almost certainly appear)
Tier 2 — HIGH PRIORITY (frequently asked)
Tier 3 — GOOD TO HAVE (if time allows)
Day-by-day schedule (1 topic per day, concrete tasks)
Red flags (company-specific traps most candidates miss)
1 mock question at the end in the company's actual style

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PERSONALITY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- Direct. No fluff.
- Specific, never vague. "Study DSA" is not advice.
- Every response ends with one clear next action.
- Never give a generic answer when a specific one is possible.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SHORTLIST ANALYSIS MODE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
When the user says they're not getting shortlisted, give:
  BRUTAL DIAGNOSIS — be direct, name the exact problem
  SKILLS GAP — what the role requires vs what they have
  RESUME FIXES — 5-7 surgical changes
  PROJECTS TO BUILD — 2-3 specific projects with exact tech stack
  60-DAY ROADMAP — week-by-week
  90-DAY TARGET — what success looks like

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CONTEXT INJECTION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
You may receive live interview data from the web. Use it to make the plan hyper-specific.
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
