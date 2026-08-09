/**
 * Time formatting and the local <-> UTC boundary.
 *
 * Everything is stored as `timestamptz` (an absolute instant) and rendered in
 * the viewer's local zone. `<input type="datetime-local">` is the one place
 * that boundary is easy to get wrong: it produces and consumes a wall-clock
 * string with no zone, so it must be converted explicitly in both directions.
 * Getting this wrong silently corrupts every derived interval.
 */

/** `Date` -> the "YYYY-MM-DDTHH:mm" a datetime-local input expects, in local time. */
export function toLocalInputValue(date: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return (
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}` +
    `T${pad(date.getHours())}:${pad(date.getMinutes())}`
  );
}

/**
 * The value of a datetime-local input -> an ISO-8601 string with offset.
 *
 * `new Date("2026-08-09T13:30")` is parsed as local time by every current
 * engine, which is what we want; `toISOString()` then converts to UTC for
 * storage.
 */
export function fromLocalInputValue(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    throw new Error(`Invalid date/time: ${value}`);
  }
  return parsed.toISOString();
}

/** Human-readable duration, e.g. 275 -> "4h 35m". */
export function formatGap(minutes: number | null): string {
  if (minutes === null || Number.isNaN(minutes)) return "—";
  if (minutes < 1) return "less than a minute";

  const hours = Math.floor(minutes / 60);
  const mins = Math.round(minutes % 60);

  if (hours === 0) return `${mins}m`;
  if (mins === 0) return `${hours}h`;
  return `${hours}h ${mins}m`;
}

const dateTimeFormat = new Intl.DateTimeFormat(undefined, {
  weekday: "short",
  day: "numeric",
  month: "short",
  hour: "numeric",
  minute: "2-digit",
});

const timeFormat = new Intl.DateTimeFormat(undefined, {
  hour: "numeric",
  minute: "2-digit",
});

export function formatDateTime(iso: string): string {
  return dateTimeFormat.format(new Date(iso));
}

export function formatTime(iso: string): string {
  return timeFormat.format(new Date(iso));
}
