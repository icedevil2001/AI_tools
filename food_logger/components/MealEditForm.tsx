"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { deleteMeal, updateMeal } from "@/app/history/actions";
import { fromLocalInputValue, toLocalInputValue } from "@/lib/time";
import { IngredientChips, type ChipIngredient } from "./IngredientChips";

export function MealEditForm({
  mealId,
  initial,
}: {
  mealId: string;
  initial: {
    eatenAt: string;
    portionSize: string;
    notes: string;
    ingredients: ChipIngredient[];
  };
}) {
  const router = useRouter();
  const [eatenAt, setEatenAt] = useState(toLocalInputValue(new Date(initial.eatenAt)));
  const [portionSize, setPortionSize] = useState(initial.portionSize);
  const [notes, setNotes] = useState(initial.notes);
  const [ingredients, setIngredients] = useState<ChipIngredient[]>(initial.ingredients);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [confirmingDelete, setConfirmingDelete] = useState(false);

  async function handleSave() {
    setBusy(true);
    setMessage(null);
    const result = await updateMeal({
      mealId,
      eatenAt: fromLocalInputValue(eatenAt),
      portionSize: portionSize || null,
      notes: notes || null,
      ingredients: ingredients.map((i) => ({
        name: i.name,
        source: i.source,
        confidence: i.confidence,
        quantityNote: i.quantityNote,
      })),
    });
    setBusy(false);
    if (!result.ok) {
      setMessage(result.error ?? "Could not save.");
      return;
    }
    router.push("/history");
    router.refresh();
  }

  return (
    <div className="space-y-6">
      <section>
        <h2 className="mb-2 text-sm font-medium text-ink">Ingredients</h2>
        <IngredientChips ingredients={ingredients} onChange={setIngredients} />
      </section>

      <label className="block">
        <span className="text-sm font-medium text-ink">When</span>
        <input
          type="datetime-local"
          value={eatenAt}
          onChange={(e) => setEatenAt(e.target.value)}
          className="mt-1 w-full rounded-xl border border-ink/15 bg-white px-4 py-3 outline-none focus:border-ink/40"
        />
        <span className="mt-1 block text-xs text-ink/50">
          Correcting this also corrects the gaps calculated around it.
        </span>
      </label>

      <label className="block">
        <span className="text-sm font-medium text-ink">Portion (optional)</span>
        <input
          value={portionSize}
          onChange={(e) => setPortionSize(e.target.value)}
          className="mt-1 w-full rounded-xl border border-ink/15 bg-white px-4 py-3 outline-none focus:border-ink/40"
        />
      </label>

      <label className="block">
        <span className="text-sm font-medium text-ink">Notes (optional)</span>
        <textarea
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          rows={3}
          className="mt-1 w-full rounded-xl border border-ink/15 bg-white px-4 py-3 outline-none focus:border-ink/40"
        />
      </label>

      {message && (
        <p role="alert" className="rounded-xl bg-amber-50 px-4 py-3 text-sm text-amber-900">
          {message}
        </p>
      )}

      <button
        type="button"
        onClick={handleSave}
        disabled={busy || ingredients.length === 0}
        className="w-full rounded-xl bg-ink px-4 py-4 text-base font-medium text-cream disabled:opacity-40"
      >
        {busy ? "Saving…" : "Save changes"}
      </button>

      {confirmingDelete ? (
        <div className="rounded-xl border border-red-200 bg-red-50 p-4">
          <p className="text-sm text-red-900">Delete this meal for good?</p>
          <div className="mt-3 flex gap-2">
            <button
              type="button"
              onClick={() => deleteMeal(mealId)}
              className="flex-1 rounded-xl bg-red-700 px-4 py-3 text-sm font-medium text-white"
            >
              Delete
            </button>
            <button
              type="button"
              onClick={() => setConfirmingDelete(false)}
              className="flex-1 rounded-xl border border-ink/15 bg-white px-4 py-3 text-sm font-medium"
            >
              Keep it
            </button>
          </div>
        </div>
      ) : (
        <button
          type="button"
          onClick={() => setConfirmingDelete(true)}
          className="w-full text-sm text-red-700 underline"
        >
          Delete this meal
        </button>
      )}
    </div>
  );
}
