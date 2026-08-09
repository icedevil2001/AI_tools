import { createServerClient } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";
import { publicEnv } from "@/lib/supabase/env";

/**
 * Refreshes the Supabase session on every request and gates the app behind
 * sign-in.
 *
 * The allowlist below is deliberately small: anything not named here requires a
 * session, so adding a new page cannot accidentally expose data by forgetting a
 * guard. Failing closed is the right default for a medical diary.
 */
const PUBLIC_PATHS = ["/login", "/auth/callback", "/auth/error"];

export async function middleware(request: NextRequest) {
  let response = NextResponse.next({ request });

  // Read through publicEnv rather than process.env directly. Middleware runs on
  // every request, so it is the first thing to fail on a misconfigured
  // deployment and should give the clearest error in the codebase. Using
  // `process.env.X!` instead hands undefined to createServerClient, which then
  // reports "Your project's URL and Key are required" -- true, but it names
  // neither the variable nor the file, sending you to the Supabase dashboard
  // when the fix is in .env.local.
  const supabase = createServerClient(
    publicEnv.supabaseUrl(),
    publicEnv.supabaseAnonKey(),
    {
      cookies: {
        getAll() {
          return request.cookies.getAll();
        },
        setAll(cookiesToSet) {
          for (const { name, value } of cookiesToSet) {
            request.cookies.set(name, value);
          }
          response = NextResponse.next({ request });
          for (const { name, value, options } of cookiesToSet) {
            response.cookies.set(name, value, options);
          }
        },
      },
    },
  );

  // getUser() revalidates the token with Supabase. getSession() only reads the
  // cookie, which a client can tamper with, so it must not be used to authorize.
  const {
    data: { user },
  } = await supabase.auth.getUser();

  const { pathname } = request.nextUrl;
  const isPublic = PUBLIC_PATHS.some((p) => pathname === p || pathname.startsWith(`${p}/`));

  if (!user && !isPublic) {
    const url = request.nextUrl.clone();
    url.pathname = "/login";
    // Preserve where they were heading so a magic link opened later lands in
    // the right place.
    url.searchParams.set("next", pathname);
    return NextResponse.redirect(url);
  }

  if (user && pathname === "/login") {
    const url = request.nextUrl.clone();
    url.pathname = "/log";
    url.search = "";
    return NextResponse.redirect(url);
  }

  return response;
}

export const config = {
  matcher: [
    // Everything except Next internals and static assets.
    "/((?!_next/static|_next/image|favicon.ico|manifest.json|icons/|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)",
  ],
};
