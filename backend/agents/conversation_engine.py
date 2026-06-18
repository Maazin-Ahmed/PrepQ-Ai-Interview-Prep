"""
PrepQ Conversation Engine
=========================
Manages conversation stage, intent detection, and state-aware prompt
injection so the LLM always knows:

  1. What stage we are in (ONBOARDING / PLAN_GENERATION / LEARNING /
     QUESTION_PRACTICE / MOCK_INTERVIEW / REVISION)
  2. What the user's latest intent is
  3. What it must NOT do (e.g., never re-generate the roadmap in LEARNING mode)

This module is purely deterministic — no LLM calls.

Public API
----------
  detect_intent(message)          → Intent enum value
  next_stage(current, intent)     → Stage enum value
  build_stage_prompt(state, context_parts) → str injected before history
  load_conv_state(session_id)     → dict
  save_conv_state(session_id, state) → None   [called by router]
"""

from __future__ import annotations

import logging
import re
from enum import Enum
from typing import Optional

logger = logging.getLogger("prepq.conversation")


# ─── Stages ───────────────────────────────────────────────────────────────────

class Stage(str, Enum):
    ONBOARDING        = "onboarding"
    PLAN_GENERATION   = "plan_generation"
    LEARNING          = "learning"
    QUESTION_PRACTICE = "question_practice"
    MOCK_INTERVIEW    = "mock_interview"
    REVISION          = "revision"


# ─── Intents ──────────────────────────────────────────────────────────────────

class Intent(str, Enum):
    PROVIDE_INFO      = "provide_info"        # answering an onboarding question
    REQUEST_PLAN      = "request_plan"        # "create a study plan", "give me roadmap"
    START_DAY         = "start_day"           # "let's start day 1", "start day 3"
    REQUEST_QUESTIONS = "request_questions"   # "give me questions", "quiz me"
    REQUEST_MOCK      = "request_mock"        # "mock interview", "test me", "interview me"
    REQUEST_REVISION  = "request_revision"    # "revise", "quick recap", "summary"
    LEARNING          = "learning"            # "explain X", "what is X", "how does X work"
    CHECK_IN          = "check_in"            # "what's next", "what should I do"
    ANSWER_MOCK       = "answer_mock"         # providing an answer during mock interview
    GENERAL           = "general"             # anything else


# ─── Intent patterns (regex, ordered highest → lowest priority) ───────────────

_INTENT_PATTERNS: list[tuple[re.Pattern, Intent]] = [
    # Plan / roadmap requests
    (re.compile(
        r"\b(create|make|give|build|generate|show|need)\b.{0,30}\b(plan|roadmap|schedule|prep plan|study plan)\b"
        r"|\b(roadmap|study plan|prep plan)\b",
        re.I
    ), Intent.REQUEST_PLAN),

    # Start a specific day
    (re.compile(
        r"\b(start|begin|let'?s?\s+(?:start|do|go with)|do)\b.{0,20}\bday\s*\d+\b"
        r"|\bday\s*\d+\b.{0,20}\b(start|begin|topic|content)\b",
        re.I
    ), Intent.START_DAY),

    # Questions / quiz
    (re.compile(
        r"\b(give me|show me|i want|generate|create|ask me)\b.{0,25}\b(questions?|quiz|problems?|exercises?|practice)\b"
        r"|\b(quiz me|practice questions?|more questions?|questions? for day\s*\d+)\b",
        re.I
    ), Intent.REQUEST_QUESTIONS),

    # Mock interview
    (re.compile(
        r"\b(mock|interview me|take my|conduct|start|do)\b.{0,20}\b(interview|mock)\b"
        r"|\b(test me|interview me|mock me)\b",
        re.I
    ), Intent.REQUEST_MOCK),

    # Revision / recap
    (re.compile(
        r"\b(revise|revision|recap|summary|quick review|review)\b",
        re.I
    ), Intent.REQUEST_REVISION),

    # Learning / explain
    (re.compile(
        r"\b(explain|what is|what are|how (does|do|to)|tell me about|describe|define|elaborate)\b",
        re.I
    ), Intent.LEARNING),

    # Check in / next steps
    (re.compile(
        r"\b(what('?s| is) next|what should i (do|study|focus)|where (do i|should i) start"
        r"|what (do i|should i) (cover|learn)|next (step|topic)|guide me)\b",
        re.I
    ), Intent.CHECK_IN),
]


