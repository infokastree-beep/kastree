/**
 * A draft that passed its checks is ready, including a Product 1 draft.
 * Run: node --experimental-strip-types --test lib/finalise-status.test.ts
 */
import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  CARRIED_ACK_LABEL,
  FINALISED_409,
  FINALISE_LOCK_NOTE,
  FINALISED_STATE,
  canOfferFinalise,
  carriedAcknowledgementRequired,
  currencyCodeFromNotice,
  finaliseFailureMessage,
  finaliseStatusLine,
  pdfDownloadLabel,
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

describe("finalise offer", () => {
  it("offers Finalise to an owner or admin while the draft is still open", () => {
    assert.equal(canOfferFinalise("owner", "draft"), true);
    assert.equal(canOfferFinalise("admin", "locked"), true);
    assert.equal(canOfferFinalise("member", "draft"), false);
    assert.equal(canOfferFinalise("viewer", "draft"), false);
    assert.equal(canOfferFinalise("owner", "final"), false);
    assert.equal(canOfferFinalise(undefined, "draft"), false);
    assert.equal(canOfferFinalise("owner", undefined), false);
  });

  it("asks for the carried-disclosure acknowledgement only when names were copied", () => {
    assert.equal(carriedAcknowledgementRequired(["HAS_EMPLOYEES"]), true);
    assert.equal(carriedAcknowledgementRequired([]), false);
    assert.equal(
      CARRIED_ACK_LABEL,
      "I have reviewed the carried-over disclosure answers.",
    );
    assert.equal(
      FINALISE_LOCK_NOTE,
      "Finalising locks this draft. Corrections require a new version.",
    );
  });

  it("names the FINAL state and the PDF that belongs to it", () => {
    assert.equal(FINALISED_STATE, "FINAL");
    assert.equal(pdfDownloadLabel("final"), "Download final PDF");
    assert.equal(pdfDownloadLabel("draft"), "Download draft PDF");
    assert.equal(pdfDownloadLabel(undefined), "Download draft PDF");
  });

  it("shows each finalise refusal in the server's own words", () => {
    for (const sentence of FINALISED_409) {
      assert.equal(finaliseFailureMessage(409, sentence), sentence);
    }
    assert.equal(
      finaliseFailureMessage(403, "Directors have not been recorded."),
      "You don't have permission to access this resource.",
    );
    assert.equal(
      finaliseFailureMessage(409, "   "),
      "This draft could not be finalised.",
    );
    assert.equal(
      finaliseFailureMessage(500, "FINAL output is never recomputed"),
      "This draft could not be finalised.",
    );
  });
});
