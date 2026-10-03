/**
 * Display rounding leaves the stored amount string alone.
 * Run: node --experimental-strip-types --test lib/report-display.test.ts
 */
import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { displayAmount } from "./report-display.ts";

describe("displayAmount", () => {
  it("rounds for display and does not rewrite the stored string", () => {
    const stored = "18400.40";
    assert.equal(displayAmount(stored, "unit"), "18400");
    assert.equal(displayAmount(stored, "thousands"), "18");
    assert.equal(stored, "18400.40");
    assert.equal(displayAmount("10.50", "unit"), "11");
    assert.equal(displayAmount("-10.50", "unit"), "-11");
    assert.equal(displayAmount("18500", "thousands"), "19");
    assert.equal(displayAmount("-18500", "thousands"), "-19");
  });
});
