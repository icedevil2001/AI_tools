/**
 * The app's public origin.
 *
 * Magic links have to carry a URL that Supabase will actually honour. Supabase
 * checks `emailRedirectTo` against the project's Redirect URLs allowlist and,
 * when it does not match, silently falls back to the project's Site URL rather
 * than reporting an error -- so a URL that cannot be allowlisted in advance
 * produces a link back to whatever the Site URL happens to be, with no clue as
 * to why.
 *
 * `window.location.origin` is exactly such a URL on Vercel: every deployment
 * gets a fresh hostname like food-logger-<hash>-<team>.vercel.app, so it can
 * never be on the allowlist. Hence this resolver, which prefers a stable origin.
 */

function normalize(value: string): string {
  const withScheme = /^https?:\/\//.test(value) ? value : `https://${value}`;
  // Trailing slashes matter: `${origin}/auth/callback` would otherwise produce
  // a double slash, which does not match an allowlist entry.
  return withScheme.replace(/\/+$/, "");
}

/**
 * Resolution order, most explicit first:
 *
 * 1. `NEXT_PUBLIC_SITE_URL` -- set this yourself when you want one canonical
 *    origin regardless of where the code is running.
 * 2. `NEXT_PUBLIC_VERCEL_PROJECT_PRODUCTION_URL` -- Vercel's *stable*
 *    production domain, which does not change between deployments.
 * 3. `NEXT_PUBLIC_VERCEL_URL` -- this specific deployment's hostname.
 * 4. `window.location.origin` -- local development.
 *
 * Set `NEXT_PUBLIC_SITE_URL` on Vercel's Production environment **only**. Left
 * unset on Preview, deployments fall through to their own hostname, so testing
 * a preview signs you into that preview rather than bouncing you to production
 * halfway through.
 */
export function getSiteUrl(): string {
  const explicit = process.env.NEXT_PUBLIC_SITE_URL;
  if (explicit) return normalize(explicit);

  const vercelProduction = process.env.NEXT_PUBLIC_VERCEL_PROJECT_PRODUCTION_URL;
  if (vercelProduction) return normalize(vercelProduction);

  const vercelDeployment = process.env.NEXT_PUBLIC_VERCEL_URL;
  if (vercelDeployment) return normalize(vercelDeployment);

  if (typeof window !== "undefined") return normalize(window.location.origin);

  // Server-side with nothing configured. Local dev is the only place this is
  // reached; anywhere else it means NEXT_PUBLIC_SITE_URL should have been set.
  return "http://localhost:3000";
}

/**
 * The public origin of an incoming request, for building redirects back to it.
 *
 * `new URL(request.url).origin` is the obvious choice and the wrong one behind
 * a proxy: on Vercel it can be the internal request origin rather than the
 * hostname the user actually typed, sending them somewhere unreachable on the
 * final hop of signing in. The forwarded headers carry the real one.
 *
 * Lives here rather than in the route file because Next.js restricts which
 * symbols a route module may export, which would leave it untestable.
 */
export function publicOriginFromRequest(request: Request): string {
  const host = request.headers.get("x-forwarded-host");
  if (host) {
    const proto = request.headers.get("x-forwarded-proto") ?? "https";
    // Both headers can carry a comma-separated chain when several proxies are
    // involved; the first entry is the origin the client addressed.
    const firstHost = host.split(",")[0].trim();
    const firstProto = proto.split(",")[0].trim();
    if (firstHost) return `${firstProto}://${firstHost}`;
  }

  return getSiteUrl();
}
