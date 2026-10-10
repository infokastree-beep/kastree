/**
 * Diagnostic line under the statutory sign-off sentence.
 * Run: node --experimental-strip-types --test lib/statutory-gate.test.ts
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";
import {
  STATUTORY_SIGNOFF,
  statutoryGateDiagnosis,
} from "./statutory-gate.ts";

const root = dirname(fileURLToPath(import.meta.url));

describe("statutoryGateDiagnosis", () => {
  it("names only the signed-in email", () => {
    assert.equal(
      statutoryGateDiagnosis("Founder@Example.com"),
      "Signed in as Founder@Example.com. This account is not on the platform administrator list.",
    );
    assert.equal(
      statutoryGateDiagnosis("  owner@kastree.ie  "),
      "Signed in as owner@kastree.ie. This account is not on the platform administrator list.",
    );
  });

  it("asks for a fresh sign-in when the profile has no email", () => {
    const expected = "We could not read your account email. Sign out and back in.";
    assert.equal(statutoryGateDiagnosis(null), expected);
    assert.equal(statutoryGateDiagnosis(undefined), expected);
    assert.equal(statutoryGateDiagnosis(""), expected);
    assert.equal(statutoryGateDiagnosis("   "), expected);
  });
});

describe("Statements page gate", () => {
  const source = readFileSync(
    join(root, "../components/statements/StatutoryContinuation.tsx"),
    "utf8",
  );

  it("keeps the existing sentence and adds the diagnosis under it", () => {
    assert.equal(
      STATUTORY_SIGNOFF,
      "Draft statutory packs stay limited to platform administrators until a qualified reviewer signs off the wording.",
    );
    assert.match(source, /STATUTORY_SIGNOFF/);
    const signoff = source.indexOf('data-testid="statutory-signoff"');
    const diagnosis = source.indexOf('data-testid="statutory-signoff-diagnosis"');
    assert.ok(signoff > 0);
    assert.ok(diagnosis > signoff);
    assert.match(
      source,
      /statutoryGateDiagnosis\(meQuery\.data\?\.email\)/,
    );
    assert.equal(source.includes("is_platform_admin === false"), true);
    assert.equal(
      source.includes(
        "enabled: isSignedIn && meQuery.data?.is_platform_admin === true",
      ),
      true,
    );
  });
});
