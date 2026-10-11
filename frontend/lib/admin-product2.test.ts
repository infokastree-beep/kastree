/**
 * The admin organisations table shows Product 2 and posts grant or revoke.
 * Run: node --experimental-strip-types --test lib/admin-product2.test.ts
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));

describe("admin product 2 access", () => {
  it("shows On or Off and posts the acknowledgement to the admin route", () => {
    const page = readFileSync(
      join(here, "../components/admin/AdminOverviewPage.tsx"),
      "utf8",
    );
    assert.equal(page.includes('product2_access === "On"'), true);
    assert.equal(page.includes("Grant"), true);
    assert.equal(page.includes("Revoke"), true);
    assert.equal(
      page.includes("/admin/organisations/${orgId}/product2-access"),
      true,
    );
    assert.equal(page.includes("JSON.stringify({ acknowledged })"), true);
    assert.equal(page.includes("product2_acknowledged_by"), true);
    assert.equal(page.includes("product2_acknowledged_at"), true);
  });
});
