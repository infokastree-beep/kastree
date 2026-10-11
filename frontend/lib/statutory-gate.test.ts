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
  ASK_OWNER,
  STATUTORY_SIGNOFF,
  UNREVIEWED_WORDING_BANNER,
  statutoryGateDiagnosis,
  statutoryWorkspaceOpen,
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

describe("statutoryWorkspaceOpen", () => {
  it("follows product2_access and falls back to the platform-admin flag", () => {
    assert.equal(statutoryWorkspaceOpen(undefined), false);
    assert.equal(
      statutoryWorkspaceOpen({
        email: "owner@example.com",
        role: "owner",
        is_platform_admin: false,
        product2_access: {
          enabled: false,
          acknowledged: false,
          source: null,
          wording_signed_off: false,
        },
      }),
      false,
    );
    assert.equal(
      statutoryWorkspaceOpen({
        email: "owner@example.com",
        role: "owner",
        is_platform_admin: false,
        product2_access: {
          enabled: true,
          acknowledged: true,
          source: "practice",
          wording_signed_off: false,
        },
      }),
      true,
    );
    assert.equal(
      statutoryWorkspaceOpen({
        email: "founder@example.com",
        role: "owner",
        is_platform_admin: true,
      }),
      true,
    );
  });
});

describe("Statutory opt-in", () => {
  const optIn = readFileSync(
    join(root, "../components/statutory/StatutoryOptIn.tsx"),
    "utf8",
  );
  const nav = readFileSync(
    join(root, "../components/layout/AdminNavLink.tsx"),
    "utf8",
  );
  const banner = readFileSync(
    join(root, "../components/statutory/UnreviewedWordingBanner.tsx"),
    "utf8",
  );
  const layout = readFileSync(
    join(root, "../app/(dashboard)/layout.tsx"),
    "utf8",
  );
  const continuation = readFileSync(
    join(root, "../components/statements/StatutoryContinuation.tsx"),
    "utf8",
  );

  it("keeps one acknowledgement post and an unticked checkbox", () => {
    assert.equal(
      STATUTORY_SIGNOFF,
      "Draft statutory packs stay limited to platform administrators until a qualified reviewer signs off the wording.",
    );
    assert.equal(
      ASK_OWNER,
      "Ask an owner or admin of this practice to turn on statutory drafts.",
    );
    assert.equal(optIn.includes("iXBRL"), false);
    assert.equal(optIn.includes("localStorage"), false);
    assert.equal(optIn.includes("defaultChecked"), false);
    assert.match(optIn, /useState\(false\)/);
    assert.match(optIn, /JSON\.stringify\(\{ accepted: true \}\)/);
    assert.match(optIn, /disabled=\{!ticked \|\| pending\}/);
    assert.match(optIn, /statutoryGateDiagnosis\(email\)/);
    const checkbox = optIn.indexOf('data-testid="statutory-opt-in-checkbox"');
    const diagnosis = optIn.indexOf('data-testid="statutory-signoff-diagnosis"');
    assert.ok(checkbox > 0);
    assert.ok(diagnosis > checkbox);
    assert.match(continuation, /StatutoryOptIn/);
    assert.equal(continuation.includes("is_platform_admin === false"), false);
  });

  it("shows Statutory to every signed-in user and Admin only to a platform admin", () => {
    const statutory = nav.indexOf('href="/statutory"');
    const admin = nav.indexOf('href="/admin"');
    assert.ok(statutory > 0);
    assert.ok(admin > statutory);
    assert.match(nav, /isSignedIn \?/);
    assert.match(nav, /show \?/);
    assert.equal(nav.includes("me.is_platform_admin") && nav.includes("Statutory"), true);
    const statutoryBlock = nav.slice(statutory - 80, statutory);
    assert.equal(statutoryBlock.includes("is_platform_admin"), false);
  });

  it("keeps the unreviewed-wording banner as one sentence for an admin grant", () => {
    assert.equal(
      UNREVIEWED_WORDING_BANNER,
      "The statutory wording is unreviewed and this practice reviews every output itself.",
    );
    assert.match(banner, /UNREVIEWED_WORDING_BANNER/);
    assert.match(banner, /access\.source !== "admin"/);
    assert.match(layout, /UnreviewedWordingBanner/);
  });
});
