import { NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";

/**
 * Magic-link landing route. Exchanges the one-time code for a session cookie.
 */
export async function GET(request: Request) {
  const { searchParams, origin } = new URL(request.url);
  const code = searchParams.get("code");
  const next = searchParams.get("next") ?? "/log";

  // Open redirects: `next` arrives from the URL, so only same-origin relative
  // paths are honoured.
  const safeNext = next.startsWith("/") && !next.startsWith("//") ? next : "/log";

  if (!code) {
    return NextResponse.redirect(`${origin}/auth/error?reason=missing_code`);
  }

  const supabase = await createClient();
  const { error } = await supabase.auth.exchangeCodeForSession(code);

  if (error) {
    return NextResponse.redirect(`${origin}/auth/error?reason=exchange_failed`);
  }

  return NextResponse.redirect(`${origin}${safeNext}`);
}
