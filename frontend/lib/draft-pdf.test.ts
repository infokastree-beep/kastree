/**
 * The adopted draft PDF is fetched with the bearer token through /backend-api.
 * Run: node --experimental-strip-types --test lib/draft-pdf.test.ts
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";
import { messageFromPdfBody, pdfBlockReason } from "./workspace-load-error.ts";

const here = dirname(fileURLToPath(import.meta.url));

describe("pdfBlockReason", () => {
  it("uses the dashboard conditions in plain English", () => {
    assert.equal(
      pdfBlockReason({
        statementsError:
          "Product 1 line 'operating_expenses' on 'Operating Expenses' needs a statutory sub-line",
        dashboardError: null,
        renderable: null,
        checks: [],
      }),
      "Confirm the sub-line for Operating Expenses first",
    );
    assert.equal(
      pdfBlockReason({
        statementsError: null,
        dashboardError: null,
        renderable: false,
        checks: [
          {
            code: "V-GATE-001",
            passed: false,
            message: "Prior-year data not validated — reconciliation blocked",
          },
        ],
      }),
      "Mark the first financial period first",
    );
    assert.equal(
      pdfBlockReason({
        statementsError: "Company not found",
        dashboardError: null,
        renderable: null,
        checks: [],
      }),
      "Company not found",
    );
    assert.equal(
      pdfBlockReason({
        statementsError: null,
        dashboardError: null,
        renderable: true,
        checks: [],
      }),
      null,
    );
  });
});

describe("messageFromPdfBody", () => {
  it("keeps the server sentence and drops a bare status", () => {
    assert.equal(
      messageFromPdfBody({ detail: "Statutory statements are not renderable" }),
      "Statutory statements are not renderable",
    );
    assert.equal(messageFromPdfBody({ detail: "API 400" }), null);
    assert.equal(messageFromPdfBody("not json"), null);
  });
});

describe("adopted draft download", () => {
  it("calls the adopted PDF route with a bearer token, not a bare link", () => {
    const workspace = readFileSync(
      join(here, "../components/statutory/StatutoryDraftWorkspace.tsx"),
      "utf8",
    );
    const helper = readFileSync(join(here, "draft-pdf.ts"), "utf8");
    assert.equal(
      workspace.includes(
        "`/year-ends/${yearEndId}/adopted-trial-balance/statements.pdf`",
      ),
      true,
    );
    assert.equal(workspace.includes("downloadDraftPdf"), true);
    assert.equal(workspace.includes("statutory-download"), true);
    assert.equal(workspace.includes("statutory-download-reason"), true);
    assert.equal(workspace.includes('sectionId === "draft-pdf"'), true);
    assert.equal(workspace.includes("statutory-outputs"), true);
    assert.equal(workspace.includes("window.open"), false);
    assert.equal(workspace.includes("statements.pdf\""), false);
    assert.equal(helper.includes('headers: { Authorization: `Bearer ${token}` }'), true);
    assert.equal(helper.includes("getApiBaseUrl()"), true);
    assert.equal(helper.includes("window.open"), false);
    assert.equal(helper.includes("API ${"), false);
  });
});
