"""
Supabase database client — fully optional in development.

When SUPABASE_URL is missing, invalid, or unreachable, all functions
return in-memory fallback data and log warnings. The core AI chat flow
is never blocked by database availability.
"""

import logging
import os
from typing import Optional
from uuid import uuid4
from datetime import datetime, timezone

logger = logging.getLogger("prepq.db")

_client = None
_available = False

# ─────────────────────────────────────────────
# In-memory fallback store (dev mode only)
# ─────────────────────────────────────────────
_mem_sessions: dict[str, dict] = {}
_mem_messages: dict[str, list[dict]] = {}
_mem_plans: dict[str, dict] = {}


def _is_valid_url(url: str) -> bool:
    """Check if a string looks like a valid Supabase URL."""
    return url.startswith("https://") and ".supabase.co" in url


def _init_client():
    """Try to initialize the Supabase client. Fail silently in dev."""
    global _client, _available

    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_SERVICE_KEY", "")

    if not url or not key:
        logger.warning("SUPABASE_URL or SUPABASE_SERVICE_KEY not set — running in offline mode.")
        return

    if not _is_valid_url(url):
        logger.warning(
            f"SUPABASE_URL looks invalid (got: '{url[:50]}...'). "
            f"Expected format: https://xxxxx.supabase.co — running in offline mode."
        )
        return

    try:
        from supabase import create_client
        _client = create_client(url, key)
        _available = True
        logger.info("Supabase client initialized successfully.")
    except Exception as exc:
        logger.warning(f"Supabase client init failed — running in offline mode: {exc}")


# Initialize on module import
_init_client()


def get_supabase():
    """Returns the Supabase client or None if unavailable."""
    return _client


def is_available() -> bool:
    """Returns True if Supabase is connected and operational."""
    return _available


# ─────────────────────────────────────────────
# USERS
# ─────────────────────────────────────────────

async def upsert_user(user_id: str, email: str) -> dict:
    if not _available:
        return {"id": user_id, "email": email}
    try:
        result = (
            _client.table("users")
            .upsert({"id": user_id, "email": email}, on_conflict="id")
            .execute()
        )
        return result.data[0] if result.data else {}
    except Exception as exc:
        logger.warning(f"upsert_user failed (continuing): {exc}")
        return {"id": user_id, "email": email}


async def get_user(user_id: str) -> Optional[dict]:
    if not _available:
        return {"id": user_id}
    try:
        result = _client.table("users").select("*").eq("id", user_id).maybe_single().execute()
        return result.data
    except Exception as exc:
        logger.warning(f"get_user failed (continuing): {exc}")
        return {"id": user_id}


# ─────────────────────────────────────────────
# SESSIONS
# ─────────────────────────────────────────────

async def create_session(user_id: str) -> dict:
    session_id = str(uuid4())
    now = datetime.now(timezone.utc).isoformat()
    fallback = {"id": session_id, "user_id": user_id, "created_at": now}

    if not _available:
        _mem_sessions[session_id] = fallback
        return fallback
    try:
        result = (
            _client.table("sessions")
            .insert({"id": session_id, "user_id": user_id})
            .execute()
        )
        return result.data[0]
    except Exception as exc:
        logger.warning(f"create_session failed (using in-memory): {exc}")
        _mem_sessions[session_id] = fallback
        return fallback


async def get_session(session_id: str) -> Optional[dict]:
    if not _available:
        return _mem_sessions.get(session_id)
    try:
        result = (
            _client.table("sessions")
            .select("*")
            .eq("id", session_id)
            .maybe_single()
            .execute()
        )
        return result.data
    except Exception as exc:
        logger.warning(f"get_session failed (checking in-memory): {exc}")
        return _mem_sessions.get(session_id)


async def update_session(session_id: str, updates: dict) -> dict:
    if not _available:
        if session_id in _mem_sessions:
            _mem_sessions[session_id].update(updates)
        else:
            _mem_sessions[session_id] = {"id": session_id, **updates}
        return _mem_sessions[session_id]
    try:
        result = (
            _client.table("sessions")
            .update(updates)
            .eq("id", session_id)
            .execute()
        )
        return result.data[0] if result.data else {}
    except Exception as exc:
        logger.warning(f"update_session failed (using in-memory): {exc}")
        if session_id in _mem_sessions:
            _mem_sessions[session_id].update(updates)
        return _mem_sessions.get(session_id, {})


