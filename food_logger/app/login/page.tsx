"use client";

import { useState } from "react";
import { createClient } from "@/lib/supabase/client";
import { getSiteUrl } from "@/lib/site-url";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [status, setStatus] = useState<"idle" | "sending" | "sent" | "error">("idle");
  const [message, setMessage] = useState("");

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setStatus("sending");

    const supabase = createClient();
    const next = new URLSearchParams(window.location.search).get("next") ?? "/log";
    // getSiteUrl() rather than window.location.origin: Vercel gives every
    // deployment a new hostname, which can never be on Supabase's Redirect URLs
    // allowlist, and an unlisted value is silently replaced with the project's
    // Site URL instead of being rejected.
    const { error } = await supabase.auth.signInWithOtp({
      email: email.trim(),
      options: {
        emailRedirectTo: `${getSiteUrl()}/auth/callback?next=${encodeURIComponent(next)}`,
      },
    });

    if (error) {
      setStatus("error");
      setMessage(error.message);
      return;
    }
    setStatus("sent");
  }

  return (
    <main className="mx-auto flex min-h-dvh w-full max-w-md flex-col justify-center px-6 py-12">
      <h1 className="text-2xl font-semibold text-ink">Food &amp; symptom diary</h1>
      <p className="mt-2 text-sm text-ink/70">
        Sign in with your email. We&apos;ll send a link — there&apos;s no password to remember.
      </p>

      {status === "sent" ? (
        <div className="mt-8 rounded-xl border border-emerald-200 bg-emerald-50 p-4">
          <p className="text-sm text-emerald-900">
            Check <span className="font-medium">{email}</span> for a sign-in link. You can close
            this tab.
          </p>
        </div>
      ) : (
        <form onSubmit={handleSubmit} className="mt-8 space-y-4">
          <div>
            <label htmlFor="email" className="block text-sm font-medium text-ink">
              Email
            </label>
            <input
              id="email"
              type="email"
              required
              autoComplete="email"
              inputMode="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="mt-1 w-full rounded-xl border border-ink/15 bg-white px-4 py-3 text-base text-ink outline-none focus:border-ink/40"
              placeholder="you@example.com"
            />
          </div>

          <button
            type="submit"
            disabled={status === "sending" || email.trim() === ""}
            className="w-full rounded-xl bg-ink px-4 py-3 text-base font-medium text-cream disabled:opacity-40"
          >
            {status === "sending" ? "Sending…" : "Send sign-in link"}
          </button>

          {status === "error" && (
            <p role="alert" className="text-sm text-red-700">
              {message}
            </p>
          )}
        </form>
      )}

      <p className="mt-10 text-xs leading-relaxed text-ink/50">
        This app is a diary to help you and your doctor spot patterns. It is not medical advice
        and cannot diagnose anything.
      </p>
    </main>
  );
}
