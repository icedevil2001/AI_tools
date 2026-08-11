"use server";

import { revalidatePath } from "next/cache";
import { z } from "zod";
import { setMealIngredients, type IngredientInput } from "@/lib/ingredients/upsert";
import { createClient, createServiceRoleClient } from "@/lib/supabase/server";

const IngredientInputSchema = z.object({
  name: z.string().min(1).max(120),
  source: z.enum(["ai", "manual"]),
  confidence: z.number().min(0).max(1).nullable().optional(),
  quantityNote: z.string().max(200).nullable().optional(),
});

const SaveMealSchema = z.object({
  eatenAt: z.string().datetime({ offset: true }),
  portionSize: z.string().max(80).nullable().optional(),
  notes: z.string().max(2000).nullable().optional(),
  ingredients: z.array(IngredientInputSchema).max(60),
  /** Unedited model response, persisted for audit. Absent for manual entries. */
  extraction: z.object({ model: z.string(), raw: z.unknown() }).nullable().optional(),
});

export type SaveMealInput = z.input<typeof SaveMealSchema>;

export interface SaveMealResult {
  ok: boolean;
  mealId?: string;
  error?: string;
}

export async function saveMeal(input: SaveMealInput): Promise<SaveMealResult> {
  const parsed = SaveMealSchema.safeParse(input);
  if (!parsed.success) {
    return { ok: false, error: parsed.error.issues.map((i) => i.message).join("; ") };
  }

  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) return { ok: false, error: "Not signed in." };

  const { eatenAt, portionSize, notes, ingredients, extraction } = parsed.data;

  const { data: meal, error: mealError } = await supabase
    .from("meals")
    .insert({
      user_id: user.id,
      eaten_at: eatenAt,
      portion_size: portionSize || null,
      notes: notes || null,
    })
    .select("id")
    .single();

  if (mealError || !meal) {
    return { ok: false, error: mealError?.message ?? "Could not save that meal." };
  }

  try {
    await setMealIngredients(supabase, meal.id, ingredients as IngredientInput[]);
  } catch (error) {
    // The meal row exists but has no ingredients. Remove it rather than leaving
    // a meal that silently records nothing about what was eaten -- an empty
    // meal in the diary is worse than a failed save the user can retry.
    await supabase.from("meals").delete().eq("id", meal.id);
    return { ok: false, error: (error as Error).message };
  }

  if (extraction) {
    // The audit row is strictly secondary to the meal, which is already saved
    // by this point. Everything here is inside try/catch because
    // createServiceRoleClient() *throws* when SUPABASE_SERVICE_ROLE_KEY is
    // missing or blank -- guarding only the insert's error result would let
    // that exception escape and report failure for a meal that was in fact
    // written, prompting the user to log it again and create a duplicate.
    try {
      // Written with the service role because clients have no insert policy on
      // ai_extractions -- an audit record of what the model said should not be
      // forgeable from the browser.
      const admin = createServiceRoleClient();
      const { error: auditError } = await admin.from("ai_extractions").insert({
        meal_id: meal.id,
        model: extraction.model,
        raw: extraction.raw ?? {},
      });
      if (auditError) {
        console.error("[saveMeal] failed to write ai_extractions:", auditError.message);
      }
    } catch (error) {
      console.error(
        "[saveMeal] could not write the extraction audit row; the meal itself saved fine:",
        (error as Error).message,
      );
    }
  }

  revalidatePath("/history");
  revalidatePath("/log");
  return { ok: true, mealId: meal.id };
}

const SetPhotoSchema = z.object({
  mealId: z.string().uuid(),
  photoPath: z.string().min(1).max(400),
});

/**
 * Record the storage path of a photo the client has already uploaded.
 *
 * Split from saveMeal because the object path contains the meal id, so the
 * meal must exist before the upload can be addressed.
 */
export async function setMealPhoto(input: z.input<typeof SetPhotoSchema>) {
  const parsed = SetPhotoSchema.safeParse(input);
  if (!parsed.success) return { ok: false, error: "Invalid photo reference." };

  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) return { ok: false, error: "Not signed in." };

  // The path must sit under this user's prefix. RLS on storage.objects already
  // enforces this for the upload itself; checking again here stops a crafted
  // request from pointing a meal row at someone else's object.
  if (!parsed.data.photoPath.startsWith(`${user.id}/`)) {
    return { ok: false, error: "Invalid photo path." };
  }

  const { error } = await supabase
    .from("meals")
    .update({ photo_path: parsed.data.photoPath })
    .eq("id", parsed.data.mealId)
    .eq("user_id", user.id);

  if (error) return { ok: false, error: error.message };

  revalidatePath("/history");
  return { ok: true };
}