async def get_user_sessions(user_id: str, limit: int = 10) -> list[dict]:
    if not _available:
        return [s for s in _mem_sessions.values() if s.get("user_id") == user_id][:limit]
    try:
        result = (
            _client.table("sessions")
            .select("*")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return result.data or []
    except Exception as exc:
        logger.warning(f"get_user_sessions failed: {exc}")
        return []


# ─────────────────────────────────────────────
# ONBOARDING STATE
# Stored as a JSON blob inside the session record so it survives
# backend restarts even in offline mode (in-memory store).
# ─────────────────────────────────────────────

async def get_onboarding_state(session_id: str) -> dict:
    """
    Load the structured onboarding state for a session.
    Returns an empty state dict if not yet set.
    """
    from agents.onboarding_engine import make_empty_state
    if not _available:
        session = _mem_sessions.get(session_id, {})
        return session.get("onboarding_state") or make_empty_state()
    try:
        result = (
            _client.table("sessions")
            .select("onboarding_state")
            .eq("id", session_id)
            .maybe_single()
            .execute()
        )
        if result.data and result.data.get("onboarding_state"):
            return result.data["onboarding_state"]
    except Exception as exc:
        logger.warning(f"get_onboarding_state failed: {exc}")
    return make_empty_state()


async def save_onboarding_state(session_id: str, state: dict) -> None:
    """
    Persist the onboarding state dict into the session record.
    Silently skips if the column doesn't exist in Supabase yet.
    """
    if not _available:
        if session_id in _mem_sessions:
            _mem_sessions[session_id]["onboarding_state"] = state
        else:
            _mem_sessions[session_id] = {"id": session_id, "onboarding_state": state}
        return
    try:
        _client.table("sessions").update(
            {"onboarding_state": state}
        ).eq("id", session_id).execute()
    except Exception as exc:
        logger.warning(f"save_onboarding_state failed (non-critical): {exc}")
        # Degrade to in-memory so the session doesn't lose state
        if session_id in _mem_sessions:
            _mem_sessions[session_id]["onboarding_state"] = state
        else:
            _mem_sessions[session_id] = {"id": session_id, "onboarding_state": state}




# ─────────────────────────────────────────────
# MESSAGES
# ─────────────────────────────────────────────

async def save_message(session_id: str, role: str, content: str) -> dict:
    msg = {
        "id": str(uuid4()),
        "session_id": session_id,
        "role": role,
        "content": content,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    if not _available:
        _mem_messages.setdefault(session_id, []).append(msg)
        return msg
    try:
        result = (
            _client.table("messages")
            .insert(msg)
            .execute()
        )
        return result.data[0] if result.data else msg
    except Exception as exc:
        logger.warning(f"save_message failed (using in-memory): {exc}")
        _mem_messages.setdefault(session_id, []).append(msg)
        return msg


async def get_messages(session_id: str, limit: int = 20) -> list[dict]:
    """Returns the last N messages for a session, ordered oldest-first."""
    if not _available:
        msgs = _mem_messages.get(session_id, [])
        return msgs[-limit:]
    try:
        result = (
            _client.table("messages")
            .select("*")
            .eq("session_id", session_id)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return list(reversed(result.data or []))
    except Exception as exc:
        logger.warning(f"get_messages failed (using in-memory): {exc}")
        msgs = _mem_messages.get(session_id, [])
        return msgs[-limit:]


# ─────────────────────────────────────────────
# PLANS
# ─────────────────────────────────────────────

async def save_plan(session_id: str, plan_data: dict) -> dict:
    payload = {
        "id": str(uuid4()),
        "session_id": session_id,
        "tier1": plan_data.get("tier1", []),
        "tier2": plan_data.get("tier2", []),
        "tier3": plan_data.get("tier3", []),
        "daily_breakdown": plan_data.get("daily_breakdown", []),
        "red_flags": plan_data.get("red_flags", []),
        "mock_question": plan_data.get("mock_question", ""),
    }

    if not _available:
        _mem_plans[session_id] = payload
        return payload
    try:
        result = _client.table("plans").insert(payload).execute()
        return result.data[0] if result.data else payload
    except Exception as exc:
        logger.warning(f"save_plan failed (using in-memory): {exc}")
        _mem_plans[session_id] = payload
        return payload


async def get_plan(session_id: str) -> Optional[dict]:
    if not _available:
        return _mem_plans.get(session_id)
    try:
        result = (
            _client.table("plans")
            .select("*")
            .eq("session_id", session_id)
            .order("created_at", desc=True)
            .limit(1)
            .maybe_single()
            .execute()
        )
        return result.data
    except Exception as exc:
        logger.warning(f"get_plan failed: {exc}")
        return _mem_plans.get(session_id)
