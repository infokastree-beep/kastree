/**
 * Read-only trial balance page copy. No amounts and no adopt control.
 * Run: node --experimental-strip-types --test lib/trial-balance-page.test.ts
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";
import {
  FACE_DATES_SENTENCE,
  FILE_NAME_NOT_RECORDED,
  NO_TRIAL_BALANCE_SELECTED,
  formatPeriodDate,
  formatUploadedAt,
  statementsHref,
} from "./trial-balance-page.ts";

describe("trial balance page", () => {
  it("links to Statements and formats the period without shifting the day", () => {
    assert.equal(
      statementsHref("11111111-1111-1111-1111-111111111111"),
      "/dashboard/11111111-1111-1111-1111-111111111111/statements?tab=Statutory",
    );
    assert.equal(formatPeriodDate("2026-01-01"), "1 January 2026");
    assert.equal(formatPeriodDate("2026-12-31"), "31 December 2026");
    assert.match(formatUploadedAt("2026-03-02T10:15:00Z"), /2 March 2026/);
    assert.match(formatUploadedAt("2026-03-02T10:15:00Z"), /10:15/);
  });

  it("states the empty file name, the empty selection, and the face-date limit", () => {
    assert.equal(NO_TRIAL_BALANCE_SELECTED, "No trial balance is selected.");
    assert.equal(FILE_NAME_NOT_RECORDED, "File name was not recorded.");
    assert.equal(
      FACE_DATES_SENTENCE,
      "Report setup face dates only change the words printed on the face. They do not change this period.",
    );
    const here = dirname(fileURLToPath(import.meta.url));
    const panel = readFileSync(
      join(here, "../components/statutory/TrialBalancePanel.tsx"),
      "utf8",
    );
    assert.match(panel, /NO_TRIAL_BALANCE_SELECTED/);
    assert.match(panel, /FILE_NAME_NOT_RECORDED/);
    assert.match(panel, /FACE_DATES_SENTENCE/);
    assert.match(panel, /Open in Statements/);
    assert.equal(panel.includes("method: \"POST\""), false);
    assert.equal(panel.includes("Delete"), false);
  });
});
