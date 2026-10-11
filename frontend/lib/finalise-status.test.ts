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
  WORDING_BANNER,
  canOfferFinalise,
  carriedAcknowledgementRequired,
  currencyCodeFromNotice,
  finalStateLabel,
  finaliseFailureMessage,
  finaliseFailureParts,
  requestIdFromBody,
  finaliseStatusLine,
  pdfDownloadLabel,
  shownStatus,
  wordDownloadLabel,
  wordingSignedOffFromServer,
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
    assert.equal(WORDING_BANNER, "Statutory wording not yet reviewed by a qualified reviewer");
    assert.equal(wordingSignedOffFromServer(undefined), false);
    assert.equal(wordingSignedOffFromServer({}), false);
    assert.equal(wordingSignedOffFromServer({ wording_signed_off: false }), false);
    assert.equal(wordingSignedOffFromServer({ wording_signed_off: true }), true);
    assert.equal(finalStateLabel(false), `FINAL — ${WORDING_BANNER}`);
    assert.equal(finalStateLabel(true), "FINAL");
    assert.equal(shownStatus("final", false), `final — ${WORDING_BANNER}`);
    assert.equal(shownStatus("final", true), "final");
    assert.equal(shownStatus("draft", false), "draft");
    assert.equal(pdfDownloadLabel("final"), `Download final PDF — ${WORDING_BANNER}`);
    assert.equal(pdfDownloadLabel("final", false), `Download final PDF — ${WORDING_BANNER}`);
    assert.equal(pdfDownloadLabel("final", true), "Download final PDF");
    assert.equal(pdfDownloadLabel("draft"), "Download draft PDF");
    assert.equal(pdfDownloadLabel(undefined), "Download draft PDF");
    assert.equal(
      wordDownloadLabel("final", false),
      `Download Word (.docx) — ${WORDING_BANNER}`,
    );
    assert.equal(wordDownloadLabel("final", true), "Download Word (.docx)");
    assert.equal(wordDownloadLabel("draft", false), "Download Word (.docx)");
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
      finaliseFailureMessage(400, "report setup is malformed"),
      "report setup is malformed",
    );
    assert.equal(
      finaliseFailureMessage(422, "Idempotency-Key is required"),
      "Idempotency-Key is required",
    );
    assert.equal(
      finaliseFailureMessage(500, "permission denied for table audit_logs"),
      "permission denied for table audit_logs",
    );
    assert.equal(
      finaliseFailureMessage(
        500,
        "permission denied for table audit_logs",
        "4f2a9c10-1111-4222-8333-abcdef012345",
      ),
      "permission denied for table audit_logs Quote reference 4f2a9c10-1111-4222-8333-abcdef012345.",
    );
    assert.equal(
      finaliseFailureMessage(500, "Something went wrong.", "ref-1"),
      "Something went wrong while finalising this draft. Quote reference ref-1.",
    );
    assert.equal(
      finaliseFailureMessage(500, "Internal Server Error", null),
      "Something went wrong while finalising this draft.",
    );
    assert.equal(
      finaliseFailureMessage(500, "FINAL output is never recomputed"),
      "FINAL output is never recomputed",
    );
    assert.equal(
      requestIdFromBody({
        detail: { message: "Something went wrong.", request_id: "ref-9" },
      }),
      "ref-9",
    );
    assert.equal(requestIdFromBody({ detail: "Directors have not been recorded." }), null);
    const missing =
      "The accounts calculation files are missing from the server. " +
      "Finalise cannot run until the application is updated. " +
      "Check the [Trial balance page](/year-ends/11111111-1111-4111-8111-111111111111/draft?section=trial-balance) " +
      "and [Company details](/year-ends/11111111-1111-4111-8111-111111111111/draft?section=company-details); " +
      "they do not hold these files.";
    assert.equal(finaliseFailureMessage(400, missing), missing);
    assert.notEqual(finaliseFailureMessage(400, missing), "This draft could not be finalised.");
    assert.deepEqual(finaliseFailureParts(missing), [
      {
        kind: "text",
        text:
          "The accounts calculation files are missing from the server. " +
          "Finalise cannot run until the application is updated. Check the ",
      },
      {
        kind: "link",
        text: "Trial balance page",
        href: "/year-ends/11111111-1111-4111-8111-111111111111/draft?section=trial-balance",
      },
      { kind: "text", text: " and " },
      {
        kind: "link",
        text: "Company details",
        href: "/year-ends/11111111-1111-4111-8111-111111111111/draft?section=company-details",
      },
      { kind: "text", text: "; they do not hold these files." },
    ]);
  });
});