def detect_intent(message: str) -> Intent:
    """
    Classify the user's message into one of the Intent values.
    Returns Intent.GENERAL if nothing matches.
    """
    for pattern, intent in _INTENT_PATTERNS:
        if pattern.search(message):
            logger.debug(f"[intent] '{message[:60]}' → {intent.value}")
            return intent
    logger.debug(f"[intent] '{message[:60]}' → general")
    return Intent.GENERAL


# ─── Stage transition table ───────────────────────────────────────────────────

def next_stage(current: Stage, intent: Intent, conv_state: dict) -> Stage:
    """
    Given the current stage and detected intent, return the next stage.
    conv_state is consulted to decide whether a plan already exists.
    """
    plan_exists = conv_state.get("plan_generated", False)

    # Explicit transitions regardless of current stage
    if intent == Intent.REQUEST_PLAN:
        return Stage.PLAN_GENERATION
    if intent == Intent.START_DAY:
        return Stage.LEARNING
    if intent == Intent.REQUEST_QUESTIONS:
        return Stage.QUESTION_PRACTICE
    if intent == Intent.REQUEST_MOCK:
        return Stage.MOCK_INTERVIEW
    if intent == Intent.REQUEST_REVISION:
        return Stage.REVISION

    # Stage-specific defaults
    if current == Stage.PLAN_GENERATION and plan_exists:
        return Stage.LEARNING
    if current == Stage.LEARNING and intent == Intent.LEARNING:
        return Stage.LEARNING
    if current == Stage.MOCK_INTERVIEW and intent == Intent.ANSWER_MOCK:
        return Stage.MOCK_INTERVIEW

    return current  # stay in current stage


# ─── Conversation state schema ────────────────────────────────────────────────

def make_empty_conv_state() -> dict:
    return {
        "stage": Stage.ONBOARDING.value,
        "plan_generated": False,
        "current_day": None,
        "current_topic": None,
        "mock_question_index": 0,
        "last_response_snippet": "",   # first 300 chars of last assistant response
    }


# ─── Stage-aware prompt builder ───────────────────────────────────────────────

# These are injected as a system-level instruction block RIGHT BEFORE the
# history so the LLM knows exactly what to do this turn.

_STAGE_INSTRUCTIONS: dict[Stage, str] = {
    Stage.PLAN_GENERATION: """
=== CURRENT MODE: PLAN GENERATION ===
The user wants a PrepQ Plan.
Generate the full PrepQ plan right now using the profile above.
DO NOT ask any clarifying questions.
Format:
  • Header: Company | Role | Days Left | Round
  • Tier 1 — MUST KNOW
  • Tier 2 — HIGH PRIORITY
  • Tier 3 — GOOD TO HAVE
  • Day-by-day schedule
  • Red flags (company-specific traps)
  • 1 mock question at the end
""",

    Stage.LEARNING: """
=== CURRENT MODE: LEARNING ===
The user wants to LEARN / START a specific day's content.
DO NOT regenerate the roadmap.
DO NOT summarize what was already covered.
Your response must:
  1. State the current topic clearly (e.g., "Today: Data Warehousing")
  2. Explain the theory in depth, with examples
  3. Give 2-3 targeted practice questions at the end
  4. End with: "Type 'questions' for more practice, or 'next topic' to continue."
""",

    Stage.QUESTION_PRACTICE: """
=== CURRENT MODE: QUESTION PRACTICE ===
The user wants QUESTIONS — not explanations, not roadmaps.
Generate exactly 8-10 questions on the current topic.
Format each as:
  Q1. [question text]
  Q2. ...
No answers. No explanations. Just questions.
End with: "Answer any one and I'll evaluate it, or type 'answers' to see solutions."
""",

    Stage.MOCK_INTERVIEW: """
=== CURRENT MODE: MOCK INTERVIEW ===
You are conducting a technical mock interview.
Rules:
  - Ask ONE question at a time.
  - Wait for the user's answer before asking the next.
  - After each answer, score it: Clarity / Correctness / Depth (1-5 each)
  - Give specific feedback — exactly what was missing.
  - Then ask the next question.
  - DO NOT dump multiple questions at once.
  - DO NOT regenerate the roadmap.
""",

    Stage.REVISION: """
=== CURRENT MODE: REVISION ===
The user wants a quick recap / revision.
Give a concise summary of the key topics covered so far.
Format as bullet points — no walls of text.
End with: "Ready for a mock interview? Type 'test me'."
""",

    Stage.ONBOARDING: """
=== CURRENT MODE: ONBOARDING ===
The user's profile is still being collected.
This turn is handled by the onboarding engine — the LLM should not be called.
""",
}


