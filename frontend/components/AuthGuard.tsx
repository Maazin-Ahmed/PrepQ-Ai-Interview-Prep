"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase";
import type { User } from "@supabase/supabase-js";

interface AuthGuardProps {
  children: (user: User) => React.ReactNode;
}

/**
 * Wraps a page that requires authentication.
 * - Shows a loading spinner while the session is being checked.
 * - Redirects to /login if the user is not signed in.
 * - Renders children (passing the resolved User) if authenticated.
 */
export default function AuthGuard({ children }: AuthGuardProps) {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [checking, setChecking] = useState(true);

  useEffect(() => {
    const supabase = createClient();

    // 1. Get the initial session (from localStorage / cookie)
    supabase.auth.getSession().then(({ data: { session } }) => {
      if (!session) {
        router.replace("/login");
      } else {
        setUser(session.user);
        setChecking(false);
      }
    });

    // 2. Keep the user state in sync with auth events (sign-in, sign-out, token refresh)
    const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, session) => {
      if (!session) {
        router.replace("/login");
      } else {
        setUser(session.user);
        setChecking(false);
      }
    });

    return () => subscription.unsubscribe();
  }, [router]);

  if (checking) {
    return (
      <div className="h-[100dvh] bg-surface-0 flex items-center justify-center">
        <div className="flex flex-col items-center gap-4">
          <span className="w-5 h-5 rounded-full border-2 border-border border-t-accent animate-spin" />
          <span className="font-mono text-[10px] text-text-muted uppercase tracking-widest">
            Checking session…
          </span>
        </div>
      </div>
    );
  }

  if (!user) return null; // Redirect in progress

  return <>{children(user)}</>;
}
