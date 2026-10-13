export const DIRECTORS_RESPONSIBILITIES_WORDING =
  "The directors are responsible for preparing the company's financial statements and for being satisfied that they give a true and fair view. The directors are responsible for keeping adequate accounting records and for safeguarding the assets of the company and for taking reasonable steps for the prevention and detection of fraud and other irregularities.";

export function DirectorsResponsibilitiesPanel() {
  return (
    <section
      className="max-w-3xl space-y-2 rounded-md border border-line bg-surface-elevated p-4"
      data-testid="directors-responsibilities-source"
    >
      <h2 className="text-sm font-semibold uppercase tracking-[0.12em] text-soft">
        Directors&apos; responsibilities statement
      </h2>
      <p className="text-sm font-semibold text-ink">source not confirmed</p>
      <p className="text-sm text-ink-secondary">
        {DIRECTORS_RESPONSIBILITIES_WORDING}
      </p>
    </section>
  );
}
