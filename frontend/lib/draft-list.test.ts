import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const list = readFileSync(
  new URL("../components/statutory/DraftList.tsx", import.meta.url),
  "utf8",
);
const start = readFileSync(
  new URL("../components/statutory/StartNextYear.tsx", import.meta.url),
  "utf8",
);

test("open stays on a section query and start next year is the only extra action", () => {
  assert.match(list, /\/draft\?section=review/);
  assert.match(list, /StartNextYear/);
  assert.match(start, /Start next year/);
  assert.match(start, /carries_over/);
  assert.match(start, /preparer_must/);
  assert.equal(list.includes("Compare"), false);
  assert.equal(start.includes("Compare"), false);
  assert.equal(start.includes("Roll forward"), false);
});
