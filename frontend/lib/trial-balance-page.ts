/**
 * Copy and links for the read-only Inputs > Trial balance page.
 * The page does not adopt, delete, or show amounts.
 */

export const NO_TRIAL_BALANCE_SELECTED = "No trial balance is selected.";

export const FILE_NAME_NOT_RECORDED = "File name was not recorded.";

export const FACE_DATES_SENTENCE =
  "Report setup face dates only change the words printed on the face. They do not change this period.";

const MONTHS = [
  "January",
  "February",
  "March",
  "April",
  "May",
  "June",
  "July",
  "August",
  "September",
  "October",
  "November",
  "December",
] as const;

export type TrialBalancePage = {
  trial_balance_id: string | null;
  period_start: string | null;
  period_end: string | null;
  uploaded_at: string | null;
  account_count: number | null;
  currency: string | null;
  file_name: string | null;
};

export function recordedFileName(fileName: string | null): string {
  if (fileName == null || fileName === "") return FILE_NAME_NOT_RECORDED;
  return fileName;
}

export function adoptableTrialBalanceLabel(item: {
  period_end: string;
  file_name: string | null;
  account_count: number;
  currency: string | null;
}): string {
  const currency = item.currency ? ` · ${item.currency}` : "";
  return `${item.period_end} · ${recordedFileName(item.file_name)} · ${item.account_count} accounts${currency}`;
}

export function statementsHref(trialBalanceId: string): string {
  return `/dashboard/${encodeURIComponent(trialBalanceId)}/statements?tab=Statutory`;
}

export function formatPeriodDate(iso: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  if (!match) return iso;
  const month = MONTHS[Number(match[2]) - 1];
  if (!month) return iso;
  return `${Number(match[3])} ${month} ${match[1]}`;
}

export function formatUploadedAt(iso: string): string {
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) return iso;
  return new Intl.DateTimeFormat("en-IE", {
    timeZone: "UTC",
    year: "numeric",
    month: "long",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).format(parsed);
}
