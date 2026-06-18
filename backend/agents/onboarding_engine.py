"""
Deterministic Onboarding Engine for PrepQ
==========================================
Replaces the LLM-driven conversational onboarding with a structured state
machine. The engine:

  1. Extracts field values from any user message using regex + keyword rules.
  2. Persists the onboarding state in the session record.
  3. Returns the next question to ask (or None when onboarding is complete).

This means the LLM is NEVER responsible for asking onboarding questions —
it simply receives the completed profile and builds the plan.
"""

import logging
import re
from typing import Optional

logger = logging.getLogger("prepq.onboarding")

# ─── Onboarding state schema ──────────────────────────────────────────────────

ONBOARDING_FIELDS = ["company", "role", "days_left", "round", "level"]

QUESTIONS = {
    "company": {
        "text": "What company are you preparing for?",
        "hint": 'e.g. "Amazon", "TCS", "Google", "Wipro"',
    },
    "role": {
        "text": "What role are you interviewing for?",
        "hint": 'e.g. "DevOps Engineer", "SDE-1", "Data Analyst"',
    },
    "days_left": {
        "text": "How many days until your interview? (type a number, or say 'skip' for 30 days)",
        "hint": "e.g. 7, 14, 30",
    },
    "round": {
        "text": "Which round is this?",
        "hint": "online assessment / technical / HR / case study / managerial / system design",
    },
    "level": {
        "text": "How confident are you in the required skills?",
        "hint": "beginner / some experience / confident",
    },
}

ROUND_ALIASES: dict[str, str] = {
    "oa": "online_assessment",
    "online assessment": "online_assessment",
    "online": "online_assessment",
    "aptitude": "online_assessment",
    "tech": "technical",
    "technical": "technical",
    "coding": "technical",
    "dsa": "technical",
    "hr": "hr",
    "human resource": "hr",
    "behavioural": "hr",
    "behavioral": "hr",
    "case": "case_study",
    "case study": "case_study",
    "managerial": "managerial",
    "manager": "managerial",
    "system design": "system_design",
    "sdi": "system_design",
    "design": "system_design",
}

LEVEL_ALIASES: dict[str, str] = {
    "beginner": "beginner",
    "start": "beginner",
    "new": "beginner",
    "fresher": "beginner",
    "no experience": "beginner",
    "zero": "beginner",
    "some": "some_experience",
    "some experience": "some_experience",
    "intermediate": "some_experience",
    "mid": "some_experience",
    "average": "some_experience",
    "ok": "some_experience",
    "okay": "some_experience",
    "decent": "some_experience",
    "confident": "confident",
    "good": "confident",
    "experienced": "confident",
    "strong": "confident",
    "senior": "confident",
    "expert": "confident",
}

# Well-known Indian companies + top global companies — used to detect company
# names that appear alone without context keywords.
KNOWN_COMPANIES = {
    "amazon", "google", "microsoft", "apple", "meta", "facebook",
    "netflix", "uber", "linkedin", "twitter", "tcs", "infosys",
    "wipro", "cognizant", "accenture", "capgemini", "hcl", "tech mahindra",
    "mphasis", "ltimindtree", "persistent", "mindtree", "hexaware",
    "zoho", "freshworks", "swiggy", "zomato", "flipkart", "meesho",
    "paytm", "phonepe", "razorpay", "cred", "groww", "zerodha",
    "ola", "rapido", "nykaa", "byju", "unacademy", "ibm", "oracle",
    "sap", "dell", "hp", "cisco", "intel", "qualcomm", "nvidia",
    "deloitte", "pwc", "ey", "kpmg", "bcg", "mckinsey",
    "goldman sachs", "jpmorgan", "morgan stanley", "barclays", "hsbc",
    "deutsche bank", "wells fargo", "mastercard", "visa", "stripe",
    "airbnb", "shopify", "atlassian", "salesforce", "adobe",
    "service now", "servicenow", "workday", "samsara",
}

# Role keywords — if a word matches, it's probably a role fragment
ROLE_KEYWORDS = {
    "engineer", "developer", "analyst", "manager", "architect",
    "scientist", "lead", "consultant", "associate", "intern",
    "devops", "sde", "swe", "backend", "frontend", "fullstack",
    "full-stack", "full stack", "data", "cloud", "ml", "ai",
    "security", "qa", "test", "product", "design", "ui", "ux",
    "systems", "platform", "infrastructure", "sre", "reliability",
    "java", "python", "react", "node", "android", "ios", "mobile",
}


def make_empty_state() -> dict:
    """Return a fresh onboarding state with all fields null."""
    return {
        "company": None,
        "role": None,
        "days_left": None,
        "round": None,
        "level": None,
    }


def is_complete(state: dict) -> bool:
    """True when all required fields are filled."""
    return all(state.get(f) for f in ONBOARDING_FIELDS)


def next_missing_field(state: dict) -> Optional[str]:
    """Return the name of the next unfilled required field, or None."""
    for field in ONBOARDING_FIELDS:
        if not state.get(field):
            return field
    return None


# ─── Extraction logic ─────────────────────────────────────────────────────────

def _extract_round(text: str) -> Optional[str]:
    text_lower = text.lower()
    # Longest match first
    for alias in sorted(ROUND_ALIASES, key=len, reverse=True):
        if alias in text_lower:
            return ROUND_ALIASES[alias]
    return None


def _extract_level(text: str) -> Optional[str]:
    text_lower = text.lower()
    for alias in sorted(LEVEL_ALIASES, key=len, reverse=True):
        if alias in text_lower:
            return LEVEL_ALIASES[alias]
    return None


