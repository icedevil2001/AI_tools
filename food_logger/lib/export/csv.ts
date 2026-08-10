/**
 * Minimal CSV serialization: quote-wraps any field containing a comma, quote,
 * or newline and doubles embedded quotes. Enough for Excel/Sheets/Numbers,
 * the only consumers this needs to satisfy.
 */
function csvField(value: string | number | null | undefined): string {
  const s = value === null || value === undefined ? "" : String(value);
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

export function toCsv(
  headers: string[],
  rows: Array<Array<string | number | null | undefined>>,
): string {
  const lines = [headers.map(csvField).join(",")];
  for (const row of rows) {
    lines.push(row.map(csvField).join(","));
  }
  // CRLF is what RFC 4180 and Excel both expect.
  return lines.join("\r\n") + "\r\n";
}
