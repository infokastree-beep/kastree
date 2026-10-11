/**
 * Disclosure groups use pack questions, and unanswered stays unanswered
 * until mark-remaining-no succeeds.
 * Run: node --experimental-strip-types --test lib/disclosure-groups.test.ts
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";

import {
  answerAfterMark,
  groupDisclosureQuestions,
  noteHref,
  remainingNoSummary,
  type DisclosureQuestion,
} from "./disclosure-groups.ts";

const here = dirname(fileURLToPath(import.meta.url));

function question(
  flag_name: string,
  group: string,
  answer: DisclosureQuestion["answer"],
  note: string | null = null,
): DisclosureQuestion {
  return {
    flag_name,
    question: `Question for ${flag_name}`,
    group,
    note,
    answer,
  };
}

describe("disclosure groups", () => {
  it("counts answered and unanswered and links one shared note", () => {
    const groups = groupDisclosureQuestions([
      question("PENSION_COMMITMENT", "Commitments", "unanswered", "N9_COMMITMENTS"),
      question("CHARGES_EXIST", "Commitments", "yes", "N9_COMMITMENTS"),
      question("HAS_EMPLOYEES", "Employees", "no", "N8_EMPLOYEES"),
    ]);
    assert.equal(groups.length, 2);
    assert.equal(groups[0]?.group, "Commitments");
    assert.equal(groups[0]?.note, "N9_COMMITMENTS");
    assert.equal(groups[0]?.answered, 1);
    assert.equal(groups[0]?.unanswered, 1);
    assert.equal(
      noteHref("year-1", "N9_COMMITMENTS"),
      "/year-ends/year-1/draft?section=notes&note=N9_COMMITMENTS",
    );
  });

  it("lists the groups and the count mark-remaining-no will set", () => {
    const summary = remainingNoSummary([
      question("PENSION_COMMITMENT", "Commitments", "unanswered", "N9_COMMITMENTS"),
      question("SUBSEQUENT_EVENTS", "Commitments", "unanswered", "N9_COMMITMENTS"),
      question("CHARGES_EXIST", "Commitments", "yes", "N9_COMMITMENTS"),
      question("HAS_FOREIGN", "Other", "unanswered"),
      question("HAS_EMPLOYEES", "Employees", "no", "N8_EMPLOYEES"),
    ]);
    assert.deepEqual(summary.groups, [
      { group: "Commitments", count: 2 },
      { group: "Other", count: 1 },
    ]);
    assert.equal(summary.total, 3);
  });

  it("keeps unanswered until the write succeeds", () => {
    const pending = question("PENSION_COMMITMENT", "Commitments", "unanswered");
    assert.equal(answerAfterMark(pending, null), "unanswered");
    assert.equal(
      answerAfterMark(pending, ["PENSION_COMMITMENT"]),
      "no",
    );
  });

  it("does not title-case a flag before the server responds", () => {
    const source = readFileSync(
      join(here, "../components/statutory/DisclosureGroups.tsx"),
      "utf8",
    );
    assert.match(source, /answerAfterMark\(question, null\)/);
    assert.equal(source.includes('answer: "no"'), false);
  });
});
