import { NextResponse } from "next/server";
import { publicOriginFromRequest } from "@/lib/site-url";
import { createClient } from "@/lib/supabase/server";

/**
 * Magic-link landing route. Exchanges the one-time code for a session cookie.
 */
export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const code = searchParams.get("code");
  const next = searchParams.get("next") ?? "/log";
  // Not new URL(request.url).origin -- behind Vercel's proxy that can be the
  // internal origin, which would strand the user on the last hop of signing in.
  const origin = publicOriginFromRequest(request);

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
