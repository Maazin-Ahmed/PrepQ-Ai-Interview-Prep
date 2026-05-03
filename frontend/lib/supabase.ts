import { createClient as _createClient } from "@supabase/supabase-js";

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL!;
const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!;

// Module-level singleton — avoids creating multiple GoTrue clients
let _instance: ReturnType<typeof _createClient> | null = null;

/**
 * Returns the singleton Supabase browser client.
 * Call this anywhere in client components.
 */
export function createClient() {
  if (!_instance) {
    _instance = _createClient(supabaseUrl, supabaseAnonKey, {
      auth: {
        persistSession: true,
        autoRefreshToken: true,
        detectSessionInUrl: true, // needed for OAuth redirects
      },
    });
  }
  return _instance;
}
