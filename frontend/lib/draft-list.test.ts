import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const source = readFileSync(
  new URL("../components/statutory/DraftList.tsx", import.meta.url),
  "utf8",
);

test("open stays on a section query and the list has no roll-forward button", () => {
  assert.match(source, /\/draft\?section=review/);
  assert.equal(source.includes("Roll forward"), false);
  assert.equal(source.includes("Compare"), false);
});
