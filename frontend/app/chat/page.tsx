"use client";

import { useState, useCallback } from "react";
import OnboardingFlow from "@/components/OnboardingFlow";
import ChatWindow from "@/components/ChatWindow";
import Sidebar from "@/components/Sidebar";
import AuthGuard from "@/components/AuthGuard";
import { type SessionRecord, loadContext } from "@/lib/storage";

type AppView =
  | { kind: "onboarding" }
  | { kind: "chat"; sessionId: string };

function ChatApp({ user }: { user: import("@supabase/supabase-js").User }) {
  const [view, setView] = useState<AppView>({ kind: "onboarding" });
  const [sidebarOpen, setSidebarOpen] = useState(false);

  // Key used to force-remount ChatWindow when switching sessions
  const [chatKey, setChatKey] = useState(0);

  // ── Handlers ────────────────────────────────────────────────────────────────

  const handleOnboardingComplete = useCallback((sid: string) => {
    setView({ kind: "chat", sessionId: sid });
    setChatKey((k) => k + 1);
  }, []);

  const handleNewSession = useCallback(() => {
    setView({ kind: "onboarding" });
    setSidebarOpen(false);
  }, []);

  const handleSelectSession = useCallback((session: SessionRecord) => {
    setView({ kind: "chat", sessionId: session.id });
    setChatKey((k) => k + 1);
    setSidebarOpen(false);
  }, []);

  const currentSessionId = view.kind === "chat" ? view.sessionId : null;
  const onboardingDone = view.kind === "chat";

  // Derive a label for the top bar
  let topBarLabel = "Onboarding";
  if (view.kind === "chat" && typeof window !== "undefined") {
    const ctx = loadContext(view.sessionId);
    if (ctx?.mode === "interview" && ctx.company && ctx.role) {
      topBarLabel = `${ctx.company} · ${ctx.role}`;
    } else if (ctx?.mode === "upskill" && ctx.target_role) {
      topBarLabel = ctx.target_role;
    } else if (ctx?.mode === "shortlist") {
      topBarLabel = "Shortlist Analysis";
    } else {
      topBarLabel = "Prep Session";
    }
  }

  return (
    <div className="h-[100dvh] bg-surface-0 flex flex-col">
      {/* ── Top bar ──────────────────────────────────────────────────────── */}
      <header
        className="border-b border-border flex items-center justify-between flex-shrink-0"
        style={{ height: "52px", paddingLeft: "16px", paddingRight: "20px" }}
      >
        <div className="flex items-center gap-3">
          {/* Hamburger — mobile only */}
          <button
            id="sidebar-toggle"
            onClick={() => setSidebarOpen((o) => !o)}
            className="md:hidden flex flex-col gap-[5px] p-1 text-text-muted hover:text-text-secondary transition-colors"
            aria-label="Toggle sidebar"
          >
            <span className="block w-4 h-px bg-current" />
            <span className="block w-4 h-px bg-current" />
            <span className="block w-3 h-px bg-current" />
          </button>

          {/* Desktop wordmark (sidebar has its own logo) */}
          <span className="hidden md:block font-mono text-accent font-semibold text-xs tracking-widest uppercase">
            PrepQ
          </span>

          <span className="text-[#1f1f1f] text-xs">|</span>

          <span className="text-text-muted text-xs font-mono truncate max-w-[200px] sm:max-w-xs">
            {topBarLabel}
          </span>
        </div>

        {currentSessionId && (
          <span className="font-mono text-[10px] text-text-muted hidden sm:block">
            {currentSessionId.slice(0, 8)}…
          </span>
        )}
      </header>

      {/* ── Body: sidebar + main ─────────────────────────────────────────── */}
      <div className="flex flex-1 overflow-hidden">
        <Sidebar
          activeSessionId={currentSessionId}
          onNewSession={handleNewSession}
          onSelectSession={handleSelectSession}
          isOpen={sidebarOpen}
          onClose={() => setSidebarOpen(false)}
          user={user}
        />

        {/* Main content */}
        <main className="flex-1 flex flex-col overflow-hidden min-w-0">
          {!onboardingDone ? (
            <OnboardingFlow onComplete={handleOnboardingComplete} />
          ) : (
            <ChatWindow
              key={chatKey}
              sessionId={currentSessionId}
            />
          )}
        </main>
      </div>
    </div>
  );
}

export default function ChatPage() {
  return (
    <AuthGuard>
      {(user) => <ChatApp user={user} />}
    </AuthGuard>
  );
}
