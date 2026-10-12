/**
 * The workspace shows the CRO statement and labels it source not confirmed.
 * Run: node --experimental-strip-types --test lib/audit-exemption.test.ts
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";

import {
  AUDIT_EXEMPTION_NOTE,
  AUDIT_EXEMPTION_PARAGRAPHS,
  AUDIT_EXEMPTION_PROVISION,
  AUDIT_EXEMPTION_SOURCE,
  AUDIT_EXEMPTION_SOURCE_LABEL,
  AUDIT_EXEMPTION_SOURCE_STATUS,
} from "./audit-exemption.ts";

const here = dirname(fileURLToPath(import.meta.url));

describe("audit exemption claim", () => {
  it("uses the CRO statement researched from a public source", () => {
    const pack = JSON.parse(
      readFileSync(
        join(here, "../../findraft/content/frs102-1a-ie/2024.09/pack.json"),
        "utf8",
      ),
    ) as {
      audit_exemption_statements: {
        source: string;
        provision: string;
        source_status: string;
        paragraphs: string[];
        explanatory_note: string;
      };
      thresholds: Record<string, unknown>;
    };
    const block = pack.audit_exemption_statements;
    assert.deepEqual(Object.keys(pack.thresholds).sort(), [
      "balance_sheet",
      "currency",
      "employees",
      "regime",
      "rule",
      "turnover",
      "years",
    ]);
    assert.equal(block.source, AUDIT_EXEMPTION_SOURCE);
    assert.equal(block.provision, AUDIT_EXEMPTION_PROVISION);
    assert.equal(block.source_status, AUDIT_EXEMPTION_SOURCE_STATUS);
    assert.equal(block.source_status, "researched (public source)");
    assert.equal(block.source_status.includes("confirmed"), false);
    assert.equal(block.source_status.includes("signed off"), false);
    assert.deepEqual(block.paragraphs, [...AUDIT_EXEMPTION_PARAGRAPHS]);
    assert.equal(block.explanatory_note, AUDIT_EXEMPTION_NOTE);
    assert.equal(AUDIT_EXEMPTION_SOURCE_LABEL, "source not confirmed");
    assert.equal(AUDIT_EXEMPTION_PARAGRAPHS[4].includes("\u2019"), true);
    assert.equal(AUDIT_EXEMPTION_PARAGRAPHS[7].includes("\u2013"), true);
    for (const paragraph of AUDIT_EXEMPTION_PARAGRAPHS) {
      assert.equal(paragraph.toLowerCase().includes("eligible"), false);
    }
  });

  it("shows the label and keeps recording to an owner or admin", () => {
    const component = readFileSync(
      join(here, "../components/statutory/AuditExemptionClaim.tsx"),
      "utf8",
    );
    const workspace = readFileSync(
      join(here, "../components/statutory/StatutoryDraftWorkspace.tsx"),
      "utf8",
    );
    const banner = readFileSync(join(here, "finalise-status.ts"), "utf8");
    assert.match(component, /data-testid="audit-exemption-source"/);
    assert.match(component, /AUDIT_EXEMPTION_SOURCE_LABEL/);
    assert.match(component, /data-testid="audit-exemption-claimed"/);
    assert.match(component, /data-testid="audit-exemption-not-claimed"/);
    assert.match(component, /data-testid="audit-exemption-clear"/);
    assert.match(component, /\{canRecord \?/);
    assert.match(workspace, /canRecord=\{canRecordClaim\}/);
    assert.match(workspace, /role === "owner" \|\| meQuery\.data\?\.role === "admin"/);
    assert.match(workspace, /\/audit-exemption/);
    assert.match(
      banner,
      /Statutory wording not yet reviewed by a qualified reviewer/,
    );
  });
});
