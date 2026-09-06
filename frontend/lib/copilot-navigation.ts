/**
 * Option A citation navigation helpers.
 *
 * Citations resolve to a page (dashboard | statements), optional statements
 * tab, and a DOM anchor id. Cross-page hops use URL ?cite=&tab= params so
 * deep links and Ask chips share one path.
 */

export type CopilotCitePage = "dashboard" | "statements";

export type StatementsTab =
  | "SOPL"
  | "SOFP"
  | "SOCIE"
  | "Variance"
  | "Risk";

export type CopilotNavigateTarget = {
  page: CopilotCitePage;
  tab?: StatementsTab;
  anchorId: string;
};

function applyCiteFlash(el: HTMLElement): void {
  el.scrollIntoView({ behavior: "smooth", block: "center" });
  el.classList.remove("copilot-cite-flash");
  // Force reflow so re-clicking the same chip retriggers the flash.
  void el.offsetWidth;
  el.classList.add("copilot-cite-flash");
}

/**
 * Scroll + highlight a cite anchor. Retries briefly so late-mounting
 * Dashboard/Statements sections (async health/performance/variance) still flash.
 */
export function flashCiteAnchor(
  anchorId: string,
  delayMs = 0,
  retryMs = 2500,
): void {
  window.setTimeout(() => {
    const started = Date.now();
    const attempt = (): void => {
      const el = document.getElementById(anchorId);
      if (el) {
        applyCiteFlash(el);
        return;
      }
      if (Date.now() - started >= retryMs) return;
      window.setTimeout(attempt, 100);
    };
    attempt();
  }, delayMs);
}

export function dashboardPath(tbId: string): string {
  return `/dashboard/${tbId}`;
}

export function statementsPath(tbId: string): string {
  return `/dashboard/${tbId}/statements`;
}

/** Build a cite deep-link for cross-page (or refreshable) navigation. */
export function citeHref(
  tbId: string,
  target: CopilotNavigateTarget,
): string {
  const base =
    target.page === "dashboard"
      ? dashboardPath(tbId)
      : statementsPath(tbId);
  const params = new URLSearchParams();
  params.set("cite", target.anchorId);
  if (target.tab) params.set("tab", target.tab);
  return `${base}?${params.toString()}`;
}

export function parseStatementsTab(
  value: string | null | undefined,
): StatementsTab | null {
  if (
    value === "SOPL" ||
    value === "SOFP" ||
    value === "SOCIE" ||
    value === "Variance" ||
    value === "Risk"
  ) {
    return value;
  }
  return null;
}
