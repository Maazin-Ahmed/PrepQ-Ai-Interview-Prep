"use client";

import { useState, useCallback } from "react";
import { streamMockQuestion, scoreMockAnswer, type MockScoreResult } from "@/lib/api";

interface MockInterviewProps {
  sessionId: string;
}

type Phase = "idle" | "loading_question" | "answering" | "scoring" | "scored";

function ScoreBar({ label, score }: { label: string; score: number }) {
  const pct = (score / 5) * 100;
  const color = score >= 4 ? "#00e5a0" : score >= 3 ? "#ffb800" : "#ff3b30";
  return (
    <div>
      <div className="flex justify-between mb-1">
        <span className="font-mono text-2xs text-text-muted uppercase tracking-widest">{label}</span>
        <span className="font-mono text-xs font-bold" style={{ color }}>{score}/5</span>
      </div>
      <div className="h-1.5 bg-surface-3 rounded-full overflow-hidden">
        <div
          className="h-full rounded-full score-bar-fill"
          style={{ "--bar-width": `${pct}%`, backgroundColor: color } as React.CSSProperties}
        />
      </div>
    </div>
  );
}

function OverallRing({ overall }: { overall: number }) {
  const pct = (overall / 5) * 100;
  const color = overall >= 4 ? "#00e5a0" : overall >= 3 ? "#ffb800" : "#ff3b30";
  const circumference = 2 * Math.PI * 36;
  const dashOffset = circumference - (pct / 100) * circumference;

  return (
    <div className="relative w-24 h-24 flex-shrink-0">
      <svg viewBox="0 0 80 80" className="w-full h-full -rotate-90">
        <circle cx="40" cy="40" r="36" fill="none" stroke="#1e1e1e" strokeWidth="6" />
        <circle
          cx="40" cy="40" r="36" fill="none"
          stroke={color} strokeWidth="6"
          strokeDasharray={circumference}
          strokeDashoffset={dashOffset}
          strokeLinecap="round"
          style={{ transition: "stroke-dashoffset 1s cubic-bezier(0.16,1,0.3,1)" }}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="font-mono text-xl font-bold" style={{ color }}>{overall.toFixed(1)}</span>
        <span className="font-mono text-2xs text-text-muted">/ 5</span>
      </div>
    </div>
  );
}

