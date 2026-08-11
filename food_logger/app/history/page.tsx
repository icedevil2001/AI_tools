import Link from "next/link";
import { NavBar } from "@/components/NavBar";
import { createClient } from "@/lib/supabase/server";
import { formatDateTime, formatGap, formatTime } from "@/lib/time";
import type { EpisodeWithTiming, MealWithTiming } from "@/lib/supabase/database.types";

export const dynamic = "force-dynamic";

interface IngredientLink {
  meal_id: string;
  source: "ai" | "manual";
  confidence: number | null;
  ingredients: { name: string } | null;
}

interface MealRow extends MealWithTiming {
  meal_ingredients: IngredientLink[];
}

type TimelineEntry =
  | { kind: "meal"; at: string; meal: MealRow }
  | { kind: "episode"; at: string; episode: EpisodeWithTiming };

export default async function HistoryPage() {
  const supabase = await createClient();

  // Timing comes from the views so the intervals shown here are the same ones
  // every other surface derives.
  //
  // Ingredients are fetched separately rather than embedded in the v_meals
  // select: PostgREST can only embed a related table through a view when it
  // manages to infer the foreign key, which is not guaranteed. Joining in
  // application code costs one extra round trip and removes that dependency
  // entirely.
  const [{ data: meals }, { data: episodes }] = await Promise.all([
    supabase.from("v_meals").select("*").order("eaten_at", { ascending: false }).limit(100),
    supabase.from("v_episodes").select("*").order("started_at", { ascending: false }).limit(100),
  ]);

  const mealIds = ((meals as MealWithTiming[] | null) ?? []).map((m) => m.id);

  const { data: links } = mealIds.length
    ? await supabase
        .from("meal_ingredients")
        .select("meal_id, source, confidence, ingredients(name)")
        .in("meal_id", mealIds)
    : { data: [] as IngredientLink[] };

  const ingredientsByMeal = new Map<string, IngredientLink[]>();
  for (const link of (links as IngredientLink[] | null) ?? []) {
    const list = ingredientsByMeal.get(link.meal_id) ?? [];
    list.push(link);
    ingredientsByMeal.set(link.meal_id, list);
  }

  const entries: TimelineEntry[] = [
    ...((meals as MealWithTiming[] | null) ?? []).map(
      (row): TimelineEntry => ({
        kind: "meal",
        at: row.eaten_at,
        meal: { ...row, meal_ingredients: ingredientsByMeal.get(row.id) ?? [] },
      }),
    ),
    ...((episodes as EpisodeWithTiming[] | null) ?? []).map(
      (episode): TimelineEntry => ({ kind: "episode", at: episode.started_at, episode }),
    ),
  ].sort((a, b) => new Date(b.at).getTime() - new Date(a.at).getTime());

  return (
    <main className="mx-auto w-full max-w-md px-5 pb-28 pt-8">
      <div className="flex items-baseline justify-between gap-3">
        <h1 className="text-xl font-semibold text-ink">History</h1>
        <a href="/api/export" className="shrink-0 text-sm font-medium underline">
          Export CSV
        </a>
      </div>
      <p className="mt-1 text-sm text-ink/60">Most recent first.</p>

      {entries.length === 0 ? (
        <div className="mt-10 rounded-2xl border border-dashed border-ink/20 p-8 text-center">
          <p className="text-sm text-ink/60">Nothing logged yet.</p>
          <Link href="/log" className="mt-3 inline-block text-sm font-medium underline">
            Log your first meal
          </Link>
        </div>
      ) : (
        <ol className="mt-6 space-y-3">
          {entries.map((entry) =>
            entry.kind === "meal" ? (
              <MealCard key={`meal-${entry.meal.id}`} meal={entry.meal} />
            ) : (
              <EpisodeCard key={`ep-${entry.episode.id}`} episode={entry.episode} />
            ),
          )}
        </ol>
      )}

      <p className="mt-10 text-xs leading-relaxed text-ink/50">
        Gaps between meals are worked out from the times you logged, so they&apos;re only as
        accurate as the log — a meal you didn&apos;t record will stretch the gap after it.
      </p>

      <NavBar />
    </main>
  );
}

function MealCard({ meal }: { meal: MealRow }) {
  const names = meal.meal_ingredients
    .map((mi) => mi.ingredients?.name)
    .filter((n): n is string => Boolean(n));

  return (
    <li className="rounded-2xl bg-white p-4">
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-sm font-medium text-ink">{formatDateTime(meal.eaten_at)}</span>
        {meal.minutes_since_previous_meal !== null && (
          <span className="shrink-0 text-xs text-ink/50">
            {formatGap(meal.minutes_since_previous_meal)} after the last
          </span>
        )}
      </div>

      <p className="mt-1.5 text-sm text-ink/80">
        {names.length > 0 ? names.join(", ") : <span className="text-ink/40">No ingredients</span>}
      </p>

      {meal.portion_size && <p className="mt-1 text-xs text-ink/50">Portion: {meal.portion_size}</p>}
      {meal.notes && <p className="mt-1 text-xs text-ink/50">{meal.notes}</p>}

      <Link
        href={`/history/meal/${meal.id}`}
        className="mt-2 inline-block text-xs font-medium underline"
      >
        Edit
      </Link>
    </li>
  );
}

function EpisodeCard({ episode }: { episode: EpisodeWithTiming }) {
  return (
    <li className="rounded-2xl border border-amber-200 bg-amber-50 p-4">
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-sm font-medium text-amber-950">
          {formatDateTime(episode.started_at)}
          {episode.ended_at && <> – {formatTime(episode.ended_at)}</>}
        </span>
        <span className="shrink-0 text-xs text-amber-900/70">
          {episode.is_ongoing ? "ongoing" : formatGap(episode.duration_minutes)}
        </span>
      </div>

      <p className="mt-1.5 text-sm text-amber-950">
        {episode.symptoms.join(", ")}
        {episode.severity !== null && (
          <span className="ml-2 text-xs opacity-70">severity {episode.severity}/10</span>
        )}
      </p>

      {episode.minutes_since_last_meal !== null && (
        <p className="mt-1 text-xs text-amber-900/70">
          {formatGap(episode.minutes_since_last_meal)} after a meal
        </p>
      )}

      {episode.notes && <p className="mt-1 text-xs text-amber-900/70">{episode.notes}</p>}

      <Link
        href={`/history/episode/${episode.id}`}
        className="mt-2 inline-block text-xs font-medium underline"
      >
        Edit
      </Link>
    </li>
  );
}
