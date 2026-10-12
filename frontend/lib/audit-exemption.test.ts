/**
 * The workspace shows the pack sentences and labels them source not confirmed.
 * Run: node --experimental-strip-types --test lib/audit-exemption.test.ts
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";

import {
  AUDIT_EXEMPTION_SOURCE_LABEL,
  AUDIT_EXEMPTION_STATEMENT,
  MEMBERS_AUDIT_STATEMENT,
} from "./audit-exemption.ts";

const here = dirname(fileURLToPath(import.meta.url));

describe("audit exemption claim", () => {
  it("uses the pending-sign-off pack sentences", () => {
    const pack = JSON.parse(
      readFileSync(
        join(here, "../../findraft/content/frs102-1a-ie/2024.09/pack.json"),
        "utf8",
      ),
    ) as {
      audit_exemption_statements: {
        source_status: string;
        exemption: string;
        members: string;
      };
      thresholds: Record<string, unknown>;
    };
    assert.deepEqual(Object.keys(pack.thresholds).sort(), [
      "balance_sheet",
      "currency",
      "employees",
      "regime",
      "rule",
      "turnover",
      "years",
    ]);
    assert.equal(pack.audit_exemption_statements.source_status, "pending-reviewer-signoff");
    assert.equal(pack.audit_exemption_statements.exemption, AUDIT_EXEMPTION_STATEMENT);
    assert.equal(pack.audit_exemption_statements.members, MEMBERS_AUDIT_STATEMENT);
    assert.equal(AUDIT_EXEMPTION_SOURCE_LABEL, "source not confirmed");
    assert.equal(AUDIT_EXEMPTION_STATEMENT.toLowerCase().includes("eligible"), false);
    assert.equal(MEMBERS_AUDIT_STATEMENT.toLowerCase().includes("eligible"), false);
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
    assert.match(component, /data-testid="audit-exemption-source"/);
    assert.match(component, /AUDIT_EXEMPTION_SOURCE_LABEL/);
    assert.match(component, /data-testid="audit-exemption-claimed"/);
    assert.match(component, /data-testid="audit-exemption-not-claimed"/);
    assert.match(component, /data-testid="audit-exemption-clear"/);
    assert.match(component, /\{canRecord \?/);
    assert.match(workspace, /canRecord=\{canRecordClaim\}/);
    assert.match(workspace, /role === "owner" \|\| meQuery\.data\?\.role === "admin"/);
    assert.match(workspace, /\/audit-exemption/);
  });
});
