/**
 * The admin banner names a revision mismatch. A match stays quiet and specific.
 * Run: node --experimental-strip-types --test lib/schema-revision.test.ts
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";

import { revisionBanner } from "./schema-revision.ts";

const here = dirname(fileURLToPath(import.meta.url));

describe("revision banner", () => {
  it("names both revisions when they differ", () => {
    const banner = revisionBanner({
      database_revision: "k7l8m9n0o1",
      code_revision: "l8m9n0o1p2",
      revision_matches: false,
    });
    assert.equal(banner.tone, "mismatch");
    assert.match(banner.text, /k7l8m9n0o1/);
    assert.match(banner.text, /l8m9n0o1p2/);
  });

  it("confirms a match", () => {
    const banner = revisionBanner({
      database_revision: "l8m9n0o1p2",
      code_revision: "l8m9n0o1p2",
      revision_matches: true,
    });
    assert.equal(banner.tone, "ok");
    assert.match(banner.text, /l8m9n0o1p2/);
  });

  it("says the comparison could not be made when a revision is missing", () => {
    const banner = revisionBanner({
      database_revision: null,
      code_revision: "l8m9n0o1p2",
      revision_matches: false,
    });
    assert.equal(banner.tone, "unknown");
  });
});

describe("admin page", () => {
  it("shows the banner from GET /health", () => {
    const page = readFileSync(
      join(here, "../components/admin/AdminOverviewPage.tsx"),
      "utf8",
    );
    assert.match(page, /apiFetch<SchemaRevisionStatus>\("\/health"/);
    assert.match(page, /data-testid="admin-revision-status"/);
    assert.match(page, /revisionBanner/);
  });
});
