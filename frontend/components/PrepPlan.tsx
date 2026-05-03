"use client";

import { useEffect, useState } from "react";
import { getSession } from "@/lib/api";

interface PrepPlanProps {
  sessionId: string;
}

interface TierItem {
  topic: string;
  reason: string;
}

interface DailyTask {
  day: number;
  focus: string;
  tasks: string[];
}

interface PlanData {
  tier1: TierItem[];
  tier2: TierItem[];
  tier3: TierItem[];
  daily_breakdown: DailyTask[];
  red_flags: string[];
  mock_question: string;
}

function TierSection({
  tier,
  items,
  label,
  badge,
}: {
  tier: 1 | 2 | 3;
  items: TierItem[];
  label: string;
  badge: string;
}) {
  const [open, setOpen] = useState(tier === 1);

  const badgeClass = tier === 1 ? "tier-1-badge" : tier === 2 ? "tier-2-badge" : "tier-3-badge";
  const count = items.length;

  return (
    <div className="border border-border rounded-sm overflow-hidden">
      <button
        id={`tier-${tier}-toggle`}
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center justify-between px-5 py-4 hover:bg-surface-1 transition-colors focus-ring"
      >
        <div className="flex items-center gap-3">
          <span className={`font-mono text-2xs px-2 py-0.5 rounded-sm ${badgeClass}`}>
            {badge}
          </span>
          <span className="font-semibold text-text-primary text-sm">{label}</span>
          <span className="font-mono text-2xs text-text-muted">{count} topics</span>
        </div>
        <svg
          width="12"
          height="12"
          viewBox="0 0 12 12"
          fill="none"
          className={`text-text-muted transition-transform ${open ? "rotate-180" : ""}`}
        >
          <path d="M2 4l4 4 4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>

      {open && (
        <div className="border-t border-border divide-y divide-border">
          {items.length === 0 ? (
            <div className="px-5 py-4 text-text-muted text-sm">No items in this tier.</div>
          ) : (
            items.map((item, i) => (
              <div key={i} className="px-5 py-4 flex items-start gap-4 hover:bg-surface-1 transition-colors">
                <span className="font-mono text-2xs text-text-muted mt-0.5 flex-shrink-0">
                  {String(i + 1).padStart(2, "0")}
                </span>
                <div>
                  <div className="text-text-primary text-sm font-medium mb-1">{item.topic}</div>
                  <div className="text-text-secondary text-xs leading-relaxed">{item.reason}</div>
                </div>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}

export default function PrepPlan({ sessionId }: PrepPlanProps) {
  const [plan, setPlan] = useState<PlanData | null>(null);
  const [session, setSession] = useState<Record<string, string> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getSession(sessionId)
      .then(({ session: s, plan: p }) => {
        setSession(s);
        setPlan(p);
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message);
        setLoading(false);
      });
  }, [sessionId]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <span className="font-mono text-text-muted text-sm animate-pulse">Loading plan…</span>
      </div>
    );
  }

  if (error || !plan) {
    return (
      <div className="flex flex-col items-center justify-center py-20 gap-4">
        <p className="font-mono text-text-muted text-sm">
          {error || "No plan found for this session."}
        </p>
        <p className="text-text-muted text-xs">
          Complete the onboarding flow to generate a plan.
        </p>
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto px-6 py-8 space-y-8">
      {/* Header */}
      {session && (
        <div className="flex flex-wrap items-center gap-4 pb-6 border-b border-border">
          {[
            { label: "Company", value: session.company },
            { label: "Role", value: session.role },
            { label: "Days Left", value: session.days_left },
            { label: "Round", value: session.round?.replace("_", " ").toUpperCase() },
            { label: "Level", value: session.level?.replace("_", " ") },
          ]
            .filter((f) => f.value)
            .map((f) => (
              <div key={f.label} className="flex flex-col gap-0.5">
                <span className="font-mono text-2xs text-text-muted uppercase tracking-widest">
                  {f.label}
                </span>
                <span className="font-mono text-sm text-text-primary font-medium">{f.value}</span>
              </div>
            ))}
        </div>
      )}

      {/* Tiers */}
      <div className="space-y-3">
        <TierSection tier={1} items={plan.tier1 || []} label="Must Know" badge="TIER 1 — CRITICAL" />
        <TierSection tier={2} items={plan.tier2 || []} label="High Priority" badge="TIER 2 — HIGH PRIORITY" />
        <TierSection tier={3} items={plan.tier3 || []} label="Good to Have" badge="TIER 3 — GOOD TO HAVE" />
      </div>

      {/* Red Flags */}
      {plan.red_flags?.length > 0 && (
        <div className="border border-danger/20 bg-danger/5 rounded-sm p-5">
          <div className="flex items-center gap-2 mb-4">
            <span className="text-danger text-xs">⚠</span>
            <span className="font-mono text-xs text-danger uppercase tracking-widest font-semibold">
              Red Flags — What Most Candidates Miss
            </span>
          </div>
          <ul className="space-y-2">
            {plan.red_flags.map((flag, i) => (
              <li key={i} className="flex items-start gap-3">
                <span className="font-mono text-2xs text-danger/60 mt-0.5 flex-shrink-0">
                  {String(i + 1).padStart(2, "0")}
                </span>
                <span className="text-sm text-text-secondary leading-relaxed">{flag}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Daily Breakdown */}
      {plan.daily_breakdown?.length > 0 && (
        <div>
          <div className="font-mono text-2xs text-text-muted uppercase tracking-widest mb-4">
            Daily Schedule
          </div>
          <div className="border border-border rounded-sm overflow-hidden">
            <div className="divide-y divide-border">
              {plan.daily_breakdown.map((day) => (
                <div key={day.day} className="px-5 py-4 flex items-start gap-5 hover:bg-surface-1 transition-colors">
                  <div className="flex-shrink-0 w-12 text-center">
                    <span className="font-mono text-xl font-bold text-accent">
                      {String(day.day).padStart(2, "0")}
                    </span>
                    <div className="font-mono text-2xs text-text-muted uppercase">Day</div>
                  </div>
                  <div className="flex-1">
                    <div className="font-medium text-text-primary text-sm mb-2">{day.focus}</div>
                    {day.tasks?.length > 0 && (
                      <ul className="space-y-1">
                        {day.tasks.map((task, ti) => (
                          <li key={ti} className="flex items-start gap-2 text-xs text-text-secondary">
                            <span className="text-accent mt-0.5 flex-shrink-0">›</span>
                            {task}
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Mock Question */}
      {plan.mock_question && (
        <div className="border border-border-bright bg-surface-1 rounded-sm p-5">
          <div className="font-mono text-2xs text-text-muted uppercase tracking-widest mb-4">
            Mock Question — Company Style
          </div>
          <p className="font-mono text-sm text-text-primary leading-relaxed">
            {plan.mock_question}
          </p>
          <a
            href={`/plan?session=${sessionId}#mock`}
            className="inline-flex items-center gap-2 mt-4 text-accent text-xs font-mono hover:underline"
          >
            → Attempt this in Mock Interview mode
          </a>
        </div>
      )}
    </div>
  );
}
