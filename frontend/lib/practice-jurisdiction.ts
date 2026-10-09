/** Practice country. New companies use its currency. Existing companies stay as they are. */

export const JURISDICTION_HINT =
  "New companies default to this country's currency";

export type PracticeJurisdiction = "IE" | "GB" | null;

export function canEditPracticeJurisdiction(
  role: string | null | undefined,
): boolean {
  return role === "owner" || role === "admin";
}

/** The settings save sends only the practice country. */
export function jurisdictionUpdateBody(
  value: PracticeJurisdiction,
): { jurisdiction: PracticeJurisdiction } {
  return { jurisdiction: value };
}
