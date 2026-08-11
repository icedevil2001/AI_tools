import { afterEach, describe, expect, it } from "vitest";
import { getSiteUrl, publicOriginFromRequest } from "@/lib/site-url";

const VARS = [
  "NEXT_PUBLIC_SITE_URL",
  "NEXT_PUBLIC_VERCEL_PROJECT_PRODUCTION_URL",
  "NEXT_PUBLIC_VERCEL_URL",
] as const;

function setEnv(env: Partial<Record<(typeof VARS)[number], string>>) {
  for (const v of VARS) delete process.env[v];
  for (const [k, value] of Object.entries(env)) process.env[k] = value;
}

afterEach(() => setEnv({}));

describe("getSiteUrl", () => {
  it("falls back to localhost when nothing is configured", () => {
    setEnv({});
    expect(getSiteUrl()).toBe("http://localhost:3000");
  });

  it("prefers an explicit site url over anything Vercel provides", () => {
    setEnv({
      NEXT_PUBLIC_SITE_URL: "https://diary.example.com",
      NEXT_PUBLIC_VERCEL_PROJECT_PRODUCTION_URL: "food-logger.vercel.app",
      NEXT_PUBLIC_VERCEL_URL: "food-logger-abc123-pri.vercel.app",
    });
    expect(getSiteUrl()).toBe("https://diary.example.com");
  });

  // The whole point of the resolver: a per-deployment hostname can never be on
  // Supabase's allowlist, so the stable production domain must win.
  it("prefers Vercel's stable production domain over the per-deployment one", () => {
    setEnv({
      NEXT_PUBLIC_VERCEL_PROJECT_PRODUCTION_URL: "food-logger.vercel.app",
      NEXT_PUBLIC_VERCEL_URL: "food-logger-abc123-pri.vercel.app",
    });
    expect(getSiteUrl()).toBe("https://food-logger.vercel.app");
  });

  // With NEXT_PUBLIC_SITE_URL set only on Production, a preview signs in
  // against itself rather than bouncing the tester to production.
  it("uses the deployment's own hostname on a preview", () => {
    setEnv({ NEXT_PUBLIC_VERCEL_URL: "food-logger-abc123-pri.vercel.app" });
    expect(getSiteUrl()).toBe("https://food-logger-abc123-pri.vercel.app");
  });

  it("adds https:// to the bare hostnames Vercel supplies", () => {
    setEnv({ NEXT_PUBLIC_VERCEL_URL: "food-logger.vercel.app" });
    expect(getSiteUrl()).toBe("https://food-logger.vercel.app");
  });

  it("preserves an explicit http:// origin", () => {
    setEnv({ NEXT_PUBLIC_SITE_URL: "http://localhost:3001" });
    expect(getSiteUrl()).toBe("http://localhost:3001");
  });

  // A trailing slash would produce `//auth/callback`, which does not match an
  // allowlist entry -- the exact failure this module exists to prevent.
  it("strips trailing slashes", () => {
    setEnv({ NEXT_PUBLIC_SITE_URL: "https://diary.example.com///" });
    expect(getSiteUrl()).toBe("https://diary.example.com");
    expect(`${getSiteUrl()}/auth/callback`).toBe("https://diary.example.com/auth/callback");
  });
});

describe("publicOriginFromRequest", () => {
  const req = (headers: Record<string, string>) =>
    new Request("https://internal-vercel-host.local/auth/callback", { headers });

  it("uses the forwarded host rather than the request's own origin", () => {
    setEnv({});
    expect(
      publicOriginFromRequest(
        req({ "x-forwarded-host": "diary.example.com", "x-forwarded-proto": "https" }),
      ),
    ).toBe("https://diary.example.com");
  });

  it("takes the first entry when proxies chain the headers", () => {
    setEnv({});
    expect(
      publicOriginFromRequest(
        req({
          "x-forwarded-host": "diary.example.com, internal.vercel.app",
          "x-forwarded-proto": "https, http",
        }),
      ),
    ).toBe("https://diary.example.com");
  });

  it("assumes https when only the host is forwarded", () => {
    setEnv({});
    expect(publicOriginFromRequest(req({ "x-forwarded-host": "diary.example.com" }))).toBe(
      "https://diary.example.com",
    );
  });

  it("falls back to the configured site url with no forwarded headers", () => {
    setEnv({ NEXT_PUBLIC_SITE_URL: "https://diary.example.com" });
    expect(publicOriginFromRequest(req({}))).toBe("https://diary.example.com");
  });
});
