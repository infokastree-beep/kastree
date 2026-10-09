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
  groupIsOpen,
  navigatorSections,
  parseGroupState,
  sectionIsOn,
  sectionsForFramework,
  SIDEBAR_GROUPS_KEY,
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
      "cash-flow",
      "oci",
      "socie",
      "trading",
      "Statement of comprehensive income",
      "Statement of changes in equity",
      "Cash flow statement",
      "Supplementary trading statement",
    ]) {
      assert.equal(source.includes(word), false, word);
    }
    assert.equal(source.includes('section.lock === "user"'), false);
    assert.equal(source.includes("statutory-toggle-"), false);
    assert.equal(source.includes('type="checkbox"'), false);
    assert.equal(source.includes("section.built === false"), true);
    assert.equal(source.includes("section.enabled === false"), true);
    assert.equal(source.includes('section.lock === "locked"'), true);
    assert.equal(source.includes(">off<"), true);
    assert.equal(source.includes(">lock<"), true);
    assert.equal(source.includes("not built"), true);
    for (const word of [
      "Signatories",
      "Events log",
      "Prior-year comparatives",
      "Home",
      "Trial balance",
    ]) {
      assert.equal(source.includes(word), false, word);
    }
    assert.equal(source.includes("aria-expanded"), true);
    assert.equal(source.includes("statutory-group-toggle-"), true);
    assert.equal(SIDEBAR_GROUPS_KEY, "kastree.sidebar.groups.v1");
    const setup = readFileSync(
      join(here, "../components/statutory/SectionsSetup.tsx"),
      "utf8",
    );
    assert.equal(setup.includes("statutory-toggle-"), true);
    assert.equal(setup.includes("not built"), true);
    assert.equal(setup.includes("locked"), true);
    assert.equal(setup.includes("Reset to pack defaults"), true);
    assert.equal(setup.includes("Confirm reset"), true);
    for (const word of ["frs102", "form11", "FRS", "Form 11"]) {
      assert.equal(setup.includes(word), false, word);
    }
    const workspace = readFileSync(
      join(here, "../components/statutory/StatutoryDraftWorkspace.tsx"),
      "utf8",
    );
    assert.equal(workspace.includes("navigatorSections(sections)"), true);
    assert.equal(workspace.includes("section-outline"), true);
    assert.equal(
      workspace.includes(
        "This section is off and will not appear in the PDF. Its data is kept.",
      ),
      true,
    );
    assert.equal(workspace.includes("Turn on"), true);
    assert.equal(workspace.includes("statutory-turn-on"), true);
    assert.equal(workspace.includes("<SectionsSetup"), true);
    assert.equal(workspace.includes("statutory-setup-notices"), true);
    assert.equal(workspace.includes("Ready to finalise."), true);
    const form = readFileSync(
      join(here, "../components/statutory/ReportSetupForm.tsx"),
      "utf8",
    );
    assert.equal(form.includes("sections:"), false);
    assert.equal(form.includes("Reset to pack defaults"), true);
    assert.equal(form.includes("Confirm reset"), true);
  });
});

describe("navigatorSections", () => {
  const rows: WorkspaceSection[] = [
    section("review", "Review dashboard", "overview", "Overview", 1),
    {
      id: "sections-setup",
      label: "Sections setup",
      group: "sections",
      group_label: "Sections",
      order: 2,
    },
    {
      id: "cover",
      label: "Cover",
      group: "sections",
      group_label: "Sections",
      order: 3,
      lock: "user",
      default: "on",
      enabled: false,
    },
    {
      id: "income",
      label: "Income statement",
      group: "sections",
      group_label: "Sections",
      order: 4,
      lock: "locked",
      enabled: true,
      built: true,
    },
    {
      id: "draft-pdf",
      label: "Draft PDF",
      group: "outputs",
      group_label: "Outputs",
      order: 5,
    },
  ];

  it("lists every pack section in order with its on or off state", () => {
    assert.deepEqual(
      navigatorSections(rows).map((item) => [item.id, item.enabled ?? null]),
      [
        ["review", null],
        ["sections-setup", null],
        ["cover", false],
        ["income", true],
        ["draft-pdf", null],
      ],
    );
    const pack = [
      section("cover", "Cover", "sections", "Sections", 1),
      section("contents", "Contents", "sections", "Sections", 2),
      section("income", "Income statement", "sections", "Sections", 3),
      section("cash-flow", "Cash flow statement", "sections", "Sections", 4),
    ];
    pack[0].lock = "user";
    pack[0].default = "on";
    pack[0].enabled = false;
    pack[1].lock = "user";
    pack[1].default = "on";
    pack[1].enabled = true;
    pack[2].lock = "locked";
    pack[2].enabled = true;
    pack[3].lock = "user";
    pack[3].default = "off";
    pack[3].built = false;
    pack[3].enabled = false;
    assert.deepEqual(
      navigatorSections(pack).map((item) => [
        item.id,
        item.enabled,
        item.lock,
        item.built,
      ]),
      [
        ["cover", false, "user", undefined],
        ["contents", true, "user", undefined],
        ["income", true, "locked", undefined],
        ["cash-flow", false, "user", false],
      ],
    );
  });

  it("opens an off section on its own panel", () => {
    assert.equal(activeSection(rows, "cover"), "cover");
    assert.equal(activeSection(rows, "income"), "income");
    assert.equal(activeSection(rows, "review"), "review");
  });
});

describe("group state", () => {
  it("treats a missing key as open and keeps only closed groups", () => {
    assert.equal(groupIsOpen({}, "sections"), true);
    assert.equal(groupIsOpen({ sections: false }, "sections"), false);
    assert.deepEqual(parseGroupState(null), {});
    assert.deepEqual(parseGroupState("not-json"), {});
    assert.deepEqual(
      parseGroupState(JSON.stringify({ inputs: false, overview: true })),
      { inputs: false },
    );
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
    assert.equal(sectionIsOn(cover, {}), true);
    assert.equal(sectionIsOn(cash, null), false);
    assert.equal(sectionIsOn(cash, {}), false);
    assert.equal(sectionIsOn(income, { income: false }), true);
    assert.equal(sectionIsOn(cover, { cover: false, "cash-flow": true }), false);
    assert.equal(sectionIsOn(cash, { cover: false, "cash-flow": true }), true);
    const optional = [
      "cover",
      "contents",
      "directors-info",
      "directors-report",
      "directors-responsibilities",
      "compilation",
    ];
    for (const id of optional) {
      const row = section(id, id, "sections", "Sections", 1);
      row.lock = "user";
      row.default = "on";
      assert.equal(sectionIsOn(row, null), true);
      assert.equal(sectionIsOn(row, {}), true);
    }
  });
});
