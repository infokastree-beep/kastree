/** Copy for the trial-balance upload dates. The general ledger keeps its own control. */

export const ACCOUNTING_PERIOD_SENTENCE =
  "These dates are the accounting period. Statutory accounts use them as the period. They cannot be edited later. To correct them, upload another trial balance and adopt it from Inputs > Trial balance.";

export const PRE_2026_WARNING =
  "This period starts before 1 January 2026. The Irish statutory pack cannot use it. Management accounts remain available.";

export const PRE_2026_EXPLANATION =
  "The Irish statutory pack applies to periods beginning on or after 1 January 2026. A trial balance that starts earlier can still be used for management accounts. It cannot be adopted into a statutory draft.";

export const PERIOD_TOO_LONG =
  "This period is longer than 18 months. Statutory accounts will use these dates.";

export const PACK_EFFECTIVE_FROM = "2026-01-01";

function addMonths(iso: string, months: number): string | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  if (!match) return null;
  const start = new Date(Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3])));
  const monthIndex = start.getUTCMonth() + months;
  const year = start.getUTCFullYear() + Math.floor(monthIndex / 12);
  const month = ((monthIndex % 12) + 12) % 12;
  const last = new Date(Date.UTC(year, month + 1, 0)).getUTCDate();
  const day = Math.min(start.getUTCDate(), last);
  const anniversary = new Date(Date.UTC(year, month, day));
  return anniversary.toISOString().slice(0, 10);
}

export function periodLongerThan18Months(periodStart: string, periodEnd: string): boolean {
  const anniversary = addMonths(periodStart, 18);
  if (anniversary == null) return false;
  return periodEnd >= anniversary;
}

export function periodStartsBeforePack(periodStart: string): boolean {
  return periodStart !== "" && periodStart < PACK_EFFECTIVE_FROM;
}
