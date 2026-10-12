/**
 * The signing rule is shown beside the directors the preparer ticks.
 * Run: node --experimental-strip-types --test lib/two-signatories.test.ts
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));

describe("two signatories", () => {
  it("states the sole-director rule on the company details form", () => {
    const pack = JSON.parse(
      readFileSync(
        join(here, "../../findraft/content/frs102-1a-ie/2024.09/pack.json"),
        "utf8",
      ),
    ) as {
      board_signatures: { source_status: string };
      data_checks: { source_status: string };
    };
    const form = readFileSync(
      join(here, "../components/statutory/CompanyDetailsForm.tsx"),
      "utf8",
    );
    assert.equal(
      pack.board_signatures.source_status,
      "researched (public source)",
    );
    assert.equal(pack.data_checks.source_status, "reviewer-to-confirm");
    assert.match(form, /data-testid="company-signing-rule"/);
    assert.match(form, /A sole director signs alone/);
    assert.match(form, /two must sign the balance sheet and the directors/);
  });
});