def _extract_days(text: str) -> Optional[int]:
    """Extract a number of days from text. 'skip' → 30."""
    text_lower = text.strip().lower()
    if text_lower in ("skip", "s", "default", "idk", "not sure", ""):
        return 30
    # "in X days", "X days", "X day", just "X"
    m = re.search(r"\b(\d{1,3})\s*(?:days?|d\b)?", text, re.I)
    if m:
        val = int(m.group(1))
        return max(1, min(val, 365))
    return None


def _looks_like_company(word: str) -> bool:
    return word.lower() in KNOWN_COMPANIES


def _looks_like_role(text: str) -> bool:
    words = set(text.lower().split())
    return bool(words & ROLE_KEYWORDS)


def _split_company_role(text: str) -> tuple[Optional[str], Optional[str]]:
    """
    Try to split a combined message like 'DevOps for Amazon' or
    'Amazon DevOps Engineer' into (company, role).
    Returns (None, None) if nothing useful found.
    """
    text_stripped = text.strip()
    text_lower = text_stripped.lower()

    # Pattern: "<role> for <company>" or "<role> at <company>"
    m = re.match(
        r"^(.+?)\s+(?:for|at|in|@)\s+(.+)$",
        text_stripped, re.I
    )
    if m:
        left, right = m.group(1).strip(), m.group(2).strip()
        # Determine which side is company, which is role
        if _looks_like_company(right) and not _looks_like_company(left):
            return right, left
        if _looks_like_company(left) and not _looks_like_company(right):
            return left, right
        # Heuristic: right is usually company after "for/at"
        return right, left

    # Pattern: "<company> <role>" — company is first word if it's known
    words = text_stripped.split()
    if len(words) >= 2:
        first = words[0]
        rest = " ".join(words[1:])
        if _looks_like_company(first):
            return first, rest
        # Last word as company
        last = words[-1]
        rest2 = " ".join(words[:-1])
        if _looks_like_company(last):
            return last, rest2

    return None, None


def extract_fields(
    message: str,
    state: dict,
    current_field: Optional[str],
) -> dict:
    """
    Parse `message` and return a dict of {field: value} for any fields
    that can be extracted. Does NOT mutate `state`.

    `current_field` is the field we're currently expecting an answer for —
    this is used to bias extraction (e.g. if we asked "what company?",
    we treat the reply as the company even without a keyword match).
    """
    extracted: dict = {}
    text = message.strip()

    # ── Always try round/level/days — they're distinctive enough ──
    if not state.get("round"):
        r = _extract_round(text)
        if r:
            extracted["round"] = r

    if not state.get("level"):
        lv = _extract_level(text)
        if lv:
            extracted["level"] = lv

    if not state.get("days_left"):
        # Only parse days when we asked for it OR when the message looks like a number
        if current_field == "days_left" or re.match(r"^\d+\s*(?:days?)?$", text.strip(), re.I):
            d = _extract_days(text)
            if d:
                extracted["days_left"] = d

    # ── Company / Role ──────────────────────────────────────────────────────
    need_company = not state.get("company")
    need_role = not state.get("role")

    if need_company or need_role:
        # Try combined extraction first ("DevOps for Amazon")
        company_guess, role_guess = _split_company_role(text)

        if company_guess and need_company:
            extracted["company"] = _title_case(company_guess)
        if role_guess and need_role:
            extracted["role"] = _title_case(role_guess)

        # Fallback: if we're explicitly asked for company, use the whole reply
        if need_company and "company" not in extracted and current_field == "company":
            extracted["company"] = _title_case(text)

        # Fallback: if we're explicitly asked for role, use the whole reply
        if need_role and "role" not in extracted and current_field == "role":
            extracted["role"] = _title_case(text)

    return extracted


def _title_case(s: str) -> str:
    """Capitalise first letter of each word, preserve abbreviations."""
    return " ".join(
        word if word.isupper() else word.capitalize()
        for word in s.strip().split()
    )


# ─── Public API ───────────────────────────────────────────────────────────────

def process_message(message: str, state: dict) -> tuple[dict, dict]:
    """
    Given a user message and the current onboarding state, return:
      (new_state, extracted_fields)

    new_state is a copy of state with any newly extracted fields applied.
    extracted_fields is the dict of {field: value} extracted from this message.
    """
    current_field = next_missing_field(state)
    extracted = extract_fields(message, state, current_field)

    new_state = {**state, **extracted}
    return new_state, extracted


def build_question(field: str) -> str:
    """Return the question string for a given field."""
    q = QUESTIONS.get(field, {})
    text = q.get("text", f"What is your {field}?")
    hint = q.get("hint", "")
    if hint:
        return f"{text}\n({hint})"
    return text


def build_state_summary(state: dict) -> str:
    """
    Build a concise human-readable summary of known onboarding fields
    to inject into the system prompt so the LLM knows what it already has.
    """
    lines = ["KNOWN USER PROFILE (already collected — do NOT ask for these again):"]
    field_labels = {
        "company": "Company",
        "role": "Role",
        "days_left": "Days until interview",
        "round": "Interview round",
        "level": "Skill level",
    }
    for field in ONBOARDING_FIELDS:
        val = state.get(field)
        if val:
            label = field_labels.get(field, field)
            lines.append(f"  • {label}: {val}")
    return "\n".join(lines)


def log_state(session_id: str, state: dict, extracted: dict, next_field: Optional[str]) -> None:
    """Emit a structured log line for debugging."""
    logger.info(
        f"[onboarding] session={session_id[:8]}… | "
        f"state={state} | "
        f"extracted={extracted} | "
        f"next_field={next_field}"
    )