export default function MockInterview({ sessionId }: MockInterviewProps) {
  const [phase, setPhase] = useState<Phase>("idle");
  const [questionIndex, setQuestionIndex] = useState(0);
  const [currentQuestion, setCurrentQuestion] = useState("");
  const [answer, setAnswer] = useState("");
  const [score, setScore] = useState<MockScoreResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const startQuestion = useCallback(async (index: number) => {
    setPhase("loading_question");
    setCurrentQuestion("");
    setAnswer("");
    setScore(null);
    setError(null);

    await streamMockQuestion({
      sessionId,
      questionIndex: index,
      onChunk: (text) => {
        setCurrentQuestion((prev) => prev + text);
        setPhase("answering");
      },
      onDone: () => setPhase("answering"),
      onError: (err) => {
        setError(err);
        setPhase("idle");
      },
    });
  }, [sessionId]);

  const submitAnswer = useCallback(async () => {
    if (!answer.trim() || !currentQuestion) return;
    setPhase("scoring");
    setError(null);

    try {
      const result = await scoreMockAnswer({
        sessionId,
        question: currentQuestion,
        answer,
        questionIndex,
      });
      setScore(result);
      setPhase("scored");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Scoring failed");
      setPhase("answering");
    }
  }, [answer, currentQuestion, sessionId, questionIndex]);

  const nextQuestion = () => {
    const next = questionIndex + 1;
    setQuestionIndex(next);
    startQuestion(next);
  };

  return (
    <div className="max-w-3xl mx-auto px-6 py-8 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <div className="font-mono text-2xs text-text-muted uppercase tracking-widest mb-1">
            Mock Interview
          </div>
          <h2 className="text-lg font-semibold text-text-primary">
            Question {questionIndex + 1}
          </h2>
        </div>
        {phase === "idle" && (
          <button
            id="start-mock-btn"
            onClick={() => startQuestion(0)}
            className="inline-flex items-center gap-2 bg-accent text-surface-0 font-semibold px-5 py-2.5 rounded-sm hover:bg-accent-dim transition-colors text-sm focus-ring"
          >
            Start Mock Interview →
          </button>
        )}
      </div>

      {/* Question box */}
      {phase === "loading_question" && (
        <div className="bg-surface-1 border border-border rounded-sm p-6">
          <span className="font-mono text-text-muted text-sm animate-pulse">
            Generating question…
          </span>
        </div>
      )}

      {(phase === "answering" || phase === "scoring" || phase === "scored") && currentQuestion && (
        <div className="bg-surface-1 border border-border rounded-sm p-6">
          <div className="font-mono text-2xs text-accent uppercase tracking-widest mb-4">
            Question
          </div>
          <p className="text-text-primary text-sm leading-relaxed font-medium">
            {currentQuestion}
          </p>
        </div>
      )}

      {/* Answer area */}
      {(phase === "answering" || phase === "scoring") && (
        <div className="space-y-3">
          <label
            htmlFor="mock-answer"
            className="font-mono text-2xs text-text-muted uppercase tracking-widest"
          >
            Your Answer
          </label>
          <textarea
            id="mock-answer"
            value={answer}
            onChange={(e) => setAnswer(e.target.value)}
            disabled={phase === "scoring"}
            rows={8}
            placeholder="Type your answer here. Be thorough — the scorer evaluates clarity, correctness, and depth."
            className="w-full bg-surface-1 border border-border text-text-primary text-sm px-4 py-3 rounded-sm outline-none placeholder:text-text-muted focus:border-accent transition-colors font-mono leading-relaxed disabled:opacity-50"
          />
          <button
            id="submit-answer-btn"
            onClick={submitAnswer}
            disabled={!answer.trim() || phase === "scoring"}
            className="inline-flex items-center gap-2 bg-accent text-surface-0 font-semibold px-6 py-3 rounded-sm hover:bg-accent-dim disabled:opacity-30 disabled:cursor-not-allowed transition-colors text-sm focus-ring"
          >
            {phase === "scoring" ? (
              <>
                <span className="w-3 h-3 rounded-full border-2 border-surface-0 border-t-transparent animate-spin" />
                Scoring…
              </>
            ) : (
              "Submit Answer →"
            )}
          </button>
        </div>
      )}

      {/* Score panel */}
      {phase === "scored" && score && (
        <div className="space-y-5 animate-slide-up">
          {/* Overall + bars */}
          <div className="bg-surface-1 border border-border rounded-sm p-6">
            <div className="font-mono text-2xs text-text-muted uppercase tracking-widest mb-6">
              Score
            </div>
            <div className="flex items-start gap-8">
              <OverallRing overall={score.overall} />
              <div className="flex-1 space-y-4">
                <ScoreBar label="Clarity" score={score.clarity} />
                <ScoreBar label="Correctness" score={score.correctness} />
                <ScoreBar label="Depth" score={score.depth} />
              </div>
            </div>
          </div>

          {/* Feedback */}
          <div className="bg-surface-1 border border-border rounded-sm p-6">
            <div className="font-mono text-2xs text-text-muted uppercase tracking-widest mb-3">
              Feedback
            </div>
            <p className="text-text-secondary text-sm leading-relaxed">{score.feedback}</p>
          </div>

          {/* Missing concepts */}
          {score.missing?.length > 0 && (
            <div className="border border-warning/20 bg-warning/5 rounded-sm p-5">
              <div className="font-mono text-2xs text-warning uppercase tracking-widest mb-4">
                What Was Missing
              </div>
              <ul className="space-y-2">
                {score.missing.map((m, i) => (
                  <li key={i} className="flex items-start gap-3">
                    <span className="text-warning text-xs mt-0.5 flex-shrink-0">→</span>
                    <span className="text-sm text-text-secondary">{m}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Next question */}
          <div className="flex items-center justify-between pt-2">
            {score.next_question && (
              <p className="text-text-muted text-xs font-mono max-w-sm">
                Next: {score.next_question.slice(0, 80)}…
              </p>
            )}
            <button
              id="next-question-btn"
              onClick={nextQuestion}
              className="inline-flex items-center gap-2 bg-surface-2 border border-border text-text-primary font-semibold px-5 py-2.5 rounded-sm hover:bg-surface-3 hover:border-border-bright transition-colors text-sm focus-ring ml-auto"
            >
              Next Question →
            </button>
          </div>
        </div>
      )}

      {error && (
        <div className="text-danger text-xs font-mono px-4 py-3 bg-danger/5 border border-danger/20 rounded-sm">
          {error}
        </div>
      )}
    </div>
  );
}
