import { EpisodeForm } from "@/components/EpisodeForm";
import { Disclaimer } from "@/components/Disclaimer";
import { NavBar } from "@/components/NavBar";
import { createClient } from "@/lib/supabase/server";
import type { EpisodeWithTiming } from "@/lib/supabase/database.types";

export const dynamic = "force-dynamic";

export default async function EpisodePage() {
  const supabase = await createClient();

  const { data: ongoingRows } = await supabase
    .from("v_episodes")
    .select("*")
    .is("ended_at", null)
    .order("started_at", { ascending: false })
    .limit(1);

  const { data: mealRows } = await supabase
    .from("meals")
    .select("eaten_at")
    .order("eaten_at", { ascending: false })
    .limit(1);

  const ongoing = (ongoingRows as EpisodeWithTiming[] | null)?.[0] ?? null;
  const lastMealAt = (mealRows as Array<{ eaten_at: string }> | null)?.[0]?.eaten_at ?? null;

  const minutesSinceLastMeal = lastMealAt
    ? Math.round((Date.now() - new Date(lastMealAt).getTime()) / 60000)
    : null;

  return (
    <main className="mx-auto w-full max-w-md px-5 pb-28 pt-8">
      <h1 className="text-xl font-semibold text-ink">How are you feeling?</h1>
      <p className="mt-1 text-sm text-ink/60">
        Log it while it&apos;s happening — you can close it off when it passes.
      </p>

      <div className="mt-6">
        <EpisodeForm ongoing={ongoing} minutesSinceLastMeal={minutesSinceLastMeal} />
      </div>

      <Disclaimer />

      <NavBar />
    </main>
  );
}
