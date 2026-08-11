"use client";

import { useState } from "react";
import { createClient } from "@/lib/supabase/client";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [status, setStatus] = useState<"idle" | "sending" | "error">("idle");
  const [message, setMessage] = useState("");

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setStatus("sending");

    const supabase = createClient();
    const { error } = await supabase.auth.signInWithPassword({
      email: email.trim(),
      password,
    });

    if (error) {
      setStatus("error");
      setMessage(error.message);
      return;
    }

    const next = new URLSearchParams(window.location.search).get("next") ?? "/log";
    window.location.href = next;
  }

  return (
    <main className="mx-auto flex min-h-dvh w-full max-w-md flex-col justify-center px-6 py-12">
      <h1 className="text-2xl font-semibold text-ink">Food &amp; symptom diary</h1>
      <p className="mt-2 text-sm text-ink/70">Sign in with your email and password.</p>

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

        <div>
          <label htmlFor="password" className="block text-sm font-medium text-ink">
            Password
          </label>
          <input
            id="password"
            type="password"
            required
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="mt-1 w-full rounded-xl border border-ink/15 bg-white px-4 py-3 text-base text-ink outline-none focus:border-ink/40"
            placeholder="••••••••"
          />
        </div>

        <button
          type="submit"
          disabled={status === "sending" || email.trim() === "" || password === ""}
          className="w-full rounded-xl bg-ink px-4 py-3 text-base font-medium text-cream disabled:opacity-40"
        >
          {status === "sending" ? "Signing in…" : "Sign in"}
        </button>

        {status === "error" && (
          <p role="alert" className="text-sm text-red-700">
            {message}
          </p>
        )}
      </form>

      <p className="mt-10 text-xs leading-relaxed text-ink/50">
        This app is a diary to help you and your doctor spot patterns. It is not medical advice
        and cannot diagnose anything.
      </p>
    </main>
  );
}
