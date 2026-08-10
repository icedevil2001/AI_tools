import { NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";
import { formatCsvDate, formatCsvTime } from "@/lib/time";
import { toCsv } from "@/lib/export/csv";
import type { EpisodeWithTiming, MealWithTiming } from "@/lib/supabase/database.types";

export const dynamic = "force-dynamic";

interface IngredientLink {
  meal_id: string;
  ingredients: { name: string } | null;
}

interface Row {
  at: string;
  type: "Meal" | "Symptom episode";
  details: string;
  severity: number | null;
  portionSize: string | null;
  notes: string | null;
  minutesSincePrevious: number | null;
  minutesSinceLastMeal: number | null;
}

/**
 * Every meal and symptom episode as one chronological CSV, meant to be handed
 * to a doctor -- so it favours plain sortable columns over the app's own
 * mobile-first, most-recent-first grouping.
 */
export async function GET() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) {
    return NextResponse.json({ error: "Not signed in." }, { status: 401 });
  }

  const [{ data: meals }, { data: episodes }] = await Promise.all([
    supabase.from("v_meals").select("*").order("eaten_at", { ascending: true }),
    supabase.from("v_episodes").select("*").order("started_at", { ascending: true }),
  ]);

  const mealRows = (meals as MealWithTiming[] | null) ?? [];
  const episodeRows = (episodes as EpisodeWithTiming[] | null) ?? [];
  const mealIds = mealRows.map((m) => m.id);

  const { data: links } = mealIds.length
    ? await supabase.from("meal_ingredients").select("meal_id, ingredients(name)").in("meal_id", mealIds)
    : { data: [] as IngredientLink[] };

  const ingredientsByMeal = new Map<string, string[]>();
  for (const link of (links as IngredientLink[] | null) ?? []) {
    if (!link.ingredients?.name) continue;
    const list = ingredientsByMeal.get(link.meal_id) ?? [];
    list.push(link.ingredients.name);
    ingredientsByMeal.set(link.meal_id, list);
  }

  const rows: Row[] = [
    ...mealRows.map(
      (m): Row => ({
        at: m.eaten_at,
        type: "Meal",
        details: (ingredientsByMeal.get(m.id) ?? []).join("; "),
        severity: null,
        portionSize: m.portion_size,
        notes: m.notes,
        minutesSincePrevious: m.minutes_since_previous_meal,
        minutesSinceLastMeal: null,
      }),
    ),
    ...episodeRows.map(
      (e): Row => ({
        at: e.started_at,
        type: "Symptom episode",
        details: e.symptoms.join("; "),
        severity: e.severity,
        portionSize: null,
        notes: e.notes,
        minutesSincePrevious: e.minutes_since_previous_episode,
        minutesSinceLastMeal: e.minutes_since_last_meal,
      }),
    ),
  ].sort((a, b) => new Date(a.at).getTime() - new Date(b.at).getTime());

  const csv = toCsv(
    [
      "Date",
      "Time",
      "Type",
      "Details",
      "Severity (1-10)",
      "Portion size",
      "Notes",
      "Minutes since previous same-type entry",
      "Minutes since last meal",
    ],
    rows.map((r) => [
      formatCsvDate(r.at),
      formatCsvTime(r.at),
      r.type,
      r.details,
      r.severity,
      r.portionSize,
      r.notes,
      r.minutesSincePrevious,
      r.minutesSinceLastMeal,
    ]),
  );

  // UTF-8 BOM so Excel on Windows renders accented characters correctly
  // instead of guessing the wrong codepage.
  return new NextResponse("\uFEFF" + csv, {
    headers: {
      "Content-Type": "text/csv; charset=utf-8",
      "Content-Disposition": `attachment; filename="food-symptom-log-${formatCsvDate(new Date().toISOString())}.csv"`,
    },
  });
}
