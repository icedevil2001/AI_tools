"use client";

import { createBrowserClient } from "@supabase/ssr";
import { publicEnv } from "./env";

/**
 * Supabase client for use in client components. Carries the anon key and the
 * user's session, so every query it makes is subject to RLS.
 */
export function createClient() {
  return createBrowserClient(publicEnv.supabaseUrl(), publicEnv.supabaseAnonKey(), {
    db: { schema: "foodlog" },
  });
}
