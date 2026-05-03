import { createClient } from "@/lib/supabase";

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";

/**
 * Retrieves the current user's JWT from the Supabase session.
 * Returns empty string if not authenticated or running on the server.
 */
async function getAuthToken(): Promise<string> {
  if (typeof window === "undefined") return "";
  try {
    const supabase = createClient();
    const { data: { session } } = await supabase.auth.getSession();
    return session?.access_token ?? "";
  } catch {
    return "";
  }
}

async function authHeaders(): Promise<Record<string, string>> {
  const token = await getAuthToken();
  return token
    ? { Authorization: `Bearer ${token}`, "Content-Type": "application/json" }
    : { "Content-Type": "application/json" };
}

// ─────────────────────────────────────────────
// Chat
// ─────────────────────────────────────────────

export interface ChatChunk {
  type: "chunk" | "done" | "error" | "metadata";
  text?: string;
  session_id?: string;
  error?: string;
}

/**
 * Streams a chat message via SSE.
 * Calls onChunk for each text chunk, onSessionId when session is established,
 * onDone on completion, and onError on failure.
 */
export async function streamChat(params: {
  message: string;
  sessionId?: string;
  onboardingContext?: string;
  onChunk: (text: string) => void;
  onSessionId?: (id: string) => void;
  onDone: () => void;
  onError: (err: string) => void;
}): Promise<void> {
  const { message, sessionId, onboardingContext, onChunk, onSessionId, onDone, onError } = params;

  let response: Response;
  try {
    response = await fetch(`${BACKEND_URL}/chat`, {
      method: "POST",
      headers: await authHeaders(),
      body: JSON.stringify({
        message,
        session_id: sessionId || null,
        onboarding_context: onboardingContext || null,
      }),
    });
  } catch {
    onError("Cannot reach the server. Make sure the backend is running on port 8000.");
    return;
  }

  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    onError(data.error || `Request failed: ${response.status}`);
    return;
  }

  const reader = response.body?.getReader();
  if (!reader) {
    onError("No response stream available.");
    return;
  }

  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n\n");
      buffer = lines.pop() || "";

      for (const line of lines) {
        if (!line.trim() || !line.startsWith("data: ")) continue;
        try {
          const chunk: ChatChunk = JSON.parse(line.slice(6));
          if (chunk.type === "chunk" && chunk.text) {
            onChunk(chunk.text);
          } else if (chunk.type === "done") {
            onDone();
          } else if (chunk.type === "error") {
            onError(chunk.error || "Unknown error");
          } else if (chunk.type === "metadata" && chunk.session_id) {
            onSessionId?.(chunk.session_id);
          }
        } catch {
          // Malformed SSE line — skip
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
}

// ─────────────────────────────────────────────
// Plan Generation
// ─────────────────────────────────────────────

export interface OnboardingAnswers {
  company?: string;
  role?: string;
  days_left?: number; // defaults to 30 on backend if omitted
  round?: string;
  level?: string;
  prepared?: string;
  skipped?: string;
  mode?: "interview_prep" | "upskill" | "shortlist";
}

export async function streamPlan(params: {
  onboarding: OnboardingAnswers;
  sessionId?: string;
  onChunk: (text: string) => void;
  onSessionId?: (id: string) => void;
  onDone: () => void;
  onError: (err: string) => void;
}): Promise<void> {
  const { onboarding, sessionId, onChunk, onSessionId, onDone, onError } = params;

  let response: Response;
  try {
    response = await fetch(`${BACKEND_URL}/plan`, {
      method: "POST",
      headers: await authHeaders(),
      body: JSON.stringify({ onboarding, session_id: sessionId || null }),
    });
  } catch {
    onError("Cannot reach the server. Make sure the backend is running on port 8000.");
    return;
  }

  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    onError(data.error || `Request failed: ${response.status}`);
    return;
  }

  const reader = response.body?.getReader();
  if (!reader) {
    onError("No response stream available.");
    return;
  }

  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n\n");
      buffer = lines.pop() || "";

      for (const line of lines) {
        if (!line.trim() || !line.startsWith("data: ")) continue;
        try {
          const chunk: ChatChunk = JSON.parse(line.slice(6));
          if (chunk.type === "chunk" && chunk.text) {
            onChunk(chunk.text);
          } else if (chunk.type === "done") {
            onDone();
          } else if (chunk.type === "error") {
            onError(chunk.error || "Unknown error");
          } else if (chunk.type === "metadata" && chunk.session_id) {
            onSessionId?.(chunk.session_id);
          }
        } catch {
          // skip
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
}

// ─────────────────────────────────────────────
// Mock Interview
// ─────────────────────────────────────────────

export async function streamMockQuestion(params: {
  sessionId: string;
  questionIndex: number;
  onChunk: (text: string) => void;
  onDone: () => void;
  onError: (err: string) => void;
}): Promise<void> {
  const { sessionId, questionIndex, onChunk, onDone, onError } = params;

  const response = await fetch(`${BACKEND_URL}/mock/question`, {
    method: "POST",
    headers: await authHeaders(),
    body: JSON.stringify({ session_id: sessionId, question_index: questionIndex }),
  });

  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    onError(data.error || `Request failed: ${response.status}`);
    return;
  }

  const reader = response.body?.getReader();
  if (!reader) {
    onError("No response stream.");
    return;
  }

  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n\n");
      buffer = lines.pop() || "";

      for (const line of lines) {
        if (!line.trim() || !line.startsWith("data: ")) continue;
        try {
          const chunk: ChatChunk = JSON.parse(line.slice(6));
          if (chunk.type === "chunk" && chunk.text) onChunk(chunk.text);
          else if (chunk.type === "done") onDone();
          else if (chunk.type === "error") onError(chunk.error || "Error");
        } catch {
          // skip
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
}

export interface MockScoreResult {
  question: string;
  answer: string;
  clarity: number;
  correctness: number;
  depth: number;
  overall: number;
  feedback: string;
  missing: string[];
  next_question?: string;
}

export async function scoreMockAnswer(params: {
  sessionId: string;
  question: string;
  answer: string;
  questionIndex: number;
}): Promise<MockScoreResult> {
  const { sessionId, question, answer, questionIndex } = params;

  const response = await fetch(`${BACKEND_URL}/mock/score`, {
    method: "POST",
    headers: await authHeaders(),
    body: JSON.stringify({
      session_id: sessionId,
      question,
      answer,
      question_index: questionIndex,
    }),
  });

  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.error || `Scoring failed: ${response.status}`);
  }

  return response.json();
}

// ─────────────────────────────────────────────
// Session
// ─────────────────────────────────────────────

export async function getSession(sessionId: string) {
  const response = await fetch(`${BACKEND_URL}/chat/session/${sessionId}`, {
    headers: await authHeaders(),
  });
  if (!response.ok) throw new Error("Session not found");
  return response.json();
}

export async function listSessions() {
  const response = await fetch(`${BACKEND_URL}/chat/sessions`, {
    headers: await authHeaders(),
  });
  if (!response.ok) throw new Error("Failed to fetch sessions");
  return response.json();
}
