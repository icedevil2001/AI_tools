/**
 * Shown wherever the app could be mistaken for offering an answer. The tool
 * records what happened and when; it does not interpret it, and the
 * time-based associations it surfaces are correlations, not causes.
 */
export function Disclaimer() {
  return (
    <p className="mt-10 text-xs leading-relaxed text-ink/50">
      This is a diary to help you and your doctor spot patterns. It isn&apos;t medical advice
      and can&apos;t diagnose anything. If you feel very unwell, contact a doctor.
    </p>
  );
}
