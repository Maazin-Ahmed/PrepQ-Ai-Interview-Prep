"use client";

import { useState, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import PrepPlan from "@/components/PrepPlan";
import MockInterview from "@/components/MockInterview";

function PlanContent() {
  const searchParams = useSearchParams();
  const sessionId = searchParams.get("session");
  const [activeTab, setActiveTab] = useState<"plan" | "mock">("plan");

  if (!sessionId) {
    return (
      <div className="min-h-screen bg-surface-0 flex items-center justify-center">
        <div className="text-center">
          <p className="font-mono text-text-muted text-sm mb-4">No session found.</p>
          <a href="/chat" className="text-accent font-mono text-sm hover:underline">
            → Start a new prep session
          </a>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-surface-0 flex flex-col">
      {/* Header */}
      <header className="border-b border-border px-6 py-4 flex items-center justify-between flex-shrink-0">
        <span className="font-mono text-accent font-semibold text-sm tracking-widest uppercase">
          PrepQ
        </span>
        <div className="flex items-center gap-1">
          <button
            id="tab-plan"
            onClick={() => setActiveTab("plan")}
            className={`font-mono text-xs px-4 py-2 transition-colors ${
              activeTab === "plan"
                ? "text-accent border-b-2 border-accent"
                : "text-text-muted hover:text-text-secondary"
            }`}
          >
            Prep Plan
          </button>
          <button
            id="tab-mock"
            onClick={() => setActiveTab("mock")}
            className={`font-mono text-xs px-4 py-2 transition-colors ${
              activeTab === "mock"
                ? "text-accent border-b-2 border-accent"
                : "text-text-muted hover:text-text-secondary"
            }`}
          >
            Mock Interview
          </button>
        </div>
        <span className="font-mono text-2xs text-text-muted">
          {sessionId.slice(0, 8)}…
        </span>
      </header>

      {/* Content */}
      <main className="flex-1 overflow-auto">
        {activeTab === "plan" ? (
          <PrepPlan sessionId={sessionId} />
        ) : (
          <MockInterview sessionId={sessionId} />
        )}
      </main>
    </div>
  );
}

export default function PlanPage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen bg-surface-0 flex items-center justify-center">
          <span className="font-mono text-text-muted text-sm animate-pulse">Loading…</span>
        </div>
      }
    >
      <PlanContent />
    </Suspense>
  );
}
