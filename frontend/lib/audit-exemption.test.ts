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
  AUDIT_EXEMPTION_ABRIDGEMENT_NOTE,
  AUDIT_EXEMPTION_NOTE,
  AUDIT_EXEMPTION_PARAGRAPHS,
  AUDIT_EXEMPTION_PROVISION,
  AUDIT_EXEMPTION_SOURCE,
  AUDIT_EXEMPTION_SOURCE_LABEL,
  AUDIT_EXEMPTION_SOURCE_STATUS,
  AUDIT_POSITION_FINAL_LOCK,
  approvalDateLine,
  printedAuditExemption,
  unprintedAuditExemptionSource,
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
        abridgement_note: string;
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
    assert.equal(block.abridgement_note, AUDIT_EXEMPTION_ABRIDGEMENT_NOTE);
    assert.equal(block.abridgement_note.includes("separate recorded claim"), true);
    assert.equal(block.abridgement_note.toLowerCase().includes("confirmed"), false);
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
    assert.match(component, /What prints if the exemption is claimed/);
    assert.match(component, /data-testid="audit-exemption-printed"/);
    const positionAt = component.indexOf('data-testid="audit-exemption-position"');
    const headingAt = component.indexOf("What prints if the exemption is claimed");
    const signaturesAt = component.indexOf('data-testid="audit-exemption-signatures"');
    assert.equal(positionAt >= 0 && headingAt > positionAt && signaturesAt > headingAt, true);
    assert.match(component, /claimed === true \?/);
    assert.match(component, /data-testid="audit-exemption-signatures"/);
    assert.match(component, /Source text \(CRO\), not printed/);
    assert.match(component, /data-testid="audit-exemption-locked"/);
    const printed = printedAuditExemption("charlie mungar buffett");
    assert.equal(printed[0], "I/We, as director(s) of charlie mungar buffett, state that:");
    assert.deepEqual(
      printed.slice(1).map((line) => line.slice(0, 3)),
      ["(a)", "(b)", "(c)", "(d)"],
    );
    assert.equal(printed.join(" ").includes("(company name)"), false);
    assert.equal(printed.join(" ").includes("(e)"), false);
    const source = unprintedAuditExemptionSource();
    assert.equal(source.some((line) => line.includes("(company name)")), true);
    assert.equal(source.some((line) => line.startsWith("*(e)")), true);
    assert.equal(source.some((line) => line.includes("use sections (a)")), true);
    assert.equal(approvalDateLine(null), "Approval date has not been recorded.");
    assert.equal(approvalDateLine("2027-03-17"), "Approved on 17 March 2027.");
    assert.equal(AUDIT_POSITION_FINAL_LOCK, "Locked: this draft is final");
    assert.match(component, /data-testid="audit-exemption-claimed"/);
    assert.match(component, /data-testid="audit-exemption-not-claimed"/);
    assert.match(component, /data-testid="audit-exemption-clear"/);
    assert.match(component, /const editable = canRecord && lockLabel == null/);
    assert.equal(component.includes("{canRecord ?"), false);
    assert.match(component, /data-testid="audit-exemption-conditions"/);
    assert.match(component, /testId: "audit-exemption-not-excluded"/);
    assert.match(component, /testId: "audit-exemption-no-member-notice"/);
    assert.match(component, /testId: "audit-exemption-returns-not-late"/);
    assert.match(component, /data-testid=\{`\$\{field\.testId\}-yes`\}/);
    assert.match(component, /data-testid="audit-exemption-conditions-record"/);
    assert.match(workspace, /canRecord=\{canRecordClaim\}/);
    assert.match(workspace, /role === "owner" \|\| meQuery\.data\?\.role === "admin"/);
    assert.match(workspace, /\/audit-exemption`,/);
    assert.match(workspace, /\/audit-exemption-conditions/);
    assert.match(
      banner,
      /Statutory wording not yet reviewed by a qualified reviewer/,
    );
  });
});
