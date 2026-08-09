import Link from "next/link";

export default async function AuthErrorPage({
  searchParams,
}: {
  searchParams: Promise<{ reason?: string }>;
}) {
  const { reason } = await searchParams;

  const explanation =
    reason === "exchange_failed"
      ? "That sign-in link has already been used or has expired."
      : "That sign-in link was incomplete.";

  return (
    <main className="mx-auto flex min-h-dvh w-full max-w-md flex-col justify-center px-6 py-12">
      <h1 className="text-xl font-semibold text-ink">Couldn&apos;t sign you in</h1>
      <p className="mt-2 text-sm text-ink/70">{explanation} Request a new one below.</p>
      <Link
        href="/login"
        className="mt-6 inline-block rounded-xl bg-ink px-4 py-3 text-center text-base font-medium text-cream"
      >
        Back to sign in
      </Link>
    </main>
  );
}
