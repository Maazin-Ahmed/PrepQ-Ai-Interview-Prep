"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

const CYCLING_PHRASES = [
  "What company and role are you preparing for?",
  "When is your interview — exact date.",
  "What round? Technical, HR, OA, case study?",
  "How confident are you in the required skills?",
  "What have you already covered? What have you skipped?",
];

const FEATURES = [
  {
    label: "HYPER-SPECIFIC PLANS",
    description:
      "Not 'study DSA'. Your plan says: 'focus on sliding window — Cognizant TA round tests exactly this'. Pulled from real interview reports.",
  },
  {
    label: "LIVE COMPANY INTEL",
    description:
      "We fetch current interview patterns from Glassdoor, AmbitionBox, and LeetCode discuss before building your plan. No stale advice.",
  },
  {
    label: "MOCK + SCORE",
    description:
      "Mock interviews in the exact style of your target company. Scored on Clarity, Correctness, and Depth — with specific feedback, not 'good job'.",
  },
];

export default function LandingPage() {
  const [phraseIndex, setPhraseIndex] = useState(0);
  const [displayedText, setDisplayedText] = useState("");
  const [charIndex, setCharIndex] = useState(0);
  const [isDeleting, setIsDeleting] = useState(false);

  useEffect(() => {
    const currentPhrase = CYCLING_PHRASES[phraseIndex];

    const delay = isDeleting ? 22 : charIndex === currentPhrase.length ? 2200 : 42;

    const timer = setTimeout(() => {
      if (!isDeleting) {
        if (charIndex < currentPhrase.length) {
          setDisplayedText(currentPhrase.slice(0, charIndex + 1));
          setCharIndex((c) => c + 1);
        } else {
          setIsDeleting(true);
        }
      } else {
        if (charIndex > 0) {
          setDisplayedText(currentPhrase.slice(0, charIndex - 1));
          setCharIndex((c) => c - 1);
        } else {
          setIsDeleting(false);
          setPhraseIndex((i) => (i + 1) % CYCLING_PHRASES.length);
        }
      }
    }, delay);

    return () => clearTimeout(timer);
  }, [charIndex, isDeleting, phraseIndex]);

  return (
    <main className="min-h-screen bg-surface-0 relative overflow-hidden">
      {/* Grid background */}
      <div className="absolute inset-0 bg-grid opacity-100 pointer-events-none" />

      {/* Accent radial glow at top */}
      <div
        className="absolute top-0 left-1/2 -translate-x-1/2 w-[800px] h-[400px] pointer-events-none"
        style={{
          background:
            "radial-gradient(ellipse 70% 50% at 50% 0%, rgba(0,229,160,0.07) 0%, transparent 70%)",
        }}
      />

      {/* Nav */}
      <nav className="relative z-10 flex items-center justify-between px-6 py-5 max-w-6xl mx-auto">
        <div className="flex items-center gap-2">
          <span className="font-mono text-accent font-semibold text-sm tracking-widest uppercase">
            PrepQ
          </span>
        </div>
        <div className="flex items-center gap-6">
          <span className="text-text-muted text-xs font-mono">
            beta
          </span>
          <Link
            id="nav-start-link"
            href="/chat"
            className="font-mono text-xs text-surface-0 bg-accent hover:bg-accent-dim transition-colors px-4 py-2 rounded-sm font-medium tracking-wide focus-ring"
          >
            Start Preparing →
          </Link>
        </div>
      </nav>

      {/* Hero */}
      <section className="relative z-10 max-w-6xl mx-auto px-6 pt-24 pb-20">
        <div className="max-w-3xl">
          {/* Status badge */}
          <div className="inline-flex items-center gap-2 mb-8 px-3 py-1.5 rounded-sm border border-border bg-surface-1">
            <span className="w-1.5 h-1.5 rounded-full bg-accent animate-pulse" />
            <span className="font-mono text-2xs text-text-secondary uppercase tracking-widest">
              AI-powered · Real-time company intel · Live scoring
            </span>
          </div>

          {/* Wordmark */}
          <h1 className="text-6xl font-bold text-text-primary leading-none tracking-tight mb-6">
            Interview prep{" "}
            <span className="text-accent">without</span>
            <br />
            the noise.
          </h1>

          <p className="text-text-secondary text-xl leading-relaxed max-w-xl mb-12">
            PrepQ doesn&apos;t give you a topic list. It builds a ruthlessly prioritized plan
            specific to your company, role, timeline, and current level — then adapts it
            every day.
          </p>

          {/* Terminal typewriter */}
          <div className="bg-surface-1 border border-border rounded-sm p-5 mb-10 max-w-xl">
            <div className="flex items-center gap-2 mb-4">
              <span className="w-2.5 h-2.5 rounded-full bg-surface-4" />
              <span className="w-2.5 h-2.5 rounded-full bg-surface-4" />
              <span className="w-2.5 h-2.5 rounded-full bg-surface-4" />
              <span className="font-mono text-2xs text-text-muted ml-2 uppercase tracking-widest">
                PrepQ Agent
              </span>
            </div>
            <div className="font-mono text-sm text-text-primary min-h-[1.5rem]">
              <span className="text-accent mr-2">›</span>
              {displayedText}
              <span className="inline-block w-[2px] h-[1em] bg-accent ml-[1px] animate-cursor-blink align-middle" />
            </div>
          </div>

          {/* CTAs */}
          <div className="flex items-center gap-4">
            <Link
              id="hero-cta-primary"
              href="/chat"
              className="inline-flex items-center gap-2 bg-accent text-surface-0 font-semibold px-6 py-3 rounded-sm hover:bg-accent-dim transition-colors text-sm focus-ring"
            >
              Start preparing
              <span aria-hidden>→</span>
            </Link>
            <Link
              id="hero-cta-secondary"
              href="/chat"
              className="inline-flex items-center gap-2 text-text-secondary border border-border hover:border-border-bright hover:text-text-primary transition-colors px-6 py-3 rounded-sm text-sm font-mono focus-ring"
            >
              See how it works
            </Link>
          </div>
        </div>
      </section>

      {/* Divider */}
      <div className="relative z-10 max-w-6xl mx-auto px-6">
        <div className="border-t border-border" />
      </div>

      {/* Feature blocks */}
      <section className="relative z-10 max-w-6xl mx-auto px-6 py-20">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-px bg-border rounded-sm overflow-hidden">
          {FEATURES.map((feat, i) => (
            <div
              key={feat.label}
              className="bg-surface-1 p-8 hover:bg-surface-2 transition-colors group"
            >
              <div className="font-mono text-2xs text-accent uppercase tracking-widest mb-4">
                {String(i + 1).padStart(2, "0")} / {feat.label}
              </div>
              <p className="text-text-secondary text-sm leading-relaxed group-hover:text-text-primary transition-colors">
                {feat.description}
              </p>
            </div>
          ))}
        </div>
      </section>

      {/* Social proof — plain stat numbers */}
      <section className="relative z-10 max-w-6xl mx-auto px-6 pb-20">
        <div className="flex flex-col md:flex-row items-start md:items-center gap-12">
          {[
            { stat: "5", label: "questions to a personalized plan" },
            { stat: "20+", label: "Indian companies with specific intel" },
            { stat: "3", label: "score dimensions per mock answer" },
          ].map(({ stat, label }) => (
            <div key={stat} className="flex items-baseline gap-3">
              <span className="font-mono text-5xl font-bold text-accent tabular-nums">
                {stat}
              </span>
              <span className="text-text-muted text-sm max-w-[140px] leading-snug">
                {label}
              </span>
            </div>
          ))}
        </div>
      </section>

      {/* Bottom CTA */}
      <section className="relative z-10 border-t border-border">
        <div className="max-w-6xl mx-auto px-6 py-16 flex flex-col md:flex-row items-start md:items-center justify-between gap-8">
          <div>
            <div className="font-mono text-2xs text-text-muted uppercase tracking-widest mb-3">
              Built for Indian freshers
            </div>
            <p className="text-text-primary text-2xl font-semibold max-w-md leading-tight">
              Your interview is in{" "}
              <span className="text-accent">X days.</span>
              <br />
              Stop guessing what to study.
            </p>
          </div>
          <Link
            id="bottom-cta"
            href="/chat"
            className="flex-shrink-0 inline-flex items-center gap-2 bg-accent text-surface-0 font-semibold px-8 py-4 rounded-sm hover:bg-accent-dim transition-colors text-sm focus-ring"
          >
            Build my prep plan →
          </Link>
        </div>
      </section>

      {/* Footer */}
      <footer className="relative z-10 border-t border-border">
        <div className="max-w-6xl mx-auto px-6 py-6 flex items-center justify-between">
          <span className="font-mono text-2xs text-text-muted uppercase tracking-widest">
            PrepQ — beta
          </span>
          <span className="font-mono text-2xs text-text-muted">
            For Indian students and freshers
          </span>
        </div>
      </footer>
    </main>
  );
}
