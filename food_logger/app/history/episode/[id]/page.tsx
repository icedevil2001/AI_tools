import Link from "next/link";
import { notFound } from "next/navigation";
import { EpisodeEditForm } from "@/components/EpisodeEditForm";
import { createClient } from "@/lib/supabase/server";

export const dynamic = "force-dynamic";

export default async function EditEpisodePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const supabase = await createClient();

  const { data: episode } = await supabase.from("episodes").select("*").eq("id", id).single();
  if (!episode) notFound();

  return (
    <main className="mx-auto w-full max-w-md px-5 pb-16 pt-8">
      <Link href="/history" className="text-sm text-ink/60 underline">
        ← Back to history
      </Link>
      <h1 className="mt-3 text-xl font-semibold text-ink">Edit episode</h1>

      <div className="mt-6">
        <EpisodeEditForm
          episodeId={episode.id}
          initial={{
            startedAt: episode.started_at,
            endedAt: episode.ended_at,
            symptoms: episode.symptoms ?? [],
            severity: episode.severity,
            notes: episode.notes ?? "",
          }}
        />
      </div>
    </main>
  );
}