def build_stage_instruction(stage: Stage, conv_state: dict) -> str:
    """
    Build the stage-specific instruction block to prepend to the LLM context.
    Includes current_day and current_topic if available.
    """
    instruction = _STAGE_INSTRUCTIONS.get(stage, "")

    current_day = conv_state.get("current_day")
    current_topic = conv_state.get("current_topic")

    supplements = []
    if current_day:
        supplements.append(f"Current study day: Day {current_day}")
    if current_topic:
        supplements.append(f"Current topic: {current_topic}")

    if supplements:
        instruction += "\nCONTEXT:\n" + "\n".join(f"  • {s}" for s in supplements) + "\n"

    return instruction.strip()


# ─── Day / topic extraction ───────────────────────────────────────────────────

def extract_day_number(message: str) -> Optional[int]:
    """Extract 'day X' number from a message like 'let's start day 3'."""
    m = re.search(r"\bday\s*(\d+)\b", message, re.I)
    return int(m.group(1)) if m else None


def extract_topic_from_plan(plan_text: str, day: int) -> Optional[str]:
    """
    Try to extract the topic for a given day from the plan text.
    Looks for patterns like 'Day 3: Topic Name' or 'Day 3 — Topic'.
    """
    patterns = [
        rf"Day\s*{day}\s*[:\-–—]\s*(.+?)(?:\n|$)",
        rf"\b{day}\.\s+(.+?)(?:\n|$)",
    ]
    for pat in patterns:
        m = re.search(pat, plan_text, re.I)
        if m:
            return m.group(1).strip()
    return None


# ─── Duplicate / repeat detection ────────────────────────────────────────────

def similarity_score(text_a: str, text_b: str) -> float:
    """
    Fast approximate similarity using word overlap.
    Returns 0.0–1.0. Above 0.7 = suspiciously similar.
    """
    if not text_a or not text_b:
        return 0.0
    words_a = set(text_a.lower().split())
    words_b = set(text_b.lower().split())
    if not words_a or not words_b:
        return 0.0
    intersection = words_a & words_b
    union = words_a | words_b
    return len(intersection) / len(union)


def is_duplicate_response(new_text: str, last_snippet: str) -> bool:
    """
    Returns True if new_text is suspiciously similar to last_snippet,
    indicating the LLM is repeating itself.
    """
    score = similarity_score(new_text[:500], last_snippet)
    if score > 0.70:
        logger.warning(
            f"[duplicate] Similarity score={score:.2f} — response is too similar to previous"
        )
        return True
    return False


# ─── Log helper ──────────────────────────────────────────────────────────────

def log_turn(
    session_id: str,
    stage: Stage,
    intent: Intent,
    conv_state: dict,
    history_count: int,
) -> None:
    logger.info(
        f"[conv] session={session_id[:8]}… | "
        f"stage={stage.value} | "
        f"intent={intent.value} | "
        f"day={conv_state.get('current_day')} | "
        f"topic={conv_state.get('current_topic')} | "
        f"plan_generated={conv_state.get('plan_generated')} | "
        f"history_msgs={history_count}"
    )
