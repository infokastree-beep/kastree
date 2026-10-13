/**
 * Section inputs open beside the document they belong to.
 * Run: node --experimental-strip-types --test lib/section-inputs.test.ts
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";
import { fixHref, presentCheck, type ReviewCheck } from "./dashboard-groups.ts";
import {
  directorsReportChildren,
  directorsReportWrite,
  interestsComplete,
  otherMattersComplete,
  recordsComplete,
  sidebarInputChildren,
  withSignatories,
  type DirectorsReportStored,
  type SectionFacts,
} from "./section-inputs.ts";
import type { WorkspaceSection } from "./workspace-sections.ts";

const here = dirname(fileURLToPath(import.meta.url));

function failed(code: string): ReviewCheck {
  return { code, severity: "WARNING", passed: false, message: "missing" };
}

function stored(
  patch: Partial<DirectorsReportStored> = {},
): DirectorsReportStored {
  return {
    accounting_records_location: "1 Harbour Street",
    interim_dividend: "0.00",
    recommended_dividend: "10.00",
    share_interests: [
      {
        name: "Ada Lovelace",
        role: "director",
        at_start: { interested: false, holdings: [] },
        at_end: { interested: false, holdings: [] },
      },
    ],
    own_shares_particulars: "Kept",
    subsequent_events_particulars: "Kept events",
    research_development_relevant: false,
    research_development_detail: null,
    political_donations_relevant: false,
    political_donations_detail: null,
    accounting_period_change_filed: false,
    ...patch,
  };
}

function facts(patch: Partial<SectionFacts> = {}): SectionFacts {
  return {
    ...stored(),
    principal_activity: "Software",
    secretary: "Grace Hopper",
    directors: [{ name: "Ada Lovelace" }],
    compilation_date: "2026-03-31",
    compilation_signatory: "Pat Lee",
    ...patch,
  };
}

describe("section input Fix links", () => {
  it("opens each directors' report check on its row", () => {
    const yearEndId = "year-1";
    const expected: Record<string, string> = {
      "V-CO-004":
        "/year-ends/year-1/draft?section=directors-report&note=principal-activity",
      "V-CO-005": "/year-ends/year-1/draft?section=signatories",
      "V-CO-006": "/year-ends/year-1/draft?section=signatories",
      "V-CO-029":
        "/year-ends/year-1/draft?section=directors-report&note=accounting-records",
      "V-CO-030":
        "/year-ends/year-1/draft?section=directors-report&note=accounting-records",
      "V-CO-031":
        "/year-ends/year-1/draft?section=directors-report&note=accounting-records",
      "V-CO-032":
        "/year-ends/year-1/draft?section=directors-report&note=share-interests",
      "V-CO-033":
        "/year-ends/year-1/draft?section=directors-report&note=other-matters",
      "V-CO-034":
        "/year-ends/year-1/draft?section=directors-report&note=other-matters",
      "V-CO-035":
        "/year-ends/year-1/draft?section=directors-report&note=other-matters",
      "V-CO-036":
        "/year-ends/year-1/draft?section=directors-report&note=other-matters",
    };
    for (const [code, href] of Object.entries(expected)) {
      const shown = presentCheck(failed(code));
      assert.equal(shown.area, "Company details");
      assert.equal(fixHref(yearEndId, shown.fix), href);
    }
  });
});

describe("section input saves", () => {
  it("keeps the facts that this row does not edit", () => {
    const current = stored();
    const saved = directorsReportWrite(current, {
      accounting_records_location: "2 Quay",
    });
    assert.equal(saved.accounting_records_location, "2 Quay");
    assert.equal(saved.interim_dividend, "0.00");
    assert.equal(saved.recommended_dividend, "10.00");
    assert.equal(saved.share_interests[0]?.name, "Ada Lovelace");
    assert.equal(saved.own_shares_particulars, "Kept");
    assert.equal(saved.subsequent_events_particulars, "Kept events");
    assert.equal(saved.research_development_relevant, false);
    assert.equal(saved.political_donations_relevant, false);
    assert.equal(saved.accounting_period_change_filed, false);
    assert.equal("country_of_incorporation" in saved, false);
    assert.equal("compilation_date" in saved, false);
  });
});

describe("section input completeness", () => {
  it("marks a blank required fact missing and a recorded nil dividend complete", () => {
    assert.equal(recordsComplete(stored()), true);
    assert.equal(
      recordsComplete(stored({ interim_dividend: null })),
      false,
    );
    assert.equal(interestsComplete(facts()), false);
    assert.equal(
      interestsComplete(
        facts({
          share_interests: [
            ...stored().share_interests,
            {
              name: "Grace Hopper",
              role: "secretary",
              at_start: { interested: false, holdings: [] },
              at_end: { interested: false, holdings: [] },
            },
          ],
        }),
      ),
      true,
    );
    assert.equal(otherMattersComplete(stored(), []), true);
    assert.equal(otherMattersComplete(stored(), ["V-CO-033"]), false);
    assert.equal(
      otherMattersComplete(stored({ accounting_period_change_filed: null }), []),
      false,
    );
    const rows = directorsReportChildren(facts(), []);
    assert.deepEqual(
      rows.map((row) => row.label),
      [
        "Accounting records and dividends",
        "Interests in shares",
        "Other matters",
        "Principal activities",
      ],
    );
    assert.equal(rows[0]?.status, "complete");
    assert.equal(rows[1]?.status, "missing");
    assert.equal(rows[3]?.status, "complete");
    const children = sidebarInputChildren(
      {
        compilation: [
          { id: "approval", number: null, label: "Approval", anchor: "approval" },
        ],
      },
      facts(),
      [],
    );
    assert.equal(children.compilation?.at(-1)?.id, "compilation-date");
    assert.equal(children.compilation?.[0]?.id, "approval");
    assert.equal(children["directors-report"]?.[0]?.anchor, "accounting-records");
  });
});

describe("signatories navigation", () => {
  it("places Signatories under report options after sections setup", () => {
    const sections: WorkspaceSection[] = [
      {
        id: "sections-setup",
        label: "Sections setup",
        group: "report-options",
        group_label: "Report options",
        order: 3,
      },
      {
        id: "trial-balance",
        label: "Trial balance",
        group: "inputs",
        group_label: "Inputs",
        order: 4,
      },
    ];
    const withRow = withSignatories(sections);
    const signatories = withRow.find((section) => section.id === "signatories");
    assert.equal(signatories?.group, "report-options");
    assert.equal(signatories?.label, "Signatories");
    assert.equal(signatories?.order, 3.5);
    assert.equal(withSignatories(withRow).length, withRow.length);
    assert.equal(
      withSignatories([
        {
          id: "review",
          label: "Review dashboard",
          group: "overview",
          group_label: "Overview",
          order: 1,
        },
      ]).some((section) => section.id === "signatories"),
      false,
    );
  });
});

describe("section input placement", () => {
  it("keeps company facts on company details and the responsibilities panel on its section", () => {
    const company = readFileSync(
      join(here, "../components/statutory/CompanyDetailsForm.tsx"),
      "utf8",
    );
    const workspace = readFileSync(
      join(here, "../components/statutory/StatutoryDraftWorkspace.tsx"),
      "utf8",
    );
    const responsibilities = readFileSync(
      join(here, "../components/statutory/DirectorsResponsibilitiesPanel.tsx"),
      "utf8",
    );
    assert.match(
      company,
      /Directors' report inputs are in the Directors' report section/,
    );
    assert.match(company, /data-testid="company-signatories-link"/);
    assert.equal(company.includes("directors-responsibilities-source"), false);
    assert.equal(company.includes("directors-report-inputs"), false);
    assert.match(company, /data-testid="company-signing-rule"/);
    assert.match(responsibilities, /data-testid="directors-responsibilities-source"/);
    assert.match(workspace, /sectionId === "directors-responsibilities"/);
    assert.match(workspace, /<DirectorsResponsibilitiesPanel \/>/);
    assert.match(workspace, /sectionId === "signatories"/);
    assert.match(workspace, /canEdit=\{canEditDetails\}/);
    assert.match(workspace, /details=\{detailsQuery\.data\}/);
    assert.match(workspace, /compilationDate=\{detailsQuery\.data\.compilation_date\}/);
    assert.match(workspace, /\/compilation-report/);
    const viewer = workspace.slice(
      workspace.indexOf("const canEditDetails"),
      workspace.indexOf("const canRecordClaim"),
    );
    assert.match(viewer, /"member"/);
    assert.equal(viewer.includes('"viewer"'), false);
  });
});
