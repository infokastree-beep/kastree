/**
 * Failed checks group by area, and Finalise names how many must be fixed.
 * Run: node --experimental-strip-types --test lib/dashboard-groups.test.ts
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";

import {
  blockingFailureCount,
  blockingSentence,
  checkLine,
  fixHref,
  groupFailedChecks,
  presentCheck,
  severityTag,
  stopsFinalise,
  type ReviewCheck,
} from "./dashboard-groups.ts";

const here = dirname(fileURLToPath(import.meta.url));

function failed(code: string, severity: string, message = code): ReviewCheck {
  return { code, severity, passed: false, message };
}

describe("review groups", () => {
  it("sends each check to the page that can clear it", () => {
    const yearEndId = "year-1";
    const groups = groupFailedChecks([
      failed("V-CO-002", "WARNING", "Registered office has not been recorded."),
      failed("V-DISC-001", "CRITICAL", "Unanswered disclosure questions: ['PENSION_COMMITMENT']"),
      failed("V-GATE-001", "BLOCKED"),
      failed("V-CMP-002", "WARNING"),
      failed("V-SEC-005", "NOTICE"),
      failed("V-SEC-007", "NOTICE"),
      failed("V-MAP-001", "CRITICAL"),
      failed("V-FA-001", "WARNING"),
    ]);
    assert.deepEqual(
      groups.map((group) => group.area),
      [
        "Company details",
        "Disclosures",
        "Comparatives",
        "Sections",
        "Setup",
        "Figures",
      ],
    );
    const byCode = new Map(
      groups.flatMap((group) => group.checks.map((check) => [check.code, check])),
    );
    assert.equal(
      fixHref(yearEndId, { section: "company-details" }),
      "/year-ends/year-1/draft?section=company-details",
    );
    assert.equal(
      fixHref(yearEndId, {
        section: "review",
        anchor: "statutory-first-period-gate",
      }),
      "/year-ends/year-1/draft?section=review#statutory-first-period-gate",
    );
    assert.equal(
      fixHref(yearEndId, { section: "notes", note: "N2_FA" }),
      "/year-ends/year-1/draft?section=notes&note=N2_FA",
    );
    assert.equal(fixHref(yearEndId, { section: "sub-lines" }).includes("sub-lines"), true);
    assert.equal(byCode.has("V-DISC-001"), true);
    assert.equal(
      checkLine(failed("V-DISC-001", "CRITICAL", "Unanswered disclosure questions: ['PENSION_COMMITMENT']"), 40),
      "40 disclosure questions are unanswered.",
    );
    assert.equal(checkLine(failed("V-DISC-001", "CRITICAL"), 1), "1 disclosure question is unanswered.");
  });

  it("counts only the checks that stop finalise", () => {
    const count = blockingFailureCount([
      failed("V-DISC-001", "CRITICAL"),
      failed("V-CO-008", "NOTICE"),
      failed("V-CO-010", "WARNING"),
      failed("V-CO-012", "NOTICE"),
      failed("V-CO-007", "NOTICE"),
      failed("V-SEC-007", "NOTICE"),
      failed("V-FA-001", "WARNING"),
      { code: "V-CO-001", severity: "WARNING", passed: true, message: "ok" },
    ]);
    assert.equal(count, 3);
    assert.equal(blockingSentence(2), "2 checks must be fixed");
    assert.equal(blockingSentence(1), "1 check must be fixed");
    assert.equal(blockingSentence(0), null);
  });

  it("shows each missing directors' confirmation in Review with its own Fix link", () => {
    const yearEndId = "year-1";
    const groups = groupFailedChecks([
      failed("V-CO-022", "WARNING", "excluded"),
      failed("V-CO-023", "WARNING", "notice"),
      failed("V-CO-024", "WARNING", "returns"),
      { code: "V-CO-022", severity: "WARNING", passed: true, message: "recorded" },
    ]);
    assert.deepEqual(
      groups.map((group) => group.area),
      ["Review"],
    );
    assert.equal(groups[0]?.checks.length, 3);
    for (const code of ["V-CO-022", "V-CO-023", "V-CO-024"]) {
      const fix = presentCheck(failed(code, "WARNING")).fix;
      assert.equal(fix.section, "review");
      assert.equal(fix.anchor, "audit-exemption-conditions");
      assert.equal(
        fixHref(yearEndId, fix),
        "/year-ends/year-1/draft?section=review#audit-exemption-conditions",
      );
      assert.equal(stopsFinalise(failed(code, "WARNING")), true);
    }
    assert.equal(
      stopsFinalise({
        code: "V-CO-022",
        severity: "WARNING",
        passed: true,
        message: "recorded",
      }),
      false,
    );
    assert.equal(
      blockingFailureCount([
        failed("V-CO-022", "WARNING"),
        failed("V-CO-023", "WARNING"),
        failed("V-CO-024", "WARNING"),
        failed("V-CO-021", "NOTICE"),
      ]),
      3,
    );
    assert.equal(stopsFinalise(failed("V-CO-025", "NOTICE")), false);
    assert.equal(stopsFinalise(failed("V-CO-026", "NOTICE")), false);
    assert.equal(stopsFinalise(failed("V-CO-027", "NOTICE")), false);
    assert.equal(stopsFinalise(failed("V-CO-029", "WARNING")), true);
    assert.equal(stopsFinalise(failed("V-CO-037", "WARNING")), true);
    assert.equal(stopsFinalise(failed("V-CO-039", "WARNING")), true);
    assert.equal(severityTag(failed("V-CO-039", "WARNING")), "Blocker");
    assert.equal(severityTag(failed("V-CO-012", "NOTICE")), "Notice");
    assert.equal(severityTag(failed("V-DISC-001", "CRITICAL")), "Blocker");
    const compilation = groupFailedChecks([
      failed("V-CO-002", "WARNING"),
      failed("V-CO-038", "WARNING"),
      failed("V-CO-039", "WARNING"),
      failed("V-DISC-001", "CRITICAL"),
      failed("V-CO-012", "NOTICE"),
    ]);
    assert.deepEqual(
      compilation.map((group) => group.area),
      [
        "Company details",
        "Practice letterhead",
        "Compilation report",
        "Disclosures",
      ],
    );
    assert.equal(
      fixHref("year-1", presentCheck(failed("V-CO-039", "WARNING")).fix),
      "/year-ends/year-1/draft?section=compilation&note=compilation-date",
    );
    assert.equal(
      blockingFailureCount([
        failed("V-CO-039", "WARNING"),
        failed("V-CO-012", "NOTICE"),
        failed("V-CO-027", "NOTICE"),
      ]),
      1,
    );
    assert.equal(presentCheck(failed("V-CO-037", "WARNING")).area, "Comparatives");
    assert.equal(
      fixHref("year-1", presentCheck(failed("V-CO-037", "WARNING")).fix),
      "/year-ends/year-1/draft?section=review#statutory-first-period-gate",
    );
    assert.equal(
      presentCheck(failed("V-CO-025", "NOTICE")).fix.section,
      "company-details",
    );
  });
});

describe("review screen", () => {
  it("keeps one wording notice and shows the finalise reason", () => {
    const workspace = readFileSync(
      join(here, "../components/statutory/StatutoryDraftWorkspace.tsx"),
      "utf8",
    );
    assert.match(workspace, /place="workspace-header"/);
    assert.equal(workspace.includes('place="downloads"'), false);
    assert.equal(workspace.includes('place="review-dashboard"'), false);
    assert.equal(workspace.includes("statutory-status-pill"), true);
    assert.match(workspace, /blockingCount=/);
    assert.match(workspace, /<ReviewChecks/);
    const finalise = readFileSync(
      join(here, "../components/statutory/FinaliseDraft.tsx"),
      "utf8",
    );
    assert.match(finalise, /statutory-finalise-reason/);
  });
});
