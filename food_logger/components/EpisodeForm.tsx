"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { endEpisode, saveEpisode } from "@/app/episode/actions";
import { formatGap, fromLocalInputValue, toLocalInputValue } from "@/lib/time";
import type { EpisodeWithTiming } from "@/lib/supabase/database.types";

/**
 * Common symptoms as quick-tap options. Free text stays available because a
 * fixed list would quietly discourage recording anything not on it.
 */
const COMMON_SYMPTOMS = [
  "Brain fog",
  "Lightheaded",
  "Dizzy",
  "Fatigue",
  "Nausea",
  "Headache",
  "Racing heart",
  "Sweating",
  "Bloating",
  "Shaky",
];

export function EpisodeForm({
  ongoing,
  minutesSinceLastMeal,
}: {
  ongoing: EpisodeWithTiming | null;
  minutesSinceLastMeal: number | null;
}) {
  const router = useRouter();

  const [symptoms, setSymptoms] = useState<string[]>([]);
  const [custom, setCustom] = useState("");
  const [severity, setSeverity] = useState(5);
  const [startedAt, setStartedAt] = useState(() => toLocalInputValue(new Date()));
  const [stillGoing, setStillGoing] = useState(true);
  const [endedAt, setEndedAt] = useState(() => toLocalInputValue(new Date()));
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  function toggle(symptom: string) {
    setSymptoms((prev) =>
      prev.includes(symptom) ? prev.filter((s) => s !== symptom) : [...prev, symptom],
    );
  }

  function addCustom() {
    const value = custom.trim();
    if (!value || symptoms.includes(value)) return;
    setSymptoms((prev) => [...prev, value]);
    setCustom("");
  }

  async function handleEndOngoing() {
    if (!ongoing) return;
    setBusy(true);
    const result = await endEpisode({
      episodeId: ongoing.id,
      endedAt: new Date().toISOString(),
    });
    setBusy(false);
    if (!result.ok) {
      setMessage(result.error ?? "Could not end that episode.");
      return;
    }
    router.refresh();
  }

  async function handleSave() {
    if (symptoms.length === 0) {
      setMessage("Pick at least one symptom.");
      return;
    }
    setBusy(true);
    setMessage(null);

    const result = await saveEpisode({
      startedAt: fromLocalInputValue(startedAt),
      endedAt: stillGoing ? null : fromLocalInputValue(endedAt),
      symptoms,
      severity,
      notes: notes || null,
    });

    setBusy(false);
    if (!result.ok) {
      setMessage(result.error ?? "Could not save that.");
      return;
    }
    router.push("/history");
    router.refresh();
  }

  // An episode already in progress takes over the screen: the useful action is
  // to close it, not to start a second one on top.
  if (ongoing) {
    return (
      <div className="space-y-5">
        <div className="rounded-2xl border border-amber-300 bg-amber-50 p-5">
          <p className="text-sm font-medium text-amber-900">An episode is in progress</p>
          <p className="mt-1 text-sm text-amber-900/80">
            Started {formatGap(Math.round((Date.now() - new Date(ongoing.started_at).getTime()) / 60000))}{" "}
            ago
            {ongoing.symptoms.length > 0 && <> — {ongoing.symptoms.join(", ")}</>}.
          </p>

          <button
            type="button"
            onClick={handleEndOngoing}
            disabled={busy}
            className="mt-4 w-full rounded-xl bg-ink px-4 py-3 text-base font-medium text-cream disabled:opacity-40"
          >
            {busy ? "Saving…" : "It's over now"}
          </button>
        </div>

        {message && (
          <p role="alert" className="rounded-xl bg-red-50 px-4 py-3 text-sm text-red-800">
            {message}
          </p>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {minutesSinceLastMeal !== null && (
        <p className="rounded-xl bg-white px-4 py-3 text-sm text-ink/70">
          Your last logged meal was{" "}
          <span className="font-medium text-ink">{formatGap(minutesSinceLastMeal)}</span> ago.
        </p>
      )}

      <section>
        <h2 className="mb-2 text-sm font-medium text-ink">What are you feeling?</h2>
        <div className="flex flex-wrap gap-2">
          {COMMON_SYMPTOMS.map((symptom) => {
            const selected = symptoms.includes(symptom);
            return (
              <button
                key={symptom}
                type="button"
                aria-pressed={selected}
                onClick={() => toggle(symptom)}
                className={[
                  "rounded-full border px-3.5 py-2 text-sm",
                  selected
                    ? "border-ink bg-ink text-cream"
                    : "border-ink/15 bg-white text-ink",
                ].join(" ")}
              >
                {symptom}
              </button>
            );
          })}
        </div>

        {symptoms.filter((s) => !COMMON_SYMPTOMS.includes(s)).length > 0 && (
          <div className="mt-2 flex flex-wrap gap-2">
            {symptoms
              .filter((s) => !COMMON_SYMPTOMS.includes(s))
              .map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => toggle(s)}
                  className="rounded-full border border-ink bg-ink px-3.5 py-2 text-sm text-cream"
                >
                  {s} ×
                </button>
              ))}
          </div>
        )}

        <div className="mt-3 flex gap-2">
          <input
            value={custom}
            onChange={(e) => setCustom(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                addCustom();
              }
            }}
            placeholder="Something else"
            aria-label="Add another symptom"
            className="min-w-0 flex-1 rounded-xl border border-ink/15 bg-white px-4 py-3 outline-none focus:border-ink/40"
          />
          <button
            type="button"
            onClick={addCustom}
            disabled={custom.trim() === ""}
            className="rounded-xl border border-ink/15 bg-white px-4 py-3 font-medium disabled:opacity-40"
          >
            Add
          </button>
        </div>
      </section>

      <label className="block">
        <span className="text-sm font-medium text-ink">
          How bad is it? <span className="tabular-nums font-semibold">{severity}</span>/10
        </span>
        <input
          type="range"
          min={1}
          max={10}
          step={1}
          value={severity}
          onChange={(e) => setSeverity(Number(e.target.value))}
          className="mt-3 w-full accent-ink"
        />
        <span className="flex justify-between text-xs text-ink/50">
          <span>Barely there</span>
          <span>Unbearable</span>
        </span>
      </label>

      <label className="block">
        <span className="text-sm font-medium text-ink">When did it start?</span>
        <input
          type="datetime-local"
          value={startedAt}
          onChange={(e) => setStartedAt(e.target.value)}
          className="mt-1 w-full rounded-xl border border-ink/15 bg-white px-4 py-3 outline-none focus:border-ink/40"
        />
      </label>

      <div>
        <label className="flex items-center gap-3">
          <input
            type="checkbox"
            checked={stillGoing}
            onChange={(e) => setStillGoing(e.target.checked)}
            className="h-5 w-5 accent-ink"
          />
          <span className="text-sm font-medium text-ink">It&apos;s still going on</span>
        </label>
        <p className="mt-1 text-xs text-ink/50">
          Leave this ticked and you can close it with one tap when it passes.
        </p>

        {!stillGoing && (
          <label className="mt-3 block">
            <span className="text-sm font-medium text-ink">When did it stop?</span>
            <input
              type="datetime-local"
              value={endedAt}
              onChange={(e) => setEndedAt(e.target.value)}
              className="mt-1 w-full rounded-xl border border-ink/15 bg-white px-4 py-3 outline-none focus:border-ink/40"
            />
          </label>
        )}
      </div>

      <label className="block">
        <span className="text-sm font-medium text-ink">Notes (optional)</span>
        <textarea
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          rows={3}
          placeholder="What you were doing, whether standing up brought it on, anything else."
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
        disabled={busy || symptoms.length === 0}
        className="w-full rounded-xl bg-ink px-4 py-4 text-base font-medium text-cream disabled:opacity-40"
      >
        {busy ? "Saving…" : "Save"}
      </button>
    </div>
  );
}
