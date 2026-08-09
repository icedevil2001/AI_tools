import type { SupabaseClient } from "@supabase/supabase-js";
import type { Ingredient, IngredientSource } from "@/lib/supabase/database.types";
import { displayName, normalizeIngredient } from "./normalize";

/** One ingredient as it arrives from either the AI path or the manual form. */
export interface IngredientInput {
  name: string;
  source: IngredientSource;
  /** Model confidence 0-1. Only meaningful when source is "ai". */
  confidence?: number | null;
  quantityNote?: string | null;
}

export interface ResolvedIngredient {
  ingredientId: string;
  normalizedName: string;
  source: IngredientSource;
  confidence: number | null;
  quantityNote: string | null;
}

/**
 * Resolve free-text ingredient names to rows in `foodlog.ingredients`,
 * creating any that do not exist yet.
 *
 * This is the single chokepoint through which every ingredient must pass.
 * Writing free text straight into `meal_ingredients` would defeat the entire
 * point of the canonical dictionary, so there is deliberately no other way to
 * attach an ingredient to a meal.
 *
 * Inputs that normalize to null (blank, punctuation, or nothing but
 * preparation words) are dropped rather than stored as empty rows. Duplicates
 * within a single call are collapsed, since `meal_ingredients` is keyed on
 * (meal_id, ingredient_id) and would otherwise raise a conflict.
 */
export async function resolveIngredients(
  supabase: SupabaseClient,
  inputs: IngredientInput[],
): Promise<ResolvedIngredient[]> {
  // Collapse duplicates by canonical key, keeping the first occurrence. When a
  // duplicate pair disagrees, prefer the manual one -- a person correcting the
  // model should win over the model.
  const byKey = new Map<string, { input: IngredientInput; normalized: string }>();

  for (const input of inputs) {
    const normalized = normalizeIngredient(input.name);
    if (!normalized) continue;

    const existing = byKey.get(normalized);
    if (!existing) {
      byKey.set(normalized, { input, normalized });
    } else if (existing.input.source === "ai" && input.source === "manual") {
      byKey.set(normalized, { input, normalized });
    }
  }

  if (byKey.size === 0) return [];

  const keys = [...byKey.keys()];

  // Insert every key, ignoring the ones already present. `ignoreDuplicates`
  // makes this safe to run concurrently: two devices logging "chicken" at the
  // same time cannot produce two rows, because normalized_name is unique.
  const { error: insertError } = await supabase
    .from("ingredients")
    .upsert(
      [...byKey.values()].map(({ input, normalized }) => ({
        name: displayName(input.name),
        normalized_name: normalized,
      })),
      { onConflict: "normalized_name", ignoreDuplicates: true },
    );

  if (insertError) {
    throw new Error(`Failed to upsert ingredients: ${insertError.message}`);
  }

  // Read back to get ids. Done as a separate select rather than relying on the
  // upsert's returned rows, because with ignoreDuplicates the rows that already
  // existed are not returned.
  const { data: rows, error: selectError } = await supabase
    .from("ingredients")
    .select("id, name, normalized_name")
    .in("normalized_name", keys);

  if (selectError) {
    throw new Error(`Failed to read back ingredients: ${selectError.message}`);
  }

  const idByKey = new Map<string, string>(
    (rows ?? []).map((r: Pick<Ingredient, "id" | "normalized_name">) => [
      r.normalized_name,
      r.id,
    ]),
  );

  const resolved: ResolvedIngredient[] = [];
  for (const [normalized, { input }] of byKey) {
    const ingredientId = idByKey.get(normalized);
    if (!ingredientId) {
      // Should be unreachable: we just inserted these. Fail loudly rather than
      // silently dropping an ingredient the user believes they logged.
      throw new Error(`Ingredient "${normalized}" was not found after upsert.`);
    }
    resolved.push({
      ingredientId,
      normalizedName: normalized,
      source: input.source,
      // A DB constraint rejects confidence on manual rows; enforce it here too
      // so the failure is a clear no-op rather than a 400 from PostgREST.
      confidence: input.source === "ai" ? (input.confidence ?? null) : null,
      quantityNote: input.quantityNote ?? null,
    });
  }

  return resolved;
}

/**
 * Replace a meal's ingredient list with exactly `inputs`.
 *
 * Used by both the initial save and later edits. Deleting first means an
 * ingredient the user removed during review actually disappears, rather than
 * lingering because the write was append-only.
 */
export async function setMealIngredients(
  supabase: SupabaseClient,
  mealId: string,
  inputs: IngredientInput[],
): Promise<ResolvedIngredient[]> {
  const resolved = await resolveIngredients(supabase, inputs);

  const { error: deleteError } = await supabase
    .from("meal_ingredients")
    .delete()
    .eq("meal_id", mealId);

  if (deleteError) {
    throw new Error(`Failed to clear meal ingredients: ${deleteError.message}`);
  }

  if (resolved.length === 0) return [];

  const { error: linkError } = await supabase.from("meal_ingredients").insert(
    resolved.map((r) => ({
      meal_id: mealId,
      ingredient_id: r.ingredientId,
      source: r.source,
      confidence: r.confidence,
      quantity_note: r.quantityNote,
    })),
  );

  if (linkError) {
    throw new Error(`Failed to link ingredients to meal: ${linkError.message}`);
  }

  return resolved;
}
