/** Groups failed review checks and points each one at the page that can clear it. */

export type CheckFix = {
  section: string;
  note?: string | null;
  anchor?: string | null;
};

export type ReviewCheck = {
  code: string;
  severity: string;
  passed: boolean;
  message: string;
  area?: string;
  fix?: CheckFix | null;
};

export type ReviewGroup = {
  area: string;
  checks: ReviewCheck[];
};

const GROUP_ORDER = [
  "Company details",
  "Disclosures",
  "Comparatives",
  "Sections",
  "Setup",
  "Figures",
  "Other",
] as const;

const FIXES: Record<string, { area: string; fix: CheckFix }> = {
  "V-CO-001": { area: "Company details", fix: { section: "company-details" } },
  "V-CO-002": { area: "Company details", fix: { section: "company-details" } },
  "V-CO-003": { area: "Company details", fix: { section: "company-details" } },
  "V-CO-004": { area: "Company details", fix: { section: "company-details" } },
  "V-CO-005": { area: "Company details", fix: { section: "company-details" } },
  "V-CO-006": { area: "Company details", fix: { section: "company-details" } },
  "V-CO-007": { area: "Company details", fix: { section: "company-details" } },
  "V-CO-008": { area: "Company details", fix: { section: "company-details" } },
  "V-CO-009": { area: "Company details", fix: { section: "company-details" } },
  "V-DISC-001": { area: "Disclosures", fix: { section: "disclosures" } },
  "V-NOTE-001": { area: "Disclosures", fix: { section: "notes" } },
  "V-NOTE-002": { area: "Disclosures", fix: { section: "notes" } },
  "V-NOTE-003": { area: "Disclosures", fix: { section: "notes" } },
  "V-GATE-001": {
    area: "Comparatives",
    fix: { section: "review", anchor: "statutory-first-period-gate" },
  },
  "V-CMP-001": { area: "Comparatives", fix: { section: "sofp" } },
  "V-CMP-002": { area: "Comparatives", fix: { section: "sofp" } },
  "V-SEC-005": { area: "Sections", fix: { section: "sections-setup" } },
  "V-SEC-006": { area: "Sections", fix: { section: "sections-setup" } },
  "V-SEC-007": { area: "Setup", fix: { section: "report-setup" } },
  "V-MAP-001": { area: "Figures", fix: { section: "sub-lines" } },
  "V-TB-001": { area: "Figures", fix: { section: "sofp" } },
  "V-BS-001": { area: "Figures", fix: { section: "sofp" } },
  "V-BANK-001": { area: "Figures", fix: { section: "sofp" } },
  "V-RE-001": { area: "Figures", fix: { section: "income" } },
  "V-FA-001": { area: "Figures", fix: { section: "notes", note: "N2_FA" } },
};

const COMPANY_BLOCKING = new Set([
  "V-CO-001",
  "V-CO-002",
  "V-CO-005",
  "V-CO-006",
  "V-CO-008",
  "V-CO-009",
]);

export function presentCheck(check: ReviewCheck): { area: string; fix: CheckFix } {
  if (check.area && check.fix?.section) {
    return { area: check.area, fix: check.fix };
  }
  return FIXES[check.code] ?? { area: "Other", fix: { section: "review" } };
}

export function disclosureCheckLine(count: number): string {
  if (count === 1) {
    return "1 disclosure question is unanswered.";
  }
  return `${count} disclosure questions are unanswered.`;
}

export function checkLine(check: ReviewCheck, unansweredCount: number): string {
  if (check.code === "V-DISC-001") {
    return disclosureCheckLine(unansweredCount);
  }
  return check.message;
}

export function fixHref(yearEndId: string, fix: CheckFix): string {
  const params = new URLSearchParams({ section: fix.section });
  if (fix.note) {
    params.set("note", fix.note);
  }
  const hash = fix.anchor ? `#${fix.anchor}` : "";
  return `/year-ends/${yearEndId}/draft?${params.toString()}${hash}`;
}

export function groupFailedChecks(checks: readonly ReviewCheck[]): ReviewGroup[] {
  const buckets = new Map<string, ReviewCheck[]>();
  for (const check of checks) {
    if (check.passed) {
      continue;
    }
    const area = presentCheck(check).area;
    const rows = buckets.get(area) ?? [];
    rows.push(check);
    buckets.set(area, rows);
  }
  const ordered = GROUP_ORDER.filter((area) => buckets.has(area));
  return ordered.map((area) => ({ area, checks: buckets.get(area) ?? [] }));
}

export function stopsFinalise(check: ReviewCheck): boolean {
  if (check.passed) {
    return false;
  }
  if (check.severity === "CRITICAL" || check.severity === "BLOCKED") {
    return true;
  }
  return COMPANY_BLOCKING.has(check.code);
}

export function blockingFailureCount(checks: readonly ReviewCheck[]): number {
  return checks.filter(stopsFinalise).length;
}

export function blockingSentence(count: number): string | null {
  if (count <= 0) {
    return null;
  }
  if (count === 1) {
    return "1 check must be fixed";
  }
  return `${count} checks must be fixed`;
}
