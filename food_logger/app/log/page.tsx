import { MealForm } from "@/components/MealForm";
import { Disclaimer } from "@/components/Disclaimer";
import { NavBar } from "@/components/NavBar";
import { createClient } from "@/lib/supabase/server";
import type { MealWithTiming } from "@/lib/supabase/database.types";

export const dynamic = "force-dynamic";

export default async function LogPage() {
  const supabase = await createClient();

  // Read the gap from the view rather than computing it here, so the number
  // shown always matches what the rest of the app derives.
  const { data } = await supabase
    .from("v_meals")
    .select("eaten_at")
    .order("eaten_at", { ascending: false })
    .limit(1);

  const lastMeal = (data as Pick<MealWithTiming, "eaten_at">[] | null)?.[0] ?? null;
  const minutesSinceLastMeal = lastMeal
    ? Math.round((Date.now() - new Date(lastMeal.eaten_at).getTime()) / 60000)
    : null;

  return (
    <main className="mx-auto w-full max-w-md px-5 pb-28 pt-8">
      <h1 className="text-xl font-semibold text-ink">Log a meal</h1>
      <p className="mt-1 text-sm text-ink/60">
        Take a photo and check what the AI found, or type it in yourself.
      </p>

      <div className="mt-6">
        <MealForm minutesSinceLastMeal={minutesSinceLastMeal} />
      </div>

      <Disclaimer />

      <NavBar />
    </main>
  );
}
