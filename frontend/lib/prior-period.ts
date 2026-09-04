/** Shared helpers for choosing which prior trial balance to compare against. */

const STORAGE_PREFIX = "kastree:preferred-prior-tb";

export function preferredPriorStorageKey(
  companyId: string,
  periodEnd: string,
): string {
  return `${STORAGE_PREFIX}:${companyId}:${periodEnd}`;
}

export function readPreferredPriorTbId(
  companyId: string,
  periodEnd: string,
): string | null {
  if (typeof window === "undefined") return null;
  try {
    const value = window.localStorage.getItem(
      preferredPriorStorageKey(companyId, periodEnd),
    );
    return value && value.length > 0 ? value : null;
  } catch {
    return null;
  }
}

export function writePreferredPriorTbId(
  companyId: string,
  periodEnd: string,
  priorTbId: string | null,
): void {
  if (typeof window === "undefined") return;
  const key = preferredPriorStorageKey(companyId, periodEnd);
  try {
    if (!priorTbId) {
      window.localStorage.removeItem(key);
      return;
    }
    window.localStorage.setItem(key, priorTbId);
  } catch {
    // Ignore quota / private-mode failures — preference is best-effort.
  }
}

export type PriorTbOption = {
  id: string;
  period_end: string;
  status: string;
};

/** Priors strictly before periodEnd, newest first (same rule as Variance auto-detect). */
export function filterPriorTbOptions(
  items: PriorTbOption[],
  periodEnd: string,
  excludeTbId?: string,
): PriorTbOption[] {
  return items
    .filter(
      (tb) =>
        tb.period_end < periodEnd &&
        (!excludeTbId || tb.id !== excludeTbId),
    )
    .sort((a, b) => (a.period_end < b.period_end ? 1 : -1));
}
