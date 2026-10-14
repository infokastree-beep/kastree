/**
 * Legal form is a listed company type. A blank choice is not recorded.
 * Run: node --experimental-strip-types --test lib/legal-form.test.ts
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";
import { LEGAL_FORM_CHOICES, legalFormCode } from "./legal-forms.ts";

const here = dirname(fileURLToPath(import.meta.url));
const pack = JSON.parse(
  readFileSync(
    join(here, "../../findraft/content/frs102-1a-ie/2024.09/pack.json"),
    "utf8",
  ),
) as {
  company_legal_forms: {
    source_status: string;
    forms: { code: string; name: string }[];
  };
  data_checks: { source_status: string };
};

describe("legal form choices", () => {
  it("matches the researched pack list and does not preselect a type", () => {
    assert.equal(
      pack.company_legal_forms.source_status,
      "researched (public source)",
    );
    assert.equal(pack.data_checks.source_status, "reviewer-to-confirm");
    assert.deepEqual(
      LEGAL_FORM_CHOICES.map((row) => [row.code, row.name]),
      pack.company_legal_forms.forms.map((row) => [row.code, row.name]),
    );
    assert.equal(legalFormCode(""), null);
    assert.equal(legalFormCode("ltd"), "ltd");
    assert.equal(legalFormCode("LLC"), null);

    const form = readFileSync(
      join(here, "../components/clients/CompanyEntityForm.tsx"),
      "utf8",
    );
    const details = readFileSync(
      join(here, "../components/statutory/CompanyDetailsForm.tsx"),
      "utf8",
    );
    const workspace = readFileSync(
      join(here, "../components/statutory/StatutoryDraftWorkspace.tsx"),
      "utf8",
    );
    assert.match(form, /data-testid="company-form-legal-form"/);
    assert.match(form, /<option value="">Not recorded<\/option>/);
    assert.match(form, /useState\(initialValues\?\.legalForm \?\? ""\)/);
    assert.equal(form.includes('useState("ltd")'), false);
    assert.match(details, /data-testid="company-details-legal-form"/);
    assert.match(details, /disabled=\{locked \|\| !canRecordLegalForm\}/);
    assert.match(workspace, /canRecordLegalForm=\{canRecordClaim\}/);
  });
});
