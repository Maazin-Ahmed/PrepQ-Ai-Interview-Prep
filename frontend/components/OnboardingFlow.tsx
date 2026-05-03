"use client";

import { useState, useRef, useEffect } from "react";
import { streamPlan, streamChat } from "@/lib/api";
import {
  savePendingPlan,
  savePendingContext,
  saveContext,
  savePlan,
  loadPendingPlan,
  loadPendingContext,
  clearPendingPlan,
  clearPendingContext,
  upsertSession,
  generateSessionTitle,
  type OnboardingContext,
} from "@/lib/storage";

interface OnboardingFlowProps {
  onComplete: (sessionId: string) => void;
}

type AppMode = "interview" | "upskill" | "shortlist";
type GenState = "idle" | "generating" | "done" | "error";

/** Minimal markdown → HTML converter (shared with ChatWindow) */
function formatMarkdown(text: string): string {
  // Escape HTML first
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

  // Bold & italic
  html = html
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/\*(.+?)\*/g, "<em>$1</em>")
    .replace(/`([^`]+)`/g, "<code>$1</code>");

  // Numbered lists — group consecutive lines starting with "N."
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

  // Unordered lists — group consecutive lines starting with "-"
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

  // Paragraphs — wrap remaining non-tagged lines
  html = html
    .replace(/\n{2,}/g, "</p><p>")
    .replace(/\n/g, "<br>")
    .replace(/^(?!<[houlpbi])(.+)$/gm, (line) =>
      line.startsWith("<") ? line : `<p>${line}</p>`
    );

  return html;
}

// ─── Step definitions per mode ─────────────────────────────────────────────

const INTERVIEW_STEPS = [
  {
    field: "company",
    question: "What company are you preparing for?",
    hint: 'e.g. "TCS", "Infosys", "Google", "Wipro"',
    type: "text" as const,
  },
  {
    field: "role",
    question: "What role?",
    hint: 'e.g. "System Engineer", "SDE", "Data Analyst"',
    type: "text" as const,
  },
  {
    field: "days_left",
    question: "How many days until your interview?",
    hint: "Skip to default to 30 days",
    type: "number-optional" as const,
  },
  {
    field: "round",
    question: "Which round is this?",
    hint: "Select the one closest to what you're facing",
    type: "select" as const,
    options: [
      { value: "online_assessment", label: "Online Assessment (OA)" },
      { value: "technical", label: "Technical Interview" },
      { value: "hr", label: "HR / Behavioural" },
      { value: "case_study", label: "Case Study" },
      { value: "managerial", label: "Managerial" },
      { value: "system_design", label: "System Design" },
    ],
  },
  {
    field: "level",
    question: "How confident are you in the required skills?",
    hint: "Be honest — this shapes your plan priorities",
    type: "select" as const,
    options: [
      { value: "beginner", label: "Beginner — just getting started" },
      { value: "some_experience", label: "Some experience — gaps in knowledge" },
      { value: "confident", label: "Confident — need focused revision" },
    ],
  },
];

const UPSKILL_STEPS = [
  {
    field: "target_role",
    question: "What role or field are you targeting?",
    hint: 'e.g. "Backend Engineer", "Data Scientist", "Product Manager"',
    type: "text" as const,
  },
  {
    field: "current_level",
    question: "Where are you right now?",
    hint: "Be honest — this is the baseline for your roadmap",
    type: "select" as const,
    options: [
      { value: "complete_beginner", label: "Complete beginner — starting from scratch" },
      { value: "some_knowledge", label: "Some knowledge — built a few things" },
      { value: "working_professional", label: "Working professional — switching or levelling up" },
    ],
  },
];

const SHORTLIST_STEPS = [
  {
    field: "target_roles",
    question: "What roles are you applying for?",
    hint: 'e.g. "SDE at product startups", "Data Analyst at MNCs"',
    type: "text" as const,
  },
  {
    field: "application_stats",
    question: "How many applications sent, how many responses?",
    hint: 'e.g. "80 sent, 3 responses" — be exact, this tells a story',
    type: "text" as const,
  },
  {
    field: "resume_summary",
    question: "Share your current resume summary.",
    hint: "Skills, years of experience, education level, notable projects (1-3 sentences is fine)",
    type: "textarea" as const,
  },
];

// ─── Helper: get steps for current mode ────────────────────────────────────

function getSteps(mode: AppMode) {
  if (mode === "interview") return INTERVIEW_STEPS;
  if (mode === "upskill") return UPSKILL_STEPS;
  return SHORTLIST_STEPS;
}

// ─── Generating / Done views ─────────────────────────────────────────────────

function GeneratingView({
  mode,
  streamedText,
  genState,
  retryCount,
  onRetry,
  onStartChatting,
}: {
  mode: AppMode;
  streamedText: string;
  genState: GenState;
  retryCount: number;
  onRetry: () => void;
  onStartChatting: () => void;
}) {
  const streamingLabels: Record<AppMode, string> = {
    interview: "Building your PrepQ plan",
    upskill: "Building your upskill roadmap",
    shortlist: "Analysing why you're not getting shortlisted",
  };

  const doneLabels: Record<AppMode, string> = {
    interview: "Your PrepQ plan is ready",
    upskill: "Your upskill roadmap is ready",
    shortlist: "Your shortlist analysis is ready",
  };

  if (genState === "done") {
    return (
      <div className="flex-1 flex flex-col items-center px-6 py-12 overflow-y-auto">
        <div className="w-full max-w-2xl">
          <div className="flex items-center gap-3 mb-6">
            <span className="w-2 h-2 rounded-full bg-accent" />
            <span className="font-mono text-xs text-accent uppercase tracking-widest">
              {doneLabels[mode]}
            </span>
          </div>
          <div className="bg-surface-1 border border-border rounded-sm p-6 overflow-y-auto max-h-[60vh]">
            <div
              className="prose-prepq text-sm text-text-primary leading-relaxed"
              dangerouslySetInnerHTML={{ __html: formatMarkdown(streamedText) }}
            />
          </div>
          <div className="mt-6 flex justify-end">
            <button
              id="start-chatting-btn"
              onClick={onStartChatting}
              className="inline-flex items-center gap-2 bg-accent text-surface-0 font-semibold px-6 py-3 rounded-sm hover:bg-accent-dim transition-colors text-sm focus-ring"
            >
              Start chatting →
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 flex flex-col items-center justify-center px-6 py-12 overflow-y-auto">
      <div className="w-full max-w-2xl">
        {genState === "error" ? (
          <div className="space-y-4">
            <div className="flex items-center gap-3 mb-4">
              <span className="w-2 h-2 rounded-full bg-danger" />
              <span className="font-mono text-xs text-danger uppercase tracking-widest">
                {retryCount >= 3
                  ? "Server unreachable"
                  : "Connection failed — retrying"}
              </span>
            </div>
            <div className="bg-surface-1 border border-danger/20 rounded-sm p-5">
              <p className="font-mono text-sm text-text-secondary mb-1">
                {retryCount >= 3
                  ? "Cannot reach the backend. Make sure it's running:"
                  : "Could not connect to the PrepQ server."}
              </p>
              {retryCount >= 3 && (
                <code className="font-mono text-xs text-accent block mt-3">
                  cd backend && uvicorn main:app --reload --port 8000
                </code>
              )}
            </div>
            {retryCount < 3 && (
              <button
                id="retry-btn"
                onClick={onRetry}
                className="inline-flex items-center gap-2 bg-accent text-surface-0 font-semibold px-6 py-3 rounded-sm hover:bg-accent-dim transition-colors text-sm focus-ring"
              >
                Try again →
              </button>
            )}
          </div>
        ) : (
          <>
            <div className="flex items-center gap-3 mb-6">
              <span className="w-2 h-2 rounded-full bg-accent animate-pulse" />
              <span className="font-mono text-xs text-accent uppercase tracking-widest">
                {streamingLabels[mode]}
              </span>
            </div>
            <div className="bg-surface-1 border border-border rounded-sm p-6 min-h-[300px] overflow-y-auto max-h-[60vh]">
              <div
                className="prose-prepq text-sm text-text-primary leading-relaxed"
                dangerouslySetInnerHTML={{
                  __html:
                    streamedText
                      ? formatMarkdown(streamedText)
                      : "<span class='text-text-muted animate-pulse'>Thinking…</span>",
                }}
              />
              {streamedText && (
                <span className="inline-block w-[2px] h-[1em] bg-accent ml-[2px] animate-cursor-blink align-middle" />
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}

// ─── Main component ──────────────────────────────────────────────────────────

export default function OnboardingFlow({ onComplete }: OnboardingFlowProps) {
  const [mode, setMode] = useState<AppMode | null>(null);
  const [step, setStep] = useState(0);
  const [answers, setAnswers] = useState<Record<string, string | number>>({});
  const [inputValue, setInputValue] = useState("");
  const [genState, setGenState] = useState<GenState>("idle");
  const [streamedText, setStreamedText] = useState("");
  const [retryCount, setRetryCount] = useState(0);

  const inputRef = useRef<HTMLInputElement | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const capturedSid = useRef<string | null>(null);
  const pendingAnswers = useRef<Record<string, string | number>>({});

  useEffect(() => {
    if (genState === "idle" && mode !== null) {
      inputRef.current?.focus();
      textareaRef.current?.focus();
    }
  }, [step, genState, mode]);

  // ── Mode selection ────────────────────────────────────────────────────────

  if (mode === null) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center px-6 py-12 overflow-y-auto">
        <div className="w-full max-w-xl">
          <div className="mb-2">
            <span className="font-mono text-2xs text-accent uppercase tracking-widest">
              PrepQ — Where to start
            </span>
          </div>
          <h2 className="text-2xl font-semibold text-text-primary mb-2 leading-tight">
            What brings you here?
          </h2>
          <p className="text-text-muted text-sm mb-8">
            Pick one — PrepQ will adjust everything based on your goal.
          </p>

          <div className="space-y-3">
            <button
              id="mode-interview"
              onClick={() => { setMode("interview"); setStep(0); }}
              className="w-full text-left px-5 py-4 rounded-sm border border-border bg-surface-1 hover:border-border-bright hover:bg-surface-2 transition-all group focus-ring"
            >
              <div className="font-mono text-2xs text-accent uppercase tracking-widest mb-1">
                01
              </div>
              <div className="font-semibold text-text-primary text-sm mb-1">
                I have an interview coming up
              </div>
              <div className="text-text-muted text-xs">
                Get a hyper-specific prep plan for your company, role, and timeline
              </div>
            </button>

            <button
              id="mode-upskill"
              onClick={() => { setMode("upskill"); setStep(0); }}
              className="w-full text-left px-5 py-4 rounded-sm border border-border bg-surface-1 hover:border-border-bright hover:bg-surface-2 transition-all group focus-ring"
            >
              <div className="font-mono text-2xs text-accent uppercase tracking-widest mb-1">
                02
              </div>
              <div className="font-semibold text-text-primary text-sm mb-1">
                I want to upskill / get job-ready
              </div>
              <div className="text-text-muted text-xs">
                Build a focused roadmap to reach your target role — no interview date needed
              </div>
            </button>

            <button
              id="mode-shortlist"
              onClick={() => { setMode("shortlist"); setStep(0); }}
              className="w-full text-left px-5 py-4 rounded-sm border border-border bg-surface-1 hover:border-border-bright hover:bg-surface-2 transition-all group focus-ring"
            >
              <div className="font-mono text-2xs text-danger uppercase tracking-widest mb-1">
                03
              </div>
              <div className="font-semibold text-text-primary text-sm mb-1">
                Why am I not getting shortlisted?
              </div>
              <div className="text-text-muted text-xs">
                Brutally honest breakdown of exactly what&apos;s wrong — and a 60/90 day fix
              </div>
            </button>
          </div>
        </div>
      </div>
    );
  }

  // ── Generating / done / error view ───────────────────────────────────────

  if (genState !== "idle") {
    return (
      <GeneratingView
        mode={mode}
        streamedText={streamedText}
        genState={genState}
        retryCount={retryCount}
        onRetry={() => execute(pendingAnswers.current)}
        onStartChatting={() => {
          if (capturedSid.current && mode) {
            // Load the context that was saved during streaming
            const ctx = (() => {
              try {
                const raw = localStorage.getItem(`prepq:context:${capturedSid.current}`);
                return raw ? JSON.parse(raw) as OnboardingContext : null;
              } catch { return null; }
            })();
            if (ctx) {
              const now = new Date().toISOString();
              upsertSession({
                id: capturedSid.current,
                title: generateSessionTitle(ctx),
                mode: ctx.mode,
                context: ctx,
                created_at: now,
                last_active: now,
              });
            }
            onComplete(capturedSid.current);
          }
        }}
      />
    );
  }

  // ── Question flow ─────────────────────────────────────────────────────────

  const steps = getSteps(mode);
  const currentStep = steps[step];
  const totalSteps = steps.length;
  const progress = (step / totalSteps) * 100;

  // Build the final message for upskill / shortlist modes
  function buildChatMessage(ans: Record<string, string | number>): string {
    if (mode === "upskill") {
      return `I want to upskill and get job-ready.\nTarget role/field: ${ans.target_role}\nCurrent level: ${ans.current_level}\n\nPlease build me a focused upskilling roadmap — specific, no fluff.`;
    }
    if (mode === "shortlist") {
      return `I'm struggling to get shortlisted. Here's my situation:\n\nTarget roles: ${ans.target_roles}\nApplication stats: ${ans.application_stats}\nResume summary: ${ans.resume_summary}\n\nGive me a brutally honest shortlist analysis.`;
    }
    return "";
  }

  async function execute(finalAnswers: Record<string, string | number>) {
    pendingAnswers.current = finalAnswers;
    setGenState("generating");
    setStreamedText("");
    capturedSid.current = null;

    // Build and save context immediately (before session ID arrives)
    const ctx: OnboardingContext = mode === "interview"
      ? {
          mode: "interview",
          company: String(finalAnswers.company || ""),
          role: String(finalAnswers.role || ""),
          days_left: Number(finalAnswers.days_left) || 30,
          round: String(finalAnswers.round || ""),
          level: String(finalAnswers.level || ""),
        }
      : mode === "upskill"
      ? {
          mode: "upskill",
          target_role: String(finalAnswers.target_role || ""),
          current_level: String(finalAnswers.current_level || ""),
        }
      : {
          mode: "shortlist",
          target_roles: String(finalAnswers.target_roles || ""),
          application_stats: String(finalAnswers.application_stats || ""),
          resume_summary: String(finalAnswers.resume_summary || ""),
        };
    savePendingContext(ctx);

    // Track streamed text in a ref so onDone/onSessionId can read it
    const streamedRef = { current: "" };

    function handleSessionId(sid: string) {
      capturedSid.current = sid;
      // Migrate pending → session-scoped
      const plan = loadPendingPlan();
      if (plan) { savePlan(sid, plan); clearPendingPlan(); }
      const savedCtx = loadPendingContext();
      if (savedCtx) { saveContext(sid, savedCtx); clearPendingContext(); }
    }

    if (mode === "interview") {
      await streamPlan({
        onboarding: {
          company: String(finalAnswers.company || ""),
          role: String(finalAnswers.role || ""),
          days_left: Number(finalAnswers.days_left) || 30,
          round: String(finalAnswers.round || ""),
          level: String(finalAnswers.level || ""),
          mode: "interview_prep",
        },
        onChunk: (text) => {
          streamedRef.current += text;
          savePendingPlan(streamedRef.current);
          setStreamedText((p) => p + text);
        },
        onSessionId: handleSessionId,
        onDone: () => {
          if (capturedSid.current) {
            // Ensure final plan saved to session key
            savePlan(capturedSid.current, streamedRef.current);
            setGenState("done");
          } else {
            setGenState("error");
          }
        },
        onError: () => {
          setRetryCount((c) => c + 1);
          setGenState("error");
        },
      });
    } else {
      // upskill + shortlist — use chat endpoint
      const message = buildChatMessage(finalAnswers);
      await streamChat({
        message,
        onChunk: (text) => {
          streamedRef.current += text;
          savePendingPlan(streamedRef.current);
          setStreamedText((p) => p + text);
        },
        onSessionId: handleSessionId,
        onDone: () => {
          if (capturedSid.current) {
            savePlan(capturedSid.current, streamedRef.current);
            setGenState("done");
          } else {
            setGenState("error");
          }
        },
        onError: () => {
          setRetryCount((c) => c + 1);
          setGenState("error");
        },
      });
    }
  }

  async function advance(fieldValue: string | number) {
    const newAnswers = { ...answers, [currentStep.field]: fieldValue };
    setAnswers(newAnswers);
    setInputValue("");

    if (step < totalSteps - 1) {
      setStep((s) => s + 1);
      return;
    }

    await execute(newAnswers);
  }

  function handleNext() {
    if (currentStep.type === "select") return;
    const val = inputValue.trim();
    if (!val) {
      // For optional fields, skip with default
      if (currentStep.type === "number-optional") {
        advance(30);
      }
      return;
    }
    advance(
      currentStep.type === "number-optional" ? parseInt(val, 10) || 30 : val
    );
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleNext();
    }
  }

  const isOptional = currentStep.type === "number-optional";

  return (
    <div className="flex-1 flex flex-col items-center justify-center px-6 py-12 overflow-y-auto">
      {/* Back to mode selection */}
      <div className="w-full max-w-xl mb-8">
        <button
          onClick={() => { setMode(null); setStep(0); setAnswers({}); setInputValue(""); }}
          className="font-mono text-2xs text-text-muted hover:text-text-secondary transition-colors flex items-center gap-1"
        >
          ← back
        </button>
      </div>

      {/* Progress bar */}
      <div className="w-full max-w-xl mb-10">
        <div className="flex items-center justify-between mb-3">
          <span className="font-mono text-2xs text-text-muted uppercase tracking-widest">
            {mode === "interview" ? "Interview Prep" : mode === "upskill" ? "Upskill" : "Shortlist Analysis"} — Step {step + 1} of {totalSteps}
          </span>
          <span className="font-mono text-2xs text-text-muted">{Math.round(progress)}%</span>
        </div>
        <div className="h-px bg-surface-3 w-full overflow-hidden">
          <div
            className="h-full bg-accent transition-all duration-500 ease-out"
            style={{ width: `${progress}%` }}
          />
        </div>
      </div>

      {/* Question */}
      <div className="w-full max-w-xl animate-slide-up" key={`${mode}-${step}`}>
        <div className="mb-2">
          <span className="font-mono text-2xs text-accent uppercase tracking-widest">
            {String(step + 1).padStart(2, "0")} / {String(totalSteps).padStart(2, "0")}
          </span>
        </div>
        <h2 className="text-2xl font-semibold text-text-primary mb-2 leading-tight">
          {currentStep.question}
        </h2>
        <p className="text-text-muted text-sm mb-8">{currentStep.hint}</p>

        {currentStep.type === "select" ? (
          <div className="space-y-2">
            {"options" in currentStep && currentStep.options?.map((opt) => (
              <button
                key={opt.value}
                id={`option-${opt.value}`}
                onClick={() => advance(opt.value)}
                className="w-full text-left px-4 py-3 rounded-sm border border-border bg-surface-1 text-text-secondary text-sm hover:border-border-bright hover:text-text-primary transition-all focus-ring"
              >
                {opt.label}
              </button>
            ))}
          </div>
        ) : currentStep.type === "textarea" ? (
          <div className="flex flex-col gap-4">
            <textarea
              ref={textareaRef}
              id={`onboarding-textarea-${currentStep.field}`}
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={currentStep.hint}
              rows={4}
              className="w-full bg-surface-1 border border-border text-text-primary text-sm px-4 py-3 rounded-sm outline-none placeholder:text-text-muted focus:border-accent transition-colors font-mono leading-relaxed resize-none"
            />
            <button
              id={`onboarding-next-${currentStep.field}`}
              onClick={handleNext}
              disabled={!inputValue.trim()}
              className="self-start inline-flex items-center gap-2 bg-accent text-surface-0 font-semibold px-6 py-3 rounded-sm hover:bg-accent-dim disabled:opacity-30 disabled:cursor-not-allowed transition-colors text-sm focus-ring"
            >
              {step === totalSteps - 1 ? "Analyse now →" : "Continue →"}
            </button>
          </div>
        ) : (
          <div className="flex flex-col gap-4">
            <input
              ref={inputRef}
              id={`onboarding-input-${currentStep.field}`}
              type={currentStep.type === "number-optional" ? "number" : "text"}
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={isOptional ? "e.g. 14 (or leave blank for 30 days)" : currentStep.hint}
              min={currentStep.type === "number-optional" ? 1 : undefined}
              max={currentStep.type === "number-optional" ? 365 : undefined}
              className="w-full bg-surface-1 border border-border text-text-primary text-lg px-4 py-4 rounded-sm outline-none placeholder:text-text-muted focus:border-accent transition-colors font-mono"
            />
            <div className="flex items-center gap-3">
              <button
                id={`onboarding-next-${currentStep.field}`}
                onClick={handleNext}
                disabled={!inputValue.trim() && !isOptional}
                className="inline-flex items-center gap-2 bg-accent text-surface-0 font-semibold px-6 py-3 rounded-sm hover:bg-accent-dim disabled:opacity-30 disabled:cursor-not-allowed transition-colors text-sm focus-ring"
              >
                {step === totalSteps - 1 ? "Build my plan →" : "Continue →"}
              </button>
              {isOptional && (
                <button
                  id="skip-days"
                  onClick={() => advance(30)}
                  className="font-mono text-xs text-text-muted hover:text-text-secondary transition-colors px-4 py-3"
                >
                  Skip → default 30 days
                </button>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
