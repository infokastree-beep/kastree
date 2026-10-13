/**
 * Directors' report inputs cite the Act. A later-year length notice does not
 * stop a final draft. A missing accounting-records location does.
 * Run: node --experimental-strip-types --test lib/directors-report-items.test.ts
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";
import { stopsFinalise, type ReviewCheck } from "./dashboard-groups.ts";

const here = dirname(fileURLToPath(import.meta.url));

function failed(code: string, severity: string): ReviewCheck {
  return { code, severity, passed: false, message: "missing" };
}

describe("directors' report items", () => {
  it("keeps the researched citation and the reviewer-to-confirm checks", () => {
    const pack = JSON.parse(
      readFileSync(
        join(here, "../../findraft/content/frs102-1a-ie/2024.09/pack.json"),
        "utf8",
      ),
    ) as {
      directors_report_items: {
        source_status: string;
        dividends: string;
        share_interests: string;
        own_shares: string;
      };
      data_checks: { source_status: string };
    };
    const form = readFileSync(
      join(here, "../components/statutory/DirectorsReportForm.tsx"),
      "utf8",
    );
    const workspace = readFileSync(
      join(here, "../components/statutory/StatutoryDraftWorkspace.tsx"),
      "utf8",
    );
    assert.equal(
      pack.directors_report_items.source_status,
      "researched (public source)",
    );
    assert.equal(pack.data_checks.source_status, "reviewer-to-confirm");
    assert.equal(
      pack.directors_report_items.dividends,
      "Companies Act 2014, section 326(1)(d)",
    );
    assert.equal(
      pack.directors_report_items.share_interests,
      "Companies Act 2014, section 329",
    );
    assert.equal(
      pack.directors_report_items.own_shares,
      "Companies Act 2014, section 328",
    );
    assert.match(form, /data-testid="directors-report-inputs"/);
    assert.match(form, /data-testid="directors-report-location"/);
    assert.match(form, /data-testid="directors-report-interim"/);
    assert.match(form, /data-testid="directors-report-recommended"/);
    assert.match(form, /data-testid="directors-report-add-person"/);
    assert.match(form, /Not recorded/);
    assert.match(form, /Enter 0\.00 if none was paid/);
    assert.equal(form.includes("Approved by the board"), false);
    assert.match(workspace, /\/directors-report/);
    assert.equal(stopsFinalise(failed("V-CO-027", "NOTICE")), false);
    assert.equal(stopsFinalise(failed("V-CO-029", "WARNING")), true);
    assert.equal(stopsFinalise(failed("V-CO-004", "WARNING")), true);
    assert.equal(
      stopsFinalise({
        code: "V-CO-029",
        severity: "WARNING",
        passed: true,
        message: "recorded",
      }),
      false,
    );
  });
});
