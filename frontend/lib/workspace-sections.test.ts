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
  sectionsForFramework,
  type ReportingFramework,
} from "./workspace-sections.ts";

const frameworks: ReportingFramework[] = [
  {
    id: "frs102-1a-ie",
    label: "FRS 102 Section 1A (Ireland)",
    available: true,
    sections: [
      { id: "report-setup", label: "Report setup" },
      { id: "sub-lines", label: "Sub-line review" },
      { id: "disclosures", label: "Disclosures" },
      { id: "adjustments", label: "Adjustments" },
      { id: "review", label: "Review dashboard" },
      { id: "income", label: "Income statement" },
      { id: "sofp", label: "Statement of financial position" },
    ],
  },
  {
    id: "form11-summary",
    label: "Sole Trader / Form 11 Summary",
    available: false,
    sections: [
      { id: "report-setup", label: "Report setup" },
      { id: "extracts", label: "Extracts summary" },
      { id: "review", label: "Review dashboard" },
    ],
  },
];

describe("sectionsForFramework", () => {
  it("returns a shorter list for Form 11 than for FRS 102", () => {
    const frs = sectionsForFramework(frameworks, "frs102-1a-ie").map(
      (section) => section.label,
    );
    const form11 = sectionsForFramework(frameworks, "form11-summary").map(
      (section) => section.label,
    );
    assert.deepEqual(form11, [
      "Report setup",
      "Extracts summary",
      "Review dashboard",
    ]);
    assert.equal(frs.includes("Extracts summary"), false);
    assert.equal(form11.includes("Sub-line review"), false);
    assert.ok(form11.length < frs.length);
  });

  it("does not fall back to the FRS 102 list for an unknown framework", () => {
    const unknown = sectionsForFramework(frameworks, "uk-frs105").map(
      (section) => section.id,
    );
    assert.deepEqual(unknown, ["report-setup", "review"]);
    assert.equal(activeSection(
      sectionsForFramework(frameworks, "form11-summary"),
      "sub-lines",
    ), "review");
  });

  it("the sidebar component does not name a framework", () => {
    const here = dirname(fileURLToPath(import.meta.url));
    const source = readFileSync(
      join(here, "../components/statutory/WorkspaceSidebar.tsx"),
      "utf8",
    );
    assert.equal(source.includes("frs102"), false);
    assert.equal(source.includes("form11"), false);
    assert.equal(source.includes("Sub-line review"), false);
  });
});
