/**
 * Environment access, centralised so a missing variable fails loudly at the
 * point of use with a message naming the variable -- rather than surfacing as
 * an opaque "Invalid API key" from a downstream service.
 */

function required(name: string, value: string | undefined): string {
  // Absent and present-but-blank need different advice. Copying .env.example
  // leaves every key defined with an empty value, so "set it" is the useful
  // instruction there, not "create the file" -- which the person has already
  // done and will waste time re-checking.
  if (value === undefined) {
    throw new Error(
      `Missing required environment variable ${name}. ` +
        `Copy food_logger/.env.example to food_logger/.env.local and fill it in.`,
    );
  }
  if (value.trim() === "") {
    throw new Error(
      `Environment variable ${name} is set but empty. ` +
        `Add its value in food_logger/.env.local, then restart the dev server ` +
        `(Next.js only reads environment variables at startup).`,
    );
  }

  return value.trim();
}

/**
 * Safe to reach the browser. Next.js inlines `NEXT_PUBLIC_*` vars into the
 * client bundle by statically replacing exact `process.env.NEXT_PUBLIC_X`
 * expressions at build time -- a dynamic `process.env[name]` lookup can't be
 * inlined and always reads as undefined in the browser, so these must
 * reference `process.env.<NAME>` directly rather than going through a
 * name-keyed helper.
 */
export const publicEnv = {
  supabaseUrl: () => required("NEXT_PUBLIC_SUPABASE_URL", process.env.NEXT_PUBLIC_SUPABASE_URL),
  supabaseAnonKey: () =>
    required("NEXT_PUBLIC_SUPABASE_ANON_KEY", process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY),
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
  return required(name, process.env[name]);
}

export const serverEnv = {
  supabaseServiceRoleKey: () => serverOnly("SUPABASE_SERVICE_ROLE_KEY"),
  openRouterApiKey: () => serverOnly("OPENROUTER_API_KEY"),
  openRouterVisionModel: () =>
    process.env.OPENROUTER_VISION_MODEL ?? "openai/gpt-5.6-luna",
  openRouterSiteUrl: () => process.env.OPENROUTER_SITE_URL ?? "",
  openRouterSiteName: () => process.env.OPENROUTER_SITE_NAME ?? "Food Logger",
};
