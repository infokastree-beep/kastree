/**
 * A draft that passed its checks is ready, including a Product 1 draft.
 * Run: node --experimental-strip-types --test lib/finalise-status.test.ts
 */
import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  currencyCodeFromNotice,
  finaliseStatusLine,
} from "./finalise-status.ts";

describe("finaliseStatusLine", () => {
  it("keeps a versioned draft that passed its checks ready", () => {
    assert.equal(
      finaliseStatusLine({ canFinalise: true, tbVersionId: "version-1" }),
      " Ready to finalise.",
    );
  });

  it("offers finalise for a Product 1 draft once checks have passed", () => {
    assert.equal(
      finaliseStatusLine({ canFinalise: true, tbVersionId: null }),
      " Ready to finalise.",
    );
  });

  it("reads the currency code from the V-CO-007 notice", () => {
    assert.equal(
      currencyCodeFromNotice(
        "Company currency is GBP. Confirm this is intended.",
      ),
      "GBP",
    );
    assert.equal(currencyCodeFromNotice("Directors have not been recorded."), null);
  });

  it("stays not ready when checks have not passed", () => {
    assert.equal(
      finaliseStatusLine({ canFinalise: false, tbVersionId: null }),
      " Not ready to finalise.",
    );
    assert.equal(
      finaliseStatusLine({ canFinalise: false, tbVersionId: "version-1" }),
      " Not ready to finalise.",
    );
  });
});
