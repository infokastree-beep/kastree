/**
 * Word export is a row under Outputs, with a progress label while the job runs.
 * Run: node --experimental-strip-types --test lib/draft-word.test.ts
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";
import {
  WORD_DOWNLOAD_LABEL,
  WORD_PROGRESS_LABEL,
  wordProgressLabel,
} from "./draft-word-status.ts";

const here = dirname(fileURLToPath(import.meta.url));

describe("wordProgressLabel", () => {
  it("shows progress only while the job is unfinished", () => {
    assert.equal(wordProgressLabel("pending"), WORD_PROGRESS_LABEL);
    assert.equal(wordProgressLabel("running"), WORD_PROGRESS_LABEL);
    assert.equal(wordProgressLabel("ready"), null);
    assert.equal(wordProgressLabel("failed"), null);
    assert.equal(wordProgressLabel("idle"), null);
    assert.equal(WORD_DOWNLOAD_LABEL, "Download Word (.docx)");
    assert.equal(WORD_PROGRESS_LABEL, "Preparing Word…");
  });
});

describe("outputs row", () => {
  it("places the Word download under Outputs with a progress state", () => {
    const workspace = readFileSync(
      join(here, "../components/statutory/StatutoryDraftWorkspace.tsx"),
      "utf8",
    );
    assert.equal(workspace.includes('sectionId === "draft-pdf"'), true);
    assert.equal(workspace.includes("statutory-outputs"), true);
    assert.equal(workspace.includes("statutory-word-row"), true);
    assert.equal(workspace.includes("statutory-download-word"), true);
    assert.equal(workspace.includes("statutory-word-progress"), true);
    assert.equal(workspace.includes("WORD_DOWNLOAD_LABEL"), true);
    assert.equal(workspace.includes("WORD_PROGRESS_LABEL"), true);
    assert.equal(workspace.includes("downloadDraftWord"), true);
    assert.equal(workspace.includes("/document.docx"), false);
  });
});
