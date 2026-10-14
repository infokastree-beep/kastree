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
  adoptableTrialBalanceLabel,
  formatPeriodDate,
  recordedFileName,
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
    assert.match(panel, /recordedFileName/);
    assert.equal(recordedFileName(null), "File name was not recorded.");
    assert.equal(recordedFileName(""), "File name was not recorded.");
    assert.equal(recordedFileName("year-end.xlsx"), "year-end.xlsx");
    assert.equal(
      adoptableTrialBalanceLabel({
        period_end: "2026-12-31",
        file_name: "year-end.xlsx",
        account_count: 24,
        currency: "EUR",
      }),
      "2026-12-31 · year-end.xlsx · 24 accounts · EUR",
    );
    assert.equal(
      adoptableTrialBalanceLabel({
        period_end: "2026-12-31",
        file_name: null,
        account_count: 2,
        currency: null,
      }),
      "2026-12-31 · File name was not recorded. · 2 accounts",
    );
    const workbench = readFileSync(
      join(here, "../components/statutory/StatutoryWorkbench.tsx"),
      "utf8",
    );
    assert.match(workbench, /adoptableTrialBalanceLabel/);
    assert.match(panel, /FACE_DATES_SENTENCE/);
    assert.match(panel, /Open in Statements/);
    const upload = readFileSync(join(here, "../components/upload/UploadForm.tsx"), "utf8");
    assert.match(upload, /ACCOUNTING_PERIOD_SENTENCE/);
    assert.match(upload, /tb-pre-2026-explanation/);
    assert.match(upload, /tb-period-too-long/);
    const period = readFileSync(join(here, "./upload-period.ts"), "utf8");
    assert.match(period, /Statutory accounts use them as the period/);
    assert.match(period, /Management accounts remain available/);
    assert.match(period, /longer than 18 months/);
    const switched = readFileSync(
      join(here, "../components/statutory/TrialBalanceSwitch.tsx"),
      "utf8",
    );
    assert.match(switched, /trial-balance\/adopt/);
    assert.match(switched, /recordedFileName/);
    assert.equal(panel.includes("method: \"POST\""), false);
    assert.equal(panel.includes("Delete"), false);
  });
});
