/**
 * The workspace shows the API sentence and can point at Sub-line review.
 * Run: node --experimental-strip-types --test lib/workspace-load-error.test.ts
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";
import { sublineGapAccount } from "./workspace-load-error.ts";

describe("sublineGapAccount", () => {
  it("names the account inside the exact API sentence", () => {
    const message =
      "Product 1 line 'operating_expenses' on 'Operating Expenses' needs a statutory sub-line";
    assert.equal(sublineGapAccount(message), "Operating Expenses");
    assert.equal(
      sublineGapAccount(
        "Product 1 line 'director_loan' on 'Director's current account' needs a statutory sub-line",
      ),
      "Director's current account",
    );
    assert.equal(sublineGapAccount("Trial balance is not confirmed"), null);
  });

  it("the workspace prints that sentence and links to Sub-line review", () => {
    const here = dirname(fileURLToPath(import.meta.url));
    const workspace = readFileSync(
      join(here, "../components/statutory/StatutoryDraftWorkspace.tsx"),
      "utf8",
    );
    const notice = readFileSync(
      join(here, "../components/statutory/StatutoryLoadError.tsx"),
      "utf8",
    );
    assert.equal(workspace.includes("statutory-dashboard-error"), true);
    assert.equal(workspace.includes("statutory-statements-error"), true);
    assert.equal(workspace.includes('selectSection("sub-lines")'), true);
    assert.equal(notice.includes("statutory-subline-review-link"), true);
    assert.equal(notice.includes("sublineGapAccount"), true);
    assert.equal(notice.includes("{message}"), true);
  });
});
