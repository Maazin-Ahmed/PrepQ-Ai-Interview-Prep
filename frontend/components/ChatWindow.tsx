"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { streamChat } from "@/lib/api";
import {
  loadPlan,
  loadMessages,
  saveMessages,
  loadContext,
  buildContextString,
  touchSession,
  type StoredMessage,
} from "@/lib/storage";

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: Date;
  isStreaming?: boolean;
}

interface ChatWindowProps {
  sessionId: string | null;
}

function MessageBubble({ message }: { message: Message }) {
  const isUser = message.role === "user";
  const time = message.timestamp.toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  });

  return (
    <div
      className={`flex gap-4 animate-slide-up ${isUser ? "flex-row-reverse" : "flex-row"}`}
    >
      {/* Avatar */}
      <div
        className={`flex-shrink-0 w-7 h-7 rounded-sm flex items-center justify-center font-mono text-2xs font-semibold ${
          isUser
            ? "bg-surface-3 text-text-secondary"
            : "bg-accent-glow border border-accent/20 text-accent"
        }`}
      >
        {isUser ? "U" : "P"}
      </div>

      {/* Bubble */}
      <div className={`max-w-[75%] group ${isUser ? "items-end" : "items-start"} flex flex-col`}>
        <div
          className={`px-4 py-3 rounded-sm text-sm leading-relaxed ${
            isUser
              ? "bg-surface-2 text-text-primary border border-border"
              : "bg-transparent text-text-primary"
          }`}
        >
          {isUser ? (
            <span>{message.content}</span>
          ) : (
            <div
              className="prose-prepq"
              dangerouslySetInnerHTML={{ __html: formatMarkdown(message.content) }}
            />
          )}
          {message.isStreaming && (
            <span className="inline-block w-[2px] h-[1em] bg-accent ml-[2px] animate-cursor-blink align-middle" />
          )}
        </div>
        <span className="font-mono text-2xs text-text-muted mt-1 opacity-0 group-hover:opacity-100 transition-opacity">
          {time}
        </span>
      </div>
    </div>
  );
}

