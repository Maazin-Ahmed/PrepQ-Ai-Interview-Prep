"use client";

import { useState, useEffect } from "react";
import type { User } from "@supabase/supabase-js";
import { createClient } from "@/lib/supabase";
import {
  loadSessionList,
  type SessionRecord,
} from "@/lib/storage";

// ── Mode badge ────────────────────────────────────────────────────────────────

function ModeBadge({ mode }: { mode: SessionRecord["mode"] }) {
  if (mode === "interview") {
    return (
      <span className="inline-block font-mono text-[10px] uppercase tracking-widest text-accent opacity-70">
        Interview
      </span>
    );
  }
  if (mode === "upskill") {
    return (
      <span className="inline-block font-mono text-[10px] uppercase tracking-widest text-warning opacity-70">
        Upskill
      </span>
    );
  }
  return (
    <span className="inline-block font-mono text-[10px] uppercase tracking-widest text-danger opacity-70">
      Shortlist
    </span>
  );
}

// ── Relative time ─────────────────────────────────────────────────────────────

function relativeTime(iso: string): string {
  const now = Date.now();
  const then = new Date(iso).getTime();
  const diff = Math.floor((now - then) / 1000);

  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  if (diff < 7 * 86400) return `${Math.floor(diff / 86400)}d ago`;
  return new Date(iso).toLocaleDateString("en-IN", { day: "numeric", month: "short" });
}

// ── Session item ──────────────────────────────────────────────────────────────

function SessionItem({
  session,
  isActive,
  onClick,
}: {
  session: SessionRecord;
  isActive: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={`
        w-full text-left px-3 py-2.5 rounded-sm transition-all group
        ${isActive
          ? "bg-[#1a1a1a] border border-[#2a2a2a]"
          : "hover:bg-[#161616] border border-transparent"
        }
      `}
    >
      <div className="flex items-start justify-between gap-2 mb-0.5">
        <ModeBadge mode={session.mode} />
        <span className="font-mono text-[10px] text-[#3a3a3a] group-hover:text-[#4a4a4a] transition-colors flex-shrink-0">
          {relativeTime(session.last_active)}
        </span>
      </div>
      <div
        className={`text-xs leading-snug truncate transition-colors ${
          isActive ? "text-[#e0e0e0]" : "text-[#7a7a7a] group-hover:text-[#a0a0a0]"
        }`}
      >
        {session.title}
      </div>
    </button>
  );
}

// ── Sidebar ───────────────────────────────────────────────────────────────────

interface SidebarProps {
  activeSessionId: string | null;
  onNewSession: () => void;
  onSelectSession: (session: SessionRecord) => void;
  isOpen: boolean;
  onClose: () => void;
  user: User;
}

export default function Sidebar({
  activeSessionId,
  onNewSession,
  onSelectSession,
  isOpen,
  onClose,
  user,
}: SidebarProps) {
  const [sessions, setSessions] = useState<SessionRecord[]>([]);
  const [signingOut, setSigningOut] = useState(false);

  async function handleSignOut() {
    setSigningOut(true);
    const supabase = createClient();
    await supabase.auth.signOut();
    // AuthGuard will detect the session change and redirect to /login
  }

  // Reload session list whenever sidebar opens or active session changes
  useEffect(() => {
    setSessions(loadSessionList());
  }, [activeSessionId, isOpen]);

  return (
    <>
      {/* Mobile backdrop */}
      {isOpen && (
        <div
          className="fixed inset-0 z-20 bg-black/60 backdrop-blur-sm md:hidden"
          onClick={onClose}
        />
      )}

      {/* Sidebar panel */}
      <aside
        className={`
          fixed md:relative z-30 md:z-auto
          top-0 left-0 h-full md:h-auto
          w-[240px] flex-shrink-0
          flex flex-col
          bg-[#0d0d0d] border-r border-[#1f1f1f]
          transition-transform duration-200 ease-out
          ${isOpen ? "translate-x-0" : "-translate-x-full md:translate-x-0"}
        `}
      >
        {/* Logo / header */}
        <div className="flex items-center justify-between px-4 py-4 border-b border-[#1a1a1a] flex-shrink-0">
          <span className="font-mono text-accent font-semibold text-xs tracking-widest uppercase">
            PrepQ
          </span>
          {/* Mobile close */}
          <button
            onClick={onClose}
            className="md:hidden text-[#4a4a4a] hover:text-[#8a8a8a] transition-colors p-1"
            aria-label="Close sidebar"
          >
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
              <path d="M1 1l12 12M13 1L1 13" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
            </svg>
          </button>
        </div>

        {/* New session button */}
        <div className="px-3 pt-3 pb-2 flex-shrink-0">
          <button
            id="new-session-btn"
            onClick={() => { onNewSession(); onClose(); }}
            className="
              w-full flex items-center gap-2 px-3 py-2.5
              bg-transparent border border-[#262626] rounded-sm
              text-[#6a6a6a] hover:text-[#c0c0c0] hover:border-[#363636]
              transition-all text-xs font-mono group
            "
          >
            <svg
              width="12"
              height="12"
              viewBox="0 0 12 12"
              fill="none"
              className="flex-shrink-0 transition-transform group-hover:rotate-90 duration-200"
            >
              <path d="M6 1v10M1 6h10" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
            </svg>
            New session
          </button>
        </div>

        {/* Session list */}
        <div className="flex-1 overflow-y-auto px-2 pb-4">
          {sessions.length === 0 ? (
            <div className="px-3 py-6 text-center">
              <p className="font-mono text-[10px] text-[#2a2a2a] uppercase tracking-widest">
                No sessions yet
              </p>
            </div>
          ) : (
            <div className="space-y-0.5">
              {sessions.map((s) => (
                <SessionItem
                  key={s.id}
                  session={s}
                  isActive={s.id === activeSessionId}
                  onClick={() => { onSelectSession(s); onClose(); }}
                />
              ))}
            </div>
          )}
        </div>

        {/* User avatar + sign out */}
        <div className="px-3 py-3 border-t border-[#1a1a1a] flex-shrink-0">
          <div className="flex items-center gap-2">
            {/* Avatar */}
            {user.user_metadata?.avatar_url ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={user.user_metadata.avatar_url as string}
                alt="avatar"
                className="w-6 h-6 rounded-full flex-shrink-0 object-cover"
              />
            ) : (
              <div className="w-6 h-6 rounded-full bg-surface-3 flex items-center justify-center flex-shrink-0">
                <span className="font-mono text-[9px] text-text-secondary uppercase">
                  {(user.email ?? "?")[0]}
                </span>
              </div>
            )}

            {/* Email truncated */}
            <span className="flex-1 font-mono text-[10px] text-[#3a3a3a] truncate">
              {user.email}
            </span>

            {/* Sign out */}
            <button
              id="sign-out-btn"
              onClick={handleSignOut}
              disabled={signingOut}
              title="Sign out"
              className="flex-shrink-0 p-1 text-[#3a3a3a] hover:text-danger transition-colors disabled:opacity-40"
              aria-label="Sign out"
            >
              {signingOut ? (
                <span className="block w-3 h-3 rounded-full border border-current border-t-transparent animate-spin" />
              ) : (
                <svg width="13" height="13" viewBox="0 0 13 13" fill="none">
                  <path
                    d="M5 2H2a1 1 0 0 0-1 1v7a1 1 0 0 0 1 1h3M9 9.5l3-3-3-3M12 6.5H5"
                    stroke="currentColor"
                    strokeWidth="1.3"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
              )}
            </button>
          </div>
        </div>
      </aside>
    </>
  );
}
