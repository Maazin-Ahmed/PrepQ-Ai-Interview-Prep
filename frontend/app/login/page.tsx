"use client";

import { useState } from "react";
import { createClient } from "@/lib/supabase";

export default function LoginPage() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleGoogleSignIn() {
    setLoading(true);
    setError(null);

    const supabase = createClient();
    const { error } = await supabase.auth.signInWithOAuth({
      provider: "google",
      options: {
        // After Google confirms auth, Supabase redirects here.
        // The callback page exchanges the code for a session and
        // then redirects to /chat.
        redirectTo: `${window.location.origin}/auth/callback`,
      },
    });

    if (error) {
      setError(error.message);
      setLoading(false);
    }
    // If no error, the browser is redirected to Google — no further action needed.
  }

  return (
    <main className="min-h-screen bg-surface-0 flex items-center justify-center px-4 relative overflow-hidden">
      {/* Grid background */}
      <div className="absolute inset-0 bg-grid opacity-100 pointer-events-none" />

      {/* Accent radial glow */}
      <div
        className="absolute top-0 left-1/2 -translate-x-1/2 w-[600px] h-[400px] pointer-events-none"
        style={{
          background:
            "radial-gradient(ellipse 70% 60% at 50% 0%, rgba(0,229,160,0.07) 0%, transparent 70%)",
        }}
      />

      {/* Card */}
      <div className="relative z-10 w-full max-w-sm">
        {/* Logo */}
        <div className="text-center mb-10">
          <span className="font-mono text-accent font-semibold text-sm tracking-widest uppercase">
            PrepQ
          </span>
          <p className="text-text-muted text-xs font-mono mt-2">
            AI interview prep for Indian freshers
          </p>
        </div>

        <div className="bg-surface-1 border border-border rounded-sm p-8">
          <h1 className="text-text-primary font-semibold text-xl mb-1 leading-tight">
            Sign in to PrepQ
          </h1>
          <p className="text-text-muted text-sm mb-8">
            Your sessions, plans and history are saved to your account.
          </p>

          {error && (
            <div className="mb-4 px-4 py-3 bg-danger/5 border border-danger/20 rounded-sm">
              <p className="text-danger text-xs font-mono">{error}</p>
            </div>
          )}

          <button
            id="google-signin-btn"
            onClick={handleGoogleSignIn}
            disabled={loading}
            className="
              w-full flex items-center justify-center gap-3
              bg-surface-2 border border-border hover:border-border-bright
              text-text-primary text-sm font-medium
              px-4 py-3 rounded-sm
              transition-all hover:bg-surface-3
              disabled:opacity-50 disabled:cursor-not-allowed
              focus-ring
            "
          >
            {loading ? (
              <span className="w-4 h-4 rounded-full border-2 border-text-muted border-t-accent animate-spin" />
            ) : (
              /* Google G logo */
              <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
                <path
                  d="M17.64 9.2c0-.637-.057-1.251-.164-1.84H9v3.481h4.844a4.14 4.14 0 0 1-1.796 2.716v2.259h2.908c1.702-1.567 2.684-3.875 2.684-6.615Z"
                  fill="#4285F4"
                />
                <path
                  d="M9 18c2.43 0 4.467-.806 5.956-2.18l-2.908-2.259c-.806.54-1.837.86-3.048.86-2.344 0-4.328-1.584-5.036-3.711H.957v2.332A8.997 8.997 0 0 0 9 18Z"
                  fill="#34A853"
                />
                <path
                  d="M3.964 10.71A5.41 5.41 0 0 1 3.682 9c0-.593.102-1.17.282-1.71V4.958H.957A8.996 8.996 0 0 0 0 9c0 1.452.348 2.827.957 4.042l3.007-2.332Z"
                  fill="#FBBC05"
                />
                <path
                  d="M9 3.58c1.321 0 2.508.454 3.44 1.345l2.582-2.58C13.463.891 11.426 0 9 0A8.997 8.997 0 0 0 .957 4.958L3.964 7.29C4.672 5.163 6.656 3.58 9 3.58Z"
                  fill="#EA4335"
                />
              </svg>
            )}
            {loading ? "Redirecting…" : "Continue with Google"}
          </button>

          <p className="text-text-muted text-xs text-center mt-6 leading-relaxed">
            By signing in you agree to our terms. Your data is stored
            securely in Supabase and never sold.
          </p>
        </div>
      </div>
    </main>
  );
}
