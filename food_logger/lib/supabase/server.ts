import { createServerClient } from "@supabase/ssr";
import { createClient as createSupabaseClient } from "@supabase/supabase-js";
import { cookies } from "next/headers";
import { publicEnv, serverEnv } from "./env";

/**
 * Supabase client for server components, route handlers and server actions.
 * Uses the anon key and the request's session cookies, so RLS still applies --
 * this is the client you want almost everywhere on the server.
 */
export async function createClient() {
  const cookieStore = await cookies();

  return createServerClient(publicEnv.supabaseUrl(), publicEnv.supabaseAnonKey(), {
    db: { schema: "foodlog" },
    cookies: {
      getAll() {
        return cookieStore.getAll();
      },
      setAll(cookiesToSet) {
        try {
          for (const { name, value, options } of cookiesToSet) {
            cookieStore.set(name, value, options);
          }
        } catch {
          // Called from a server component, where cookies are read-only. The
          // middleware refreshes the session, so this is safe to swallow.
        }
      },
    },
  });
}

/**
 * Service-role client. Bypasses RLS entirely.
 *
 * Only for writes the user must not be able to forge -- currently just the
 * ai_extractions audit rows. Never hand this client a user-supplied filter and
 * never use it merely to avoid writing a policy: every use is a place where
 * RLS is not protecting you, so the caller must scope the query itself.
 */
export function createServiceRoleClient() {
  return createSupabaseClient(publicEnv.supabaseUrl(), serverEnv.supabaseServiceRoleKey(), {
    db: { schema: "foodlog" },
    auth: { persistSession: false, autoRefreshToken: false },
  });
}
