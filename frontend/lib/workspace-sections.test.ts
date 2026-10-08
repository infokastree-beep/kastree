/**
 * The sidebar list comes from the selected framework.
 * Run: node --experimental-strip-types --test lib/workspace-sections.test.ts
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";
import {
  activeSection,
  sectionIsOn,
  sectionsForFramework,
  type ReportingFramework,
  type WorkspaceSection,
} from "./workspace-sections.ts";

function section(
  id: string,
  label: string,
  group: string,
  groupLabel: string,
  order: number,
): WorkspaceSection {
  return { id, label, group, group_label: groupLabel, order };
}

const frameworks: ReportingFramework[] = [
  {
    id: "frs102-1a-ie",
    label: "FRS 102 Section 1A (Ireland)",
    available: true,
    sections: [
      section("review", "Review dashboard", "overview", "Overview", 1),
      section("report-setup", "Report setup", "report-options", "Report options", 2),
      section("sub-lines", "Mapping", "inputs", "Inputs", 3),
      section("adjustments", "Adjustments", "inputs", "Inputs", 4),
      section("disclosures", "Disclosures", "inputs", "Inputs", 5),
      section("company-details", "Company details", "inputs", "Inputs", 6),
      section("income", "Income statement", "sections", "Sections", 7),
      section("sofp", "Statement of financial position", "sections", "Sections", 8),
    ],
  },
  {
    id: "form11-summary",
    label: "Sole Trader / Form 11 Summary",
    available: false,
    sections: [
      section("review", "Review dashboard", "overview", "Overview", 1),
      section("report-setup", "Report setup", "report-options", "Report options", 2),
    ],
  },
];

describe("sectionsForFramework", () => {
  it("returns a shorter list for Form 11 than for FRS 102", () => {
    const frs = sectionsForFramework(frameworks, "frs102-1a-ie");
    const form11 = sectionsForFramework(frameworks, "form11-summary");
    assert.deepEqual(
      form11.map((item) => item.label),
      ["Review dashboard", "Report setup"],
    );
    assert.equal(
      frs.map((item) => item.label).includes("Extracts summary"),
      false,
    );
    assert.equal(form11.map((item) => item.label).includes("Mapping"), false);
    assert.equal(form11.some((item) => item.group === "sections"), false);
    assert.equal(
      frs.find((item) => item.id === "company-details")?.group,
      "inputs",
    );
    assert.ok(form11.length < frs.length);
  });

  it("does not fall back to the FRS 102 list for an unknown framework", () => {
    const unknown = sectionsForFramework(frameworks, "uk-frs105").map(
      (item) => item.id,
    );
    assert.deepEqual(unknown, ["review", "report-setup"]);
    assert.equal(
      activeSection(sectionsForFramework(frameworks, "form11-summary"), "sub-lines"),
      "review",
    );
  });

  it("the sidebar component does not name a framework or a group", () => {
    const here = dirname(fileURLToPath(import.meta.url));
    const source = readFileSync(
      join(here, "../components/statutory/WorkspaceSidebar.tsx"),
      "utf8",
    );
    for (const word of [
      "frs102",
      "form11",
      "FRS",
      "Form 11",
      "Sub-line review",
      "Overview",
      "Company details",
      "Mapping",
      "Report options",
      "Inputs",
      "Sections",
      "Outputs",
      "Cover",
      "Draft PDF",
    ]) {
      assert.equal(source.includes(word), false, word);
    }
    assert.equal(source.includes('section.lock === "user"'), true);
    assert.equal(source.includes("statutory-toggle-"), true);
    assert.equal(source.includes("opacity-50"), true);
    const form = readFileSync(
      join(here, "../components/statutory/ReportSetupForm.tsx"),
      "utf8",
    );
    assert.equal(form.includes("sections:"), false);
  });
});

describe("sectionIsOn", () => {
  const cover = section("cover", "Cover", "sections", "Sections", 7);
  cover.lock = "user";
  cover.default = "on";
  const cash = section("cash-flow", "Cash flow statement", "sections", "Sections", 11);
  cash.lock = "user";
  cash.default = "off";
  const income = section("income", "Income statement", "sections", "Sections", 8);
  income.lock = "locked";
  income.default = "on";

  it("uses the pack default until a saved map names the section", () => {
    assert.equal(sectionIsOn(cover, null), true);
    assert.equal(sectionIsOn(cash, null), false);
    assert.equal(sectionIsOn(income, { income: false }), true);
    assert.equal(sectionIsOn(cover, { cover: false, "cash-flow": true }), false);
    assert.equal(sectionIsOn(cash, { cover: false, "cash-flow": true }), true);
  });
});