/** Minimal markdown → HTML converter */
function formatMarkdown(text: string): string {
  let html = text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");

  // Headings
  html = html
    .replace(/^### (.+)$/gm, "<h3>$1</h3>")
    .replace(/^## (.+)$/gm, "<h2>$1</h2>")
    .replace(/^# (.+)$/gm, "<h1>$1</h1>");

  // Horizontal rule
  html = html.replace(/^---$/gm, "<hr>");

  // Bold, italic, code
  html = html
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/\*(.+?)\*/g, "<em>$1</em>")
    .replace(/`([^`]+)`/g, "<code>$1</code>");

  // Numbered lists — group consecutive "N. item" lines
  html = html.replace(
    /((?:^\d+\.[ \t]+.+(?:\n|$))+)/gm,
    (block) => {
      const items = block
        .trim()
        .split("\n")
        .map((line) => `<li>${line.replace(/^\d+\.[ \t]+/, "")}</li>`)
        .join("");
      return `<ol>${items}</ol>\n`;
    }
  );

  // Unordered lists — group consecutive "- item" lines
  html = html.replace(
    /((?:^- .+(?:\n|$))+)/gm,
    (block) => {
      const items = block
        .trim()
        .split("\n")
        .map((line) => `<li>${line.replace(/^- /, "")}</li>`)
        .join("");
      return `<ul>${items}</ul>\n`;
    }
  );

  // Paragraphs
  html = html
    .replace(/\n{2,}/g, "</p><p>")
    .replace(/\n/g, "<br>")
    .replace(/^(?!<[houlpbi])(.+)$/gm, (line) =>
      line.startsWith("<") ? line : `<p>${line}</p>`
    );

  return html;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

let _counter = 0;
function uid() {
  _counter += 1;
  return String(_counter);
}

function storedToMessage(s: StoredMessage): Message {
  return { ...s, timestamp: new Date(s.timestamp) };
}

function messageToStored(m: Message): StoredMessage {
  return { id: m.id, role: m.role, content: m.content, timestamp: m.timestamp.toISOString() };
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function ChatWindow({ sessionId: initialSessionId }: ChatWindowProps) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [sessionId, setSessionId] = useState<string | null>(initialSessionId);
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hydrated, setHydrated] = useState(false);

  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // ── Hydrate from localStorage on mount ──────────────────────────────────────
  useEffect(() => {
    if (!initialSessionId) { setHydrated(true); return; }

    const stored = loadMessages(initialSessionId);
    const plan = loadPlan(initialSessionId);

    let initial: Message[] = [];

    // If a plan exists and no stored messages yet, inject it as first assistant message
    if (plan && stored.length === 0) {
      initial = [{
        id: uid(),
        role: "assistant",
        content: plan,
        timestamp: new Date(),
      }];
    } else if (stored.length > 0) {
      initial = stored.map(storedToMessage);
      // If plan exists but isn't already the first message, prepend it
      if (plan && initial[0]?.content !== plan) {
        initial = [
          { id: uid(), role: "assistant", content: plan, timestamp: new Date() },
          ...initial,
        ];
      }
    }

    setMessages(initial);
    setHydrated(true);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialSessionId]);

  // Persist messages whenever they change (skip during streaming to avoid churn)
  useEffect(() => {
    if (!hydrated || !sessionId || isStreaming) return;
    // Don't persist the "plan" message (first assistant msg if it equals stored plan)
    // — it's always re-injected on load from savePlan, so just persist everything
    const toStore = messages
      .filter((m) => !m.isStreaming)
      .map(messageToStored);
    saveMessages(sessionId, toStore);
  }, [messages, sessionId, hydrated, isStreaming]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // ── Send ──────────────────────────────────────────────────────────────────────
  const sendMessage = useCallback(async () => {
    const text = input.trim();
    if (!text || isStreaming) return;

    setError(null);
    setInput("");

    const userMsg: Message = {
      id: uid(),
      role: "user",
      content: text,
      timestamp: new Date(),
    };

    const assistantId = uid();
    const assistantMsg: Message = {
      id: assistantId,
      role: "assistant",
      content: "",
      timestamp: new Date(),
      isStreaming: true,
    };

    setMessages((prev) => [...prev, userMsg, assistantMsg]);
    setIsStreaming(true);

    // Load onboarding context to send with this request
    const ctx = sessionId ? loadContext(sessionId) : null;
    const onboardingContext = ctx ? buildContextString(ctx) : undefined;

    await streamChat({
      message: text,
      sessionId: sessionId || undefined,
      onboardingContext,
      onChunk: (chunk) => {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId ? { ...m, content: m.content + chunk } : m
          )
        );
      },
      onSessionId: (sid) => {
        setSessionId(sid);
      },
      onDone: () => {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId ? { ...m, isStreaming: false } : m
          )
        );
        setIsStreaming(false);
        if (sessionId) touchSession(sessionId);
        inputRef.current?.focus();
      },
      onError: (err) => {
        setError(err);
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId
              ? { ...m, content: "Something went wrong. Please try again.", isStreaming: false }
              : m
          )
        );
        setIsStreaming(false);
      },
    });
  }, [input, isStreaming, sessionId]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value);
    e.target.style.height = "auto";
    e.target.style.height = `${Math.min(e.target.scrollHeight, 140)}px`;
  };

  return (
    <div className="flex flex-col h-full max-w-4xl mx-auto w-full">
      {/* Messages area */}
      <div className="flex-1 overflow-y-auto px-6 py-6 space-y-6">
        {hydrated && messages.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full gap-4 text-center py-20">
            <div className="font-mono text-accent text-sm uppercase tracking-widest">
              PrepQ Agent
            </div>
            <p className="text-text-muted text-sm max-w-xs">
              Your prep strategist is ready. Start the conversation — ask about your interview, or let PrepQ guide you.
            </p>
          </div>
        )}
        {messages.map((msg) => (
          <MessageBubble key={msg.id} message={msg} />
        ))}
        {error && (
          <div className="text-danger text-xs font-mono px-4 py-2 bg-danger/5 border border-danger/20 rounded-sm">
            {error}
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input area */}
      <div className="border-t border-border px-6 py-4 flex-shrink-0">
        <div className="flex items-end gap-3 bg-surface-1 border border-border rounded-sm px-4 py-3 focus-within:border-border-bright transition-colors">
          <textarea
            id="chat-input"
            ref={inputRef}
            value={input}
            onChange={handleInputChange}
            onKeyDown={handleKeyDown}
            placeholder="Type a message… (Enter to send, Shift+Enter for newline)"
            disabled={isStreaming}
            rows={1}
            className="flex-1 bg-transparent text-text-primary text-sm placeholder:text-text-muted outline-none font-sans resize-none min-h-[24px] max-h-[140px] leading-relaxed disabled:opacity-50"
            style={{ height: "24px" }}
          />
          <button
            id="send-button"
            onClick={sendMessage}
            disabled={!input.trim() || isStreaming}
            className="flex-shrink-0 w-8 h-8 flex items-center justify-center bg-accent hover:bg-accent-dim disabled:opacity-30 disabled:cursor-not-allowed transition-colors rounded-sm"
            aria-label="Send message"
          >
            {isStreaming ? (
              <span className="w-3 h-3 rounded-full border-2 border-surface-0 border-t-transparent animate-spin" />
            ) : (
              <svg
                width="14"
                height="14"
                viewBox="0 0 14 14"
                fill="none"
                className="text-surface-0"
              >
                <path
                  d="M1 7h12M7 1l6 6-6 6"
                  stroke="currentColor"
                  strokeWidth="1.5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            )}
          </button>
        </div>
        <p className="font-mono text-2xs text-text-muted mt-2 text-center">
          PrepQ uses real interview data from Glassdoor, AmbitionBox, and LeetCode discuss.
        </p>
      </div>
    </div>
  );
}
