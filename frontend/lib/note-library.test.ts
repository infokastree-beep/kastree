import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { reasonSentence } from "./note-library.ts";

test("reason sentences name the line or the question and no amount", () => {
  const sentences = [
    reasonSentence("always", "Tangible fixed assets", true),
    reasonSentence("trial_balance", "Tangible fixed assets", true),
    reasonSentence("trial_balance", "Tangible fixed assets", false),
    reasonSentence(
      "disclosure_yes",
      "Are there retirement-benefit commitments?",
      true,
    ),
    reasonSentence(
      "unanswered",
      "Are there retirement-benefit commitments?",
      true,
    ),
    reasonSentence(
      "disclosure_no",
      "Are there retirement-benefit commitments?",
      false,
    ),
    reasonSentence(
      "omitted",
      "Are there retirement-benefit commitments?",
      true,
    ),
    reasonSentence("added", "Are there retirement-benefit commitments?", false),
  ];
  assert.equal(sentences[0], "This note is always included.");
  assert.equal(
    sentences[1],
    "Included because Tangible fixed assets has a balance.",
  );
  assert.equal(
    sentences[7],
    "Added by the preparer. The answer to “Are there retirement-benefit commitments?” is No.",
  );
  for (const sentence of sentences) {
    assert.equal(/\d/.test(sentence), false);
    assert.equal(sentence.includes("£"), false);
    assert.equal(sentence.includes("€"), false);
  }
});

test("the notes library shows the server sentence and the four controls", () => {
  const source = readFileSync(
    new URL("../components/statutory/NotesLibrary.tsx", import.meta.url),
    "utf8",
  );
  assert.match(source, /row\.sentence/);
  assert.match(source, /statutory-note-library/);
  assert.match(source, /Omit as immaterial/);
  assert.match(source, /Add this block/);
});
