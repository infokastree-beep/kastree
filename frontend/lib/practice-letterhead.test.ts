/**
 * The practice letterhead save is owner or admin, and sends three fields.
 * Run: node --experimental-strip-types --test lib/practice-letterhead.test.ts
 */
import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  LETTERHEAD_HINT,
  canEditPracticeLetterhead,
  letterheadUpdateBody,
} from "./practice-letterhead.ts";
import { fixHref, presentCheck, stopsFinalise } from "./dashboard-groups.ts";

describe("practice letterhead", () => {
  it("lets an owner or admin change the letterhead", () => {
    assert.equal(canEditPracticeLetterhead("owner"), true);
    assert.equal(canEditPracticeLetterhead("admin"), true);
    assert.equal(canEditPracticeLetterhead("member"), false);
    assert.equal(canEditPracticeLetterhead("viewer"), false);
  });

  it("sends the legal name, address, and contact", () => {
    const body = letterheadUpdateBody({
      name: "Harbour Practice",
      letterhead_address: "1 Practice Quay\nDublin",
      letterhead_contact: "01 555 0100",
    });
    assert.deepEqual(Object.keys(body), [
      "name",
      "letterhead_address",
      "letterhead_contact",
    ]);
    assert.equal(
      LETTERHEAD_HINT,
      "Printed on the compilation report. The report wording is pending the professional body's illustrative text.",
    );
  });

  it("points the incomplete letterhead at settings", () => {
    const fix = presentCheck({
      code: "V-CO-038",
      severity: "WARNING",
      passed: false,
      message: "The practice address has not been recorded.",
    }).fix;
    assert.equal(fix.section, "settings");
    assert.equal(fix.anchor, "practice-letterhead");
    assert.equal(fixHref("year-1", fix), "/settings#practice-letterhead");
    assert.equal(
      stopsFinalise({
        code: "V-CO-038",
        severity: "WARNING",
        passed: false,
        message: "The practice address has not been recorded.",
      }),
      true,
    );
  });
});
