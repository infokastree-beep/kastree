/**
 * Export link attributes: PDF opens in a new tab; Excel/CSV do not pretend
 * the download attribute works on a cross-origin presigned URL.
 * Run: node --experimental-strip-types --test lib/export-download.test.ts
 */
import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { exportAnchorAttributes } from "./export-download.ts";

const FILE_URL = "https://storage.example/exports/abc.pdf?sig=1";

describe("exportAnchorAttributes", () => {
  it("opens PDF in a new tab and does not force a download", () => {
    const attrs = exportAnchorAttributes(FILE_URL, "pdf");
    assert.equal(attrs.href, FILE_URL);
    assert.equal(attrs.target, "_blank");
    assert.equal(attrs.rel, "noopener noreferrer");
    assert.equal("download" in attrs, false);
  });

  it("does not set target or download for Excel", () => {
    const attrs = exportAnchorAttributes(
      "https://storage.example/exports/abc.xlsx?sig=1",
      "xlsx",
    );
    assert.equal(attrs.target, undefined);
    assert.equal("download" in attrs, false);
    assert.equal(attrs.rel, "noopener noreferrer");
  });

  it("does not set target or download for CSV", () => {
    const attrs = exportAnchorAttributes(
      "https://storage.example/exports/abc.csv?sig=1",
      "csv",
    );
    assert.equal(attrs.target, undefined);
    assert.equal("download" in attrs, false);
  });
});
