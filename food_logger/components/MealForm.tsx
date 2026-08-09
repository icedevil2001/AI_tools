"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { saveMeal, setMealPhoto } from "@/app/log/actions";
import { prepareImage } from "@/lib/image";
import { createClient } from "@/lib/supabase/client";
import { IngredientChips, type ChipIngredient } from "./IngredientChips";
import { formatGap, toLocalInputValue, fromLocalInputValue } from "@/lib/time";

type Phase = "idle" | "analyzing" | "saving";

export function MealForm({ minutesSinceLastMeal }: { minutesSinceLastMeal: number | null }) {
  const router = useRouter();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [phase, setPhase] = useState<Phase>("idle");
  const [ingredients, setIngredients] = useState<ChipIngredient[]>([]);
  const [eatenAt, setEatenAt] = useState(() => toLocalInputValue(new Date()));
  const [portionSize, setPortionSize] = useState("");
  const [notes, setNotes] = useState("");
  const [preview, setPreview] = useState<string | null>(null);
  const [photoBlob, setPhotoBlob] = useState<Blob | null>(null);
  const [extraction, setExtraction] = useState<{ model: string; raw: unknown } | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  async function handleFile(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    setMessage(null);
    setPhase("analyzing");

    try {
      const prepared = await prepareImage(file);
      setPreview(prepared.dataUrl);
      setPhotoBlob(prepared.blob);

      const res = await fetch("/api/analyze-photo", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ imageDataUrl: prepared.dataUrl }),
      });
      const body = await res.json();

      if (!res.ok) {
        // Degrade to manual entry. The photo is still kept and saved, so the
        // record is not lost just because the model was unavailable.
        setMessage(body.error ?? "Couldn't read that photo. Add the ingredients yourself.");
        return;
      }

      setExtraction({ model: body.model, raw: body.raw });
      setIngredients(
        (body.ingredients as Array<{ name: string; confidence: number; quantity_note?: string | null }>).map(
          (i) => ({
            name: i.name,
            source: "ai" as const,
            confidence: i.confidence,
            quantityNote: i.quantity_note ?? null,
          }),
        ),
      );
      if (body.ingredients.length === 0) {
        setMessage("The AI didn't find any food in that photo. Add the ingredients yourself.");
      }
    } catch (error) {
      setMessage((error as Error).message);
    } finally {
      setPhase("idle");
      // Allow re-picking the same file, which otherwise fires no change event.
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }

  async function handleSave() {
    if (ingredients.length === 0) {
      setMessage("Add at least one ingredient before saving.");
      return;
    }
    setPhase("saving");
    setMessage(null);

    const result = await saveMeal({
      eatenAt: fromLocalInputValue(eatenAt),
      portionSize: portionSize || null,
      notes: notes || null,
      ingredients: ingredients.map((i) => ({
        name: i.name,
        source: i.source,
        confidence: i.confidence,
        quantityNote: i.quantityNote,
      })),
      extraction,
    });

    if (!result.ok || !result.mealId) {
      setPhase("idle");
      setMessage(result.error ?? "Could not save that meal.");
      return;
    }

    // Upload the photo after the meal exists, because the object path contains
    // the meal id. A failed upload does not discard the meal -- the ingredients
    // are the data that matters; the photo is a convenience.
    if (photoBlob) {
      try {
        const supabase = createClient();
        const {
          data: { user },
        } = await supabase.auth.getUser();
        if (user) {
          const path = `${user.id}/${result.mealId}.jpg`;
          const { error } = await supabase.storage
            .from("meal-photos")
            .upload(path, photoBlob, { contentType: "image/jpeg", upsert: true });
          if (!error) await setMealPhoto({ mealId: result.mealId, photoPath: path });
        }
      } catch {
        // Non-fatal, as above.
      }
    }

    router.push("/history");
    router.refresh();
  }

  const busy = phase !== "idle";

  return (
    <div className="space-y-6">
      {minutesSinceLastMeal !== null && (
        <p className="rounded-xl bg-white px-4 py-3 text-sm text-ink/70">
          It&apos;s been <span className="font-medium text-ink">{formatGap(minutesSinceLastMeal)}</span>{" "}
          since your last logged meal.
        </p>
      )}

      <div>
        <input
          ref={fileInputRef}
          type="file"
          accept="image/*"
          capture="environment"
          onChange={handleFile}
          className="sr-only"
          id="meal-photo"
        />
        <label
          htmlFor="meal-photo"
          className="flex cursor-pointer items-center justify-center rounded-2xl border-2 border-dashed border-ink/20 bg-white px-4 py-8 text-center text-base font-medium text-ink/70"
        >
          {phase === "analyzing" ? "Reading the photo…" : preview ? "Retake photo" : "Take a photo"}
        </label>

        {preview && (
          // eslint-disable-next-line @next/next/no-img-element -- a local data URI, not a remote asset
          <img
            src={preview}
            alt="The meal being logged"
            className="mt-3 max-h-64 w-full rounded-2xl object-cover"
          />
        )}
        <p className="mt-2 text-center text-xs text-ink/50">
          A photo is optional — you can log everything by hand.
        </p>
      </div>

      <section>
        <h2 className="mb-2 text-sm font-medium text-ink">Ingredients</h2>
        <IngredientChips ingredients={ingredients} onChange={setIngredients} />
      </section>

      <div className="grid gap-4">
        <label className="block">
          <span className="text-sm font-medium text-ink">When</span>
          <input
            type="datetime-local"
            value={eatenAt}
            onChange={(e) => setEatenAt(e.target.value)}
            className="mt-1 w-full rounded-xl border border-ink/15 bg-white px-4 py-3 outline-none focus:border-ink/40"
          />
        </label>

        <label className="block">
          <span className="text-sm font-medium text-ink">Portion (optional)</span>
          <input
            value={portionSize}
            onChange={(e) => setPortionSize(e.target.value)}
            placeholder="e.g. large bowl, half a plate"
            className="mt-1 w-full rounded-xl border border-ink/15 bg-white px-4 py-3 outline-none focus:border-ink/40"
          />
        </label>

        <label className="block">
          <span className="text-sm font-medium text-ink">Notes (optional)</span>
          <textarea
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            rows={3}
            placeholder="Anything worth remembering — where you ate, how hungry you were, how you felt."
            className="mt-1 w-full rounded-xl border border-ink/15 bg-white px-4 py-3 outline-none focus:border-ink/40"
          />
        </label>
      </div>

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
        {phase === "saving" ? "Saving…" : "Save meal"}
      </button>
    </div>
  );
}
