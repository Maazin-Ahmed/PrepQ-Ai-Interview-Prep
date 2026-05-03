/**
 * PrepQ localStorage helpers
 * All keys are scoped to a session ID so multiple sessions never collide.
 */

export interface OnboardingContext {
  mode: "interview" | "upskill" | "shortlist";
  company?: string;
  role?: string;
  days_left?: number;
  round?: string;
  level?: string;
  target_role?: string;
  current_level?: string;
  target_roles?: string;
  application_stats?: string;
  resume_summary?: string;
}

export interface StoredMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: string; // ISO string (Date is not JSON-serialisable)
}

// ── Session record (for sidebar list) ────────────────────────────────────────

export interface SessionRecord {
  id: string;
  title: string;            // auto-generated e.g. "Amazon SDE-1 · 7 days"
  mode: "interview" | "upskill" | "shortlist";
  context: OnboardingContext;
  created_at: string;       // ISO
  last_active: string;      // ISO — updated on every message
}

// ── Keys ─────────────────────────────────────────────────────────────────────

const PLAN_KEY = (sid: string) => `prepq:plan:${sid}`;
const MESSAGES_KEY = (sid: string) => `prepq:messages:${sid}`;
const CONTEXT_KEY = (sid: string) => `prepq:context:${sid}`;
const SESSION_LIST_KEY = "prepq:sessions";

/** Map session → a stable key so we can look up context without a session ID */
const PENDING_CONTEXT_KEY = "prepq:pending_context";
const PENDING_PLAN_KEY = "prepq:pending_plan";

const MAX_SESSIONS = 20;

// ── Session list ──────────────────────────────────────────────────────────────

export function loadSessionList(): SessionRecord[] {
  try {
    const raw = localStorage.getItem(SESSION_LIST_KEY);
    return raw ? (JSON.parse(raw) as SessionRecord[]) : [];
  } catch {
    return [];
  }
}

export function saveSessionList(sessions: SessionRecord[]): void {
  try {
    localStorage.setItem(SESSION_LIST_KEY, JSON.stringify(sessions));
  } catch {}
}

export function upsertSession(record: SessionRecord): void {
  try {
    const list = loadSessionList();
    const idx = list.findIndex((s) => s.id === record.id);
    if (idx !== -1) {
      list[idx] = record;
    } else {
      list.unshift(record); // newest first
      // Enforce max — remove oldest entries + their data
      while (list.length > MAX_SESSIONS) {
        const removed = list.pop();
        if (removed) deleteSessionData(removed.id);
      }
    }
    saveSessionList(list);
  } catch {}
}

export function touchSession(sessionId: string): void {
  try {
    const list = loadSessionList();
    const idx = list.findIndex((s) => s.id === sessionId);
    if (idx !== -1) {
      list[idx].last_active = new Date().toISOString();
      // Move to front
      const [rec] = list.splice(idx, 1);
      list.unshift(rec);
      saveSessionList(list);
    }
  } catch {}
}

function deleteSessionData(sessionId: string): void {
  try {
    localStorage.removeItem(PLAN_KEY(sessionId));
    localStorage.removeItem(MESSAGES_KEY(sessionId));
    localStorage.removeItem(CONTEXT_KEY(sessionId));
  } catch {}
}

// ── Auto-title generator ──────────────────────────────────────────────────────

export function generateSessionTitle(ctx: OnboardingContext): string {
  if (ctx.mode === "interview") {
    const co = ctx.company || "Company";
    const ro = ctx.role || "Role";
    const days = ctx.days_left ? ` · ${ctx.days_left}d` : "";
    return `${co} ${ro}${days}`;
  }
  if (ctx.mode === "upskill") {
    return ctx.target_role ? `${ctx.target_role} · Upskill` : "Upskill";
  }
  if (ctx.mode === "shortlist") {
    return ctx.target_roles
      ? `Shortlist · ${ctx.target_roles.slice(0, 30)}`
      : "Shortlist Analysis";
  }
  return "Session";
}

// ── Plan ──────────────────────────────────────────────────────────────────────

