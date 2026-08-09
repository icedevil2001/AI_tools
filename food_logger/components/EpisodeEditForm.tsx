"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { deleteEpisode, updateEpisode } from "@/app/history/actions";
import { fromLocalInputValue, toLocalInputValue } from "@/lib/time";

export function EpisodeEditForm({
  episodeId,
  initial,
}: {
  episodeId: string;
  initial: {
    startedAt: string;
    endedAt: string | null;
    symptoms: string[];
    severity: number | null;
    notes: string;
  };
}) {
  const router = useRouter();
  const [startedAt, setStartedAt] = useState(toLocalInputValue(new Date(initial.startedAt)));
  const [stillGoing, setStillGoing] = useState(initial.endedAt === null);
  const [endedAt, setEndedAt] = useState(
    toLocalInputValue(initial.endedAt ? new Date(initial.endedAt) : new Date()),
  );
  const [symptoms, setSymptoms] = useState<string[]>(initial.symptoms);
  const [custom, setCustom] = useState("");
  const [severity, setSeverity] = useState(initial.severity ?? 5);
  const [notes, setNotes] = useState(initial.notes);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [confirmingDelete, setConfirmingDelete] = useState(false);

  function addCustom() {
    const value = custom.trim();
    if (!value || symptoms.includes(value)) return;
    setSymptoms((prev) => [...prev, value]);
    setCustom("");
  }

  async function handleSave() {
    setBusy(true);
    setMessage(null);
    const result = await updateEpisode({
      episodeId,
      startedAt: fromLocalInputValue(startedAt),
      endedAt: stillGoing ? null : fromLocalInputValue(endedAt),
      symptoms,
      severity,
      notes: notes || null,
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
        <h2 className="mb-2 text-sm font-medium text-ink">Symptoms</h2>
        <div className="flex flex-wrap gap-2">
          {symptoms.map((symptom) => (
            <button
              key={symptom}
              type="button"
              onClick={() => setSymptoms((prev) => prev.filter((s) => s !== symptom))}
              aria-label={`Remove ${symptom}`}
              className="rounded-full border border-ink bg-ink px-3.5 py-2 text-sm text-cream"
            >
              {symptom} ×
            </button>
          ))}
          {symptoms.length === 0 && (
            <p className="text-sm text-ink/50">No symptoms — add at least one.</p>
          )}
        </div>

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
            placeholder="Add a symptom"
            aria-label="Add a symptom"
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
          Severity <span className="tabular-nums font-semibold">{severity}</span>/10
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
      </label>

      <label className="block">
        <span className="text-sm font-medium text-ink">Started</span>
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
          <span className="text-sm font-medium text-ink">Still going on</span>
        </label>

        {!stillGoing && (
          <label className="mt-3 block">
            <span className="text-sm font-medium text-ink">Ended</span>
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
        {busy ? "Saving…" : "Save changes"}
      </button>

      {confirmingDelete ? (
        <div className="rounded-xl border border-red-200 bg-red-50 p-4">
          <p className="text-sm text-red-900">Delete this episode for good?</p>
          <div className="mt-3 flex gap-2">
            <button
              type="button"
              onClick={() => deleteEpisode(episodeId)}
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
          Delete this episode
        </button>
      )}
    </div>
  );
}
