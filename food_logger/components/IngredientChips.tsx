"use client";

import { useState } from "react";
import type { IngredientSource } from "@/lib/supabase/database.types";

export interface ChipIngredient {
  name: string;
  source: IngredientSource;
  confidence: number | null;
  quantityNote: string | null;
}

/**
 * Editable review of the ingredient list.
 *
 * The model's output is always shown here for confirmation and never written
 * straight to the database. An unreviewed extraction is worse than no
 * extraction, because it looks like data: this diary is meant to be handed to a
 * doctor, and a hallucinated ingredient is indistinguishable from an observed
 * one once it is stored.
 */
export function IngredientChips({
  ingredients,
  onChange,
}: {
  ingredients: ChipIngredient[];
  onChange: (next: ChipIngredient[]) => void;
}) {
  const [draft, setDraft] = useState("");

  function add() {
    const name = draft.trim();
    if (!name) return;
    onChange([...ingredients, { name, source: "manual", confidence: null, quantityNote: null }]);
    setDraft("");
  }

  function remove(index: number) {
    onChange(ingredients.filter((_, i) => i !== index));
  }

  return (
    <div>
      <div className="flex flex-wrap gap-2">
        {ingredients.map((ingredient, index) => {
          // Anything the model was unsure about is visually distinct, so a
          // guess is never mistaken for an observation at a glance.
          const uncertain =
            ingredient.source === "ai" &&
            ingredient.confidence !== null &&
            ingredient.confidence < 0.6;

          return (
            <span
              key={`${ingredient.name}-${index}`}
              className={[
                "inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-sm",
                uncertain
                  ? "border-dashed border-amber-400 bg-amber-50 text-amber-900"
                  : "border-ink/15 bg-white text-ink",
              ].join(" ")}
            >
              <span>{ingredient.name}</span>

              {ingredient.source === "ai" && ingredient.confidence !== null && (
                <span
                  className="text-xs tabular-nums opacity-60"
                  title={`Model confidence ${(ingredient.confidence * 100).toFixed(0)}%`}
                >
                  {(ingredient.confidence * 100).toFixed(0)}%
                </span>
              )}

              <button
                type="button"
                onClick={() => remove(index)}
                aria-label={`Remove ${ingredient.name}`}
                className="-mr-1 ml-0.5 grid h-6 w-6 place-items-center rounded-full text-base leading-none opacity-50 hover:opacity-100"
              >
                ×
              </button>
            </span>
          );
        })}

        {ingredients.length === 0 && (
          <p className="text-sm text-ink/50">No ingredients yet — add them below.</p>
        )}
      </div>

      <div className="mt-3 flex gap-2">
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              add();
            }
          }}
          placeholder="Add an ingredient"
          aria-label="Add an ingredient"
          className="min-w-0 flex-1 rounded-xl border border-ink/15 bg-white px-4 py-3 text-base outline-none focus:border-ink/40"
        />
        <button
          type="button"
          onClick={add}
          disabled={draft.trim() === ""}
          className="rounded-xl border border-ink/15 bg-white px-4 py-3 text-base font-medium disabled:opacity-40"
        >
          Add
        </button>
      </div>

      {ingredients.some((i) => i.source === "ai") && (
        <p className="mt-2 text-xs text-ink/50">
          Dashed chips are ones the AI wasn&apos;t confident about. Check them before saving.
        </p>
      )}
    </div>
  );
}
