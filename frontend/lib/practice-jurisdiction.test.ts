/**
 * The practice country save does not include company fields.
 * Run: node --experimental-strip-types --test lib/practice-jurisdiction.test.ts
 */
import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  JURISDICTION_HINT,
  canEditPracticeJurisdiction,
  jurisdictionUpdateBody,
} from "./practice-jurisdiction.ts";

describe("practice jurisdiction", () => {
  it("lets an owner or admin change the practice country", () => {
    assert.equal(canEditPracticeJurisdiction("owner"), true);
    assert.equal(canEditPracticeJurisdiction("admin"), true);
    assert.equal(canEditPracticeJurisdiction("member"), false);
    assert.equal(canEditPracticeJurisdiction("viewer"), false);
  });

  it("sends only the jurisdiction", () => {
    assert.deepEqual(jurisdictionUpdateBody("IE"), { jurisdiction: "IE" });
    assert.deepEqual(jurisdictionUpdateBody("GB"), { jurisdiction: "GB" });
    assert.deepEqual(jurisdictionUpdateBody(null), { jurisdiction: null });
    assert.equal(
      Object.keys(jurisdictionUpdateBody("IE")).join(","),
      "jurisdiction",
    );
  });

  it("uses the plain-English hint", () => {
    assert.equal(
      JURISDICTION_HINT,
      "New companies default to this country's currency",
    );
  });
});