export function savePlan(sessionId: string, planText: string): void {
  try {
    localStorage.setItem(PLAN_KEY(sessionId), planText);
  } catch {
    // Storage quota exceeded or private-mode restriction — silently ignore
  }
}

export function loadPlan(sessionId: string): string | null {
  try {
    return localStorage.getItem(PLAN_KEY(sessionId));
  } catch {
    return null;
  }
}

/** Save the plan before session ID is known (during streaming). */
export function savePendingPlan(planText: string): void {
  try {
    localStorage.setItem(PENDING_PLAN_KEY, planText);
  } catch {}
}

export function loadPendingPlan(): string | null {
  try {
    return localStorage.getItem(PENDING_PLAN_KEY);
  } catch {
    return null;
  }
}

export function clearPendingPlan(): void {
  try {
    localStorage.removeItem(PENDING_PLAN_KEY);
  } catch {}
}

// ── Onboarding context ────────────────────────────────────────────────────────

export function saveContext(sessionId: string, ctx: OnboardingContext): void {
  try {
    localStorage.setItem(CONTEXT_KEY(sessionId), JSON.stringify(ctx));
  } catch {}
}

export function loadContext(sessionId: string): OnboardingContext | null {
  try {
    const raw = localStorage.getItem(CONTEXT_KEY(sessionId));
    return raw ? (JSON.parse(raw) as OnboardingContext) : null;
  } catch {
    return null;
  }
}

/** Save context before session ID is known. */
export function savePendingContext(ctx: OnboardingContext): void {
  try {
    localStorage.setItem(PENDING_CONTEXT_KEY, JSON.stringify(ctx));
  } catch {}
}

export function loadPendingContext(): OnboardingContext | null {
  try {
    const raw = localStorage.getItem(PENDING_CONTEXT_KEY);
    return raw ? (JSON.parse(raw) as OnboardingContext) : null;
  } catch {
    return null;
  }
}

export function clearPendingContext(): void {
  try {
    localStorage.removeItem(PENDING_CONTEXT_KEY);
  } catch {}
}

// ── Message history ───────────────────────────────────────────────────────────

export function saveMessages(sessionId: string, messages: StoredMessage[]): void {
  try {
    localStorage.setItem(MESSAGES_KEY(sessionId), JSON.stringify(messages));
  } catch {}
}

export function loadMessages(sessionId: string): StoredMessage[] {
  try {
    const raw = localStorage.getItem(MESSAGES_KEY(sessionId));
    return raw ? (JSON.parse(raw) as StoredMessage[]) : [];
  } catch {
    return [];
  }
}

// ── Context → natural language string for the backend ────────────────────────

export function buildContextString(ctx: OnboardingContext): string {
  if (ctx.mode === "interview") {
    const parts: string[] = [];
    if (ctx.company && ctx.role) {
      parts.push(`User is preparing for ${ctx.company} — ${ctx.role}.`);
    }
    if (ctx.days_left) parts.push(`${ctx.days_left} days left until the interview.`);
    if (ctx.round) parts.push(`Round: ${ctx.round.replace(/_/g, " ")}.`);
    if (ctx.level) parts.push(`Confidence level: ${ctx.level.replace(/_/g, " ")}.`);
    return parts.join(" ");
  }

  if (ctx.mode === "upskill") {
    const parts: string[] = [];
    if (ctx.target_role) parts.push(`User wants to upskill for: ${ctx.target_role}.`);
    if (ctx.current_level) parts.push(`Current level: ${ctx.current_level.replace(/_/g, " ")}.`);
    return parts.join(" ");
  }

  if (ctx.mode === "shortlist") {
    const parts: string[] = [];
    if (ctx.target_roles) parts.push(`Target roles: ${ctx.target_roles}.`);
    if (ctx.application_stats) parts.push(`Application stats: ${ctx.application_stats}.`);
    if (ctx.resume_summary) parts.push(`Resume summary: ${ctx.resume_summary}.`);
    return parts.join(" ");
  }

  return "";
}
