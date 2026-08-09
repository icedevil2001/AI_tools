"use server";

import { revalidatePath } from "next/cache";
import { z } from "zod";
import { createClient } from "@/lib/supabase/server";

const SaveEpisodeSchema = z.object({
  startedAt: z.string().datetime({ offset: true }),
  /** Null means the episode is still going on. */
  endedAt: z.string().datetime({ offset: true }).nullable().optional(),
  symptoms: z.array(z.string().min(1).max(60)).max(20),
  severity: z.number().int().min(1).max(10).nullable().optional(),
  notes: z.string().max(2000).nullable().optional(),
});

export type SaveEpisodeInput = z.input<typeof SaveEpisodeSchema>;

export async function saveEpisode(input: SaveEpisodeInput) {
  const parsed = SaveEpisodeSchema.safeParse(input);
  if (!parsed.success) {
    return { ok: false, error: parsed.error.issues.map((i) => i.message).join("; ") };
  }

  const { startedAt, endedAt, symptoms, severity, notes } = parsed.data;

  // Checked here as well as by the DB constraint so the user gets a sentence
  // rather than a Postgres error string.
  if (endedAt && new Date(endedAt) < new Date(startedAt)) {
    return { ok: false, error: "The episode can't end before it started." };
  }

  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) return { ok: false, error: "Not signed in." };

  const { data, error } = await supabase
    .from("episodes")
    .insert({
      user_id: user.id,
      started_at: startedAt,
      ended_at: endedAt ?? null,
      symptoms,
      severity: severity ?? null,
      notes: notes || null,
    })
    .select("id")
    .single();

  if (error) return { ok: false, error: error.message };

  revalidatePath("/history");
  revalidatePath("/episode");
  return { ok: true, episodeId: data.id };
}

const EndEpisodeSchema = z.object({
  episodeId: z.string().uuid(),
  endedAt: z.string().datetime({ offset: true }),
});

/**
 * Close an ongoing episode.
 *
 * The one-tap counterpart to logging a start while it is happening -- which is
 * the whole reason `ended_at` is nullable rather than a required duration
 * guessed after the fact.
 */
export async function endEpisode(input: z.input<typeof EndEpisodeSchema>) {
  const parsed = EndEpisodeSchema.safeParse(input);
  if (!parsed.success) return { ok: false, error: "Invalid request." };

  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) return { ok: false, error: "Not signed in." };

  const { data: existing, error: readError } = await supabase
    .from("episodes")
    .select("started_at")
    .eq("id", parsed.data.episodeId)
    .eq("user_id", user.id)
    .single();

  if (readError || !existing) return { ok: false, error: "Episode not found." };

  if (new Date(parsed.data.endedAt) < new Date(existing.started_at)) {
    return { ok: false, error: "The episode can't end before it started." };
  }

  const { error } = await supabase
    .from("episodes")
    .update({ ended_at: parsed.data.endedAt })
    .eq("id", parsed.data.episodeId)
    .eq("user_id", user.id);

  if (error) return { ok: false, error: error.message };

  revalidatePath("/history");
  revalidatePath("/episode");
  return { ok: true };
}
