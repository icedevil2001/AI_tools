/**
 * Environment access, centralised so a missing variable fails loudly at the
 * point of use with a message naming the variable -- rather than surfacing as
 * an opaque "Invalid API key" from a downstream service.
 */

function required(name: string): string {
  const value = process.env[name];
  if (!value) {
    throw new Error(
      `Missing required environment variable ${name}. Copy .env.example to .env.local and fill it in.`,
    );
  }
  return value;
}

/** Safe to reach the browser. */
export const publicEnv = {
  supabaseUrl: () => required("NEXT_PUBLIC_SUPABASE_URL"),
  supabaseAnonKey: () => required("NEXT_PUBLIC_SUPABASE_ANON_KEY"),
};

/**
 * Server-only. Importing this module from a client component would inline the
 * values into the browser bundle, so every accessor asserts it is running on
 * the server first.
 */
function serverOnly(name: string): string {
  if (typeof window !== "undefined") {
    throw new Error(`${name} is server-only and must never be read in the browser.`);
  }
  return required(name);
}

export const serverEnv = {
  supabaseServiceRoleKey: () => serverOnly("SUPABASE_SERVICE_ROLE_KEY"),
  openRouterApiKey: () => serverOnly("OPENROUTER_API_KEY"),
  openRouterVisionModel: () =>
    process.env.OPENROUTER_VISION_MODEL ?? "openai/gpt-5.6-luna",
  openRouterSiteUrl: () => process.env.OPENROUTER_SITE_URL ?? "",
  openRouterSiteName: () => process.env.OPENROUTER_SITE_NAME ?? "Food Logger",
};
