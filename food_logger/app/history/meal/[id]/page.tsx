import Link from "next/link";
import { notFound } from "next/navigation";
import { MealEditForm } from "@/components/MealEditForm";
import { createClient } from "@/lib/supabase/server";
import type { ChipIngredient } from "@/components/IngredientChips";

export const dynamic = "force-dynamic";

export default async function EditMealPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const supabase = await createClient();

  // No user_id filter needed -- RLS restricts this to the signed-in user's own
  // rows, so a meal belonging to someone else simply returns nothing.
  const { data: meal } = await supabase
    .from("meals")
    .select("*, meal_ingredients(source, confidence, quantity_note, ingredients(name))")
    .eq("id", id)
    .single();

  if (!meal) notFound();

  const ingredients: ChipIngredient[] = (
    meal.meal_ingredients as Array<{
      source: "ai" | "manual";
      confidence: number | null;
      quantity_note: string | null;
      ingredients: { name: string } | null;
    }>
  )
    .filter((mi) => mi.ingredients)
    .map((mi) => ({
      name: mi.ingredients!.name,
      source: mi.source,
      confidence: mi.confidence,
      quantityNote: mi.quantity_note,
    }));

  return (
    <main className="mx-auto w-full max-w-md px-5 pb-16 pt-8">
      <Link href="/history" className="text-sm text-ink/60 underline">
        ← Back to history
      </Link>
      <h1 className="mt-3 text-xl font-semibold text-ink">Edit meal</h1>

      <div className="mt-6">
        <MealEditForm
          mealId={meal.id}
          initial={{
            eatenAt: meal.eaten_at,
            portionSize: meal.portion_size ?? "",
            notes: meal.notes ?? "",
            ingredients,
          }}
        />
      </div>
    </main>
  );
}
