/**
 * The reset request is not sent until the dialog is confirmed.
 * Run: node --experimental-strip-types --test lib/reset-confirm.test.ts
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, it } from "node:test";
import {
  RESET_CONFIRM_MESSAGE,
  resetConfirmAfter,
  type ResetConfirmAction,
  type ResetConfirmState,
} from "./reset-confirm.ts";

const here = dirname(fileURLToPath(import.meta.url));

describe("resetConfirmAfter", () => {
  it("does not send until Reset is chosen on an open dialog", () => {
    let state: ResetConfirmState = "closed";
    const sent: ResetConfirmAction[] = [];

    function act(action: ResetConfirmAction): void {
      const next = resetConfirmAfter(state, action);
      state = next.state;
      if (next.send) {
        sent.push(action);
      }
    }

    act("open");
    assert.equal(state, "open");
    assert.deepEqual(sent, []);
    act("cancel");
    assert.equal(state, "closed");
    assert.deepEqual(sent, []);
    act("reset");
    assert.deepEqual(sent, []);
    act("open");
    act("reset");
    assert.equal(state, "closed");
    assert.deepEqual(sent, ["reset"]);
  });
});

describe("reset dialog copy", () => {
  it("both setup screens use the shared dialog and do not post on the first click", () => {
    const dialog = readFileSync(
      join(here, "../components/statutory/ResetDefaultsDialog.tsx"),
      "utf8",
    );
    const sections = readFileSync(
      join(here, "../components/statutory/SectionsSetup.tsx"),
      "utf8",
    );
    const form = readFileSync(
      join(here, "../components/statutory/ReportSetupForm.tsx"),
      "utf8",
    );
    assert.equal(
      RESET_CONFIRM_MESSAGE,
      "Reset to pack defaults? Saved settings on this draft will be cleared.",
    );
    assert.equal(dialog.includes("{RESET_CONFIRM_MESSAGE}"), true);
    assert.match(dialog, />\s*Cancel\s*</);
    assert.match(dialog, />\s*Reset\s*</);
    assert.equal(dialog.includes("Reset to pack defaults"), true);
    assert.equal(dialog.includes("resetConfirmAfter"), true);
    assert.equal(dialog.includes("if (next.send)"), true);
    assert.equal(dialog.includes('act("reset")'), true);
    for (const source of [sections, form]) {
      assert.equal(source.includes("ResetDefaultsDialog"), true);
      assert.equal(source.includes("onReset();"), false);
    }
  });
});
