/**
 * Note links scroll to the anchor the preview payload names.
 * Run: node --experimental-strip-types --test lib/section-preview.test.ts
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";
import {
  scrollAnchorFor,
  showsPageNumberNote,
  type PreviewChild,
} from "./section-preview.ts";

const children: PreviewChild[] = [
  { id: "N3_DEBTORS", number: 3, label: "Debtors", anchor: "note-N3_DEBTORS" },
  { id: "approval", number: null, label: "Approval", anchor: "approval" },
  { id: "bad", number: null, label: "Bad", anchor: "note bad" },
];

describe("scrollAnchorFor", () => {
  it("uses the printed anchor for a note code or a compilation page", () => {
    assert.equal(scrollAnchorFor("N3_DEBTORS", children), "note-N3_DEBTORS");
    assert.equal(scrollAnchorFor("note-N3_DEBTORS", children), "note-N3_DEBTORS");
    assert.equal(scrollAnchorFor("approval", children), "approval");
    assert.equal(scrollAnchorFor(null, children), null);
    assert.equal(scrollAnchorFor("missing", children), null);
    assert.equal(scrollAnchorFor("bad", children), null);
  });
});

describe("showsPageNumberNote", () => {
  it("is only the contents page", () => {
    assert.equal(showsPageNumberNote("contents"), true);
    assert.equal(showsPageNumberNote("income"), false);
    assert.equal(showsPageNumberNote("notes"), false);
  });

  it("the preview frame is sandboxed and the face table is gone", () => {
    const here = dirname(fileURLToPath(import.meta.url));
    const frame = readFileSync(
      join(here, "../components/statutory/SectionPreview.tsx"),
      "utf8",
    );
    const workspace = readFileSync(
      join(here, "../components/statutory/StatutoryDraftWorkspace.tsx"),
      "utf8",
    );
    const sidebar = readFileSync(
      join(here, "../components/statutory/WorkspaceSidebar.tsx"),
      "utf8",
    );
    assert.equal(frame.includes('sandbox=""'), true);
    assert.equal(frame.includes("allow-scripts"), false);
    assert.equal(frame.includes("allow-same-origin"), false);
    assert.equal(frame.includes("srcDoc"), false);
    assert.equal(frame.includes("srcdoc"), false);
    assert.equal(workspace.includes("function FaceTable"), false);
    assert.equal(workspace.includes("Page numbers appear in the PDF."), true);
    assert.equal(workspace.includes("<SectionPreview"), true);
    assert.equal(sidebar.includes("child.label"), true);
    assert.equal(sidebar.includes("Debtors"), false);
    assert.equal(sidebar.includes("audit-exemption"), false);
  });
});
