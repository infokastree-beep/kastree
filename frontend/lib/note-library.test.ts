import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { groupByNoteClass, NOTE_CLASS_ORDER } from "./section-preview.ts";
import { reasonSentence, type NoteLibraryRow } from "./note-library.ts";

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
  assert.match(source, /row\.title/);
  assert.match(source, /row\.kind/);
  assert.match(source, /statutory-note-library/);
  assert.match(source, /Omit as immaterial/);
  assert.match(source, /Add this block/);
  assert.equal(source.includes("N0_ENTITY"), false);
  assert.equal(source.includes(">{row.block_id}<"), false);
  const row = (title: string, kind: "Note" | "Policy", noteClass: string): NoteLibraryRow => ({
    block_id: "hidden",
    title,
    reason: "always",
    sentence: "This note is always included.",
    can_omit: false,
    can_restore: false,
    can_add: false,
    can_remove: false,
    kind,
    note_class: noteClass,
    note_class_label: noteClass[0]?.toUpperCase() + noteClass.slice(1),
  });
  const groups = groupByNoteClass(
    [
      row("Company information", "Note", "other"),
      row("Debtors", "Policy", "policies"),
      row("Debtors", "Note", "current assets"),
      row("Creditors", "Policy", "policies"),
      row("Creditors", "Note", "creditors"),
    ],
    NOTE_CLASS_ORDER,
  );
  assert.deepEqual(
    groups.map((group) => [group.label, group.items.map((item) => `${item.kind} ${item.title}`)]),
    [
      ["Policies", ["Policy Debtors", "Policy Creditors"]],
      ["Current assets", ["Note Debtors"]],
      ["Creditors", ["Note Creditors"]],
      ["Other", ["Note Company information"]],
    ],
  );
  for (const group of groups) {
    for (const item of group.items) {
      assert.equal(item.title.includes("N0_"), false);
      assert.notEqual(item.title, item.block_id);
    }
  }
});
