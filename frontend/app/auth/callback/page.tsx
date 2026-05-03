"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase";

/**
 * OAuth callback page.
 *
 * Why a client page instead of a server route.ts?
 *
 * Supabase's Google OAuth (implicit / PKCE flow) delivers tokens in the URL
 * **hash fragment** — e.g. `#access_token=...&refresh_token=...&type=signup`.
 * Hash fragments are NEVER sent to the server (it's a browser-only construct),
 * so a server-side Route Handler can never read them. This page runs in the
 * browser, reads `window.location.hash`, extracts the tokens, and calls
 * `supabase.auth.setSession()` to persist the session in localStorage.
 */
export default function AuthCallbackPage() {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function handleCallback() {
      const supabase = createClient();

      // Supabase JS SDK can detect and exchange the hash automatically when
      // detectSessionInUrl: true is set (which our singleton does). Calling
      // getSession() here triggers that detection before we do anything else.
      const { data, error: sessionError } = await supabase.auth.getSession();

      if (!sessionError && data.session) {
        // Session is already set — the SDK handled the hash exchange for us.
        router.replace("/chat");
        return;
      }

      // Fallback: manually parse the hash and call setSession().
      // Handles cases where the SDK didn't auto-detect (e.g. hash format changed).
      const hash = window.location.hash.slice(1); // strip leading '#'
      const params = new URLSearchParams(hash);

      const accessToken = params.get("access_token");
      const refreshToken = params.get("refresh_token");

      if (accessToken && refreshToken) {
        const { error: sessionSetError } = await supabase.auth.setSession({
          access_token: accessToken,
          refresh_token: refreshToken,
        });

        if (!sessionSetError) {
          router.replace("/chat");
          return;
        }

        setError(`Session error: ${sessionSetError.message}`);
        return;
      }

      // No token in hash and no existing session — something upstream failed.
      setError(
        sessionError?.message ??
          "No authentication token found. Please try signing in again."
      );
    }

    handleCallback();
  }, [router]);

  if (error) {
    return (
      <main className="min-h-screen bg-surface-0 flex items-center justify-center px-4">
        <div className="w-full max-w-sm text-center">
          <div className="font-mono text-accent text-xs tracking-widest uppercase mb-6">
            PrepQ
          </div>
          <div className="bg-surface-1 border border-danger/20 rounded-sm p-6">
            <div className="text-danger text-sm font-medium mb-2">
              Sign-in failed
            </div>
            <p className="text-text-muted text-xs leading-relaxed mb-6">{error}</p>
            <a
              href="/login"
              className="inline-flex items-center gap-2 text-xs font-mono text-accent hover:underline"
            >
              ← Back to login
            </a>
          </div>
        </div>
      </main>
    );
  }

  // Loading state while the session is being established
  return (
    <main className="min-h-screen bg-surface-0 flex items-center justify-center">
      <div className="flex flex-col items-center gap-4">
        <span className="w-5 h-5 rounded-full border-2 border-border border-t-accent animate-spin" />
        <span className="font-mono text-[10px] text-text-muted uppercase tracking-widest">
          Completing sign-in…
        </span>
      </div>
    </main>
  );
}
