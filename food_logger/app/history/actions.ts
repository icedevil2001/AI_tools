"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { z } from "zod";
import { setMealIngredients, type IngredientInput } from "@/lib/ingredients/upsert";
import { createClient } from "@/lib/supabase/server";

const UpdateMealSchema = z.object({
  mealId: z.string().uuid(),
  eatenAt: z.string().datetime({ offset: true }),
  portionSize: z.string().max(80).nullable().optional(),
  notes: z.string().max(2000).nullable().optional(),
  ingredients: z
    .array(
      z.object({
        name: z.string().min(1).max(120),
        source: z.enum(["ai", "manual"]),
        confidence: z.number().min(0).max(1).nullable().optional(),
        quantityNote: z.string().max(200).nullable().optional(),
      }),
    )
    .max(60),
});

/**
 * Edit a logged meal.
 *
 * Correcting `eaten_at` is expected -- people log late. Nothing here
 * recalculates gaps, because nothing stores them: the timing views recompute
 * from these timestamps on the next read.
 */
export async function updateMeal(input: z.input<typeof UpdateMealSchema>) {
  const parsed = UpdateMealSchema.safeParse(input);
  if (!parsed.success) {
    return { ok: false, error: parsed.error.issues.map((i) => i.message).join("; ") };
  }

  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) return { ok: false, error: "Not signed in." };

  const { mealId, eatenAt, portionSize, notes, ingredients } = parsed.data;

  if (ingredients.length === 0) {
    return { ok: false, error: "A meal needs at least one ingredient." };
  }

  const { error } = await supabase
    .from("meals")
    .update({
      eaten_at: eatenAt,
      portion_size: portionSize || null,
      notes: notes || null,
    })
    .eq("id", mealId)
    .eq("user_id", user.id);

  if (error) return { ok: false, error: error.message };

  try {
    await setMealIngredients(supabase, mealId, ingredients as IngredientInput[]);
  } catch (e) {
    return { ok: false, error: (e as Error).message };
  }

  revalidatePath("/history");
  return { ok: true };
}

export async function deleteMeal(mealId: string) {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) return { ok: false, error: "Not signed in." };

  // meal_ingredients and ai_extractions cascade. The stored photo does not, so
  // remove it explicitly rather than leaving an orphan in the bucket.
  const { data: meal } = await supabase
    .from("meals")
    .select("photo_path")
    .eq("id", mealId)
    .eq("user_id", user.id)
    .single();

  if (meal?.photo_path) {
    await supabase.storage.from("meal-photos").remove([meal.photo_path]);
  }

  const { error } = await supabase.from("meals").delete().eq("id", mealId).eq("user_id", user.id);
  if (error) return { ok: false, error: error.message };

  revalidatePath("/history");
  redirect("/history");
}

const UpdateEpisodeSchema = z.object({
  episodeId: z.string().uuid(),
  startedAt: z.string().datetime({ offset: true }),
  endedAt: z.string().datetime({ offset: true }).nullable().optional(),
  symptoms: z.array(z.string().min(1).max(60)).max(20),
  severity: z.number().int().min(1).max(10).nullable().optional(),
  notes: z.string().max(2000).nullable().optional(),
});

export async function updateEpisode(input: z.input<typeof UpdateEpisodeSchema>) {
  const parsed = UpdateEpisodeSchema.safeParse(input);
  if (!parsed.success) {
    return { ok: false, error: parsed.error.issues.map((i) => i.message).join("; ") };
  }

  const { episodeId, startedAt, endedAt, symptoms, severity, notes } = parsed.data;

  if (endedAt && new Date(endedAt) < new Date(startedAt)) {
    return { ok: false, error: "The episode can't end before it started." };
  }
  if (symptoms.length === 0) {
    return { ok: false, error: "An episode needs at least one symptom." };
  }

  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) return { ok: false, error: "Not signed in." };

  const { error } = await supabase
    .from("episodes")
    .update({
      started_at: startedAt,
      ended_at: endedAt ?? null,
      symptoms,
      severity: severity ?? null,
      notes: notes || null,
    })
    .eq("id", episodeId)
    .eq("user_id", user.id);

  if (error) return { ok: false, error: error.message };

  revalidatePath("/history");
  return { ok: true };
}

export async function deleteEpisode(episodeId: string) {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) return { ok: false, error: "Not signed in." };

  const { error } = await supabase
    .from("episodes")
    .delete()
    .eq("id", episodeId)
    .eq("user_id", user.id);

  if (error) return { ok: false, error: error.message };

  revalidatePath("/history");
  redirect("/history");
}
