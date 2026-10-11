/**
 * A currency change is not sent until the acknowledgement is checked
 * when the company already has trial balances.
 * Run: node --experimental-strip-types --test lib/company-form.test.ts
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";
import {
  currencyChangeAllowed,
  defaultCompanyCurrency,
  defaultCountryOfIncorporation,
  editCompanyInitialValues,
} from "./company-form.ts";

const here = dirname(fileURLToPath(import.meta.url));

describe("currencyChangeAllowed", () => {
  it("allows a currency change when the company has no trial balances", () => {
    assert.equal(
      currencyChangeAllowed({
        currentCurrency: "GBP",
        nextCurrency: "EUR",
        hasTrialBalances: false,
        acknowledged: false,
      }),
      true,
    );
  });

  it("blocks a currency change with trial balances until acknowledged", () => {
    assert.equal(
      currencyChangeAllowed({
        currentCurrency: "GBP",
        nextCurrency: "EUR",
        hasTrialBalances: true,
        acknowledged: false,
      }),
      false,
    );
    assert.equal(
      currencyChangeAllowed({
        currentCurrency: "GBP",
        nextCurrency: "EUR",
        hasTrialBalances: true,
        acknowledged: true,
      }),
      true,
    );
  });

  it("does not require acknowledgement when the currency is unchanged", () => {
    assert.equal(
      currencyChangeAllowed({
        currentCurrency: "gbp",
        nextCurrency: "GBP",
        hasTrialBalances: true,
        acknowledged: false,
      }),
      true,
    );
  });
});

describe("defaultCompanyCurrency", () => {
  it("preselects euro for an Irish practice and pound otherwise", () => {
    assert.equal(defaultCompanyCurrency("IE"), "EUR");
    assert.equal(defaultCompanyCurrency("GB"), "GBP");
    assert.equal(defaultCompanyCurrency(null), "GBP");
    assert.equal(defaultCompanyCurrency(undefined), "GBP");
  });
});

describe("defaultCountryOfIncorporation", () => {
  it("preselects Ireland only when the practice jurisdiction is Ireland", () => {
    assert.equal(defaultCountryOfIncorporation("IE"), "IE");
    assert.equal(defaultCountryOfIncorporation("GB"), "");
    assert.equal(defaultCountryOfIncorporation("US"), "");
    assert.equal(defaultCountryOfIncorporation(null), "");
    assert.equal(defaultCountryOfIncorporation(undefined), "");
  });
});

describe("editCompanyInitialValues", () => {
  it("fills the edit form from the saved company, including a blank country", () => {
    assert.deepEqual(
      editCompanyInitialValues({
        name: "Acme Ltd",
        functional_currency: "EUR",
        country_of_incorporation: null,
        company_number: null,
        industry: null,
        company_type: "holding",
      }),
      {
        name: "Acme Ltd",
        functionalCurrency: "EUR",
        countryOfIncorporation: "",
        companyNumber: "",
        industry: "",
        companyType: "holding",
      },
    );
  });

  it("shows the stored country on the edit form", () => {
    assert.equal(
      editCompanyInitialValues({
        name: "Acme Ltd",
        functional_currency: "EUR",
        country_of_incorporation: "IE",
        company_type: "trading",
      }).countryOfIncorporation,
      "IE",
    );
    assert.equal(
      editCompanyInitialValues({
        name: "Acme Ltd",
        functional_currency: "USD",
        country_of_incorporation: "US",
        company_type: "trading",
      }).countryOfIncorporation,
      "US",
    );
  });
});

describe("edit company form props", () => {
  it("keeps initial values, the currency acknowledgement, and the jurisdiction default", () => {
    const form = readFileSync(
      join(here, "../components/clients/CompanyEntityForm.tsx"),
      "utf8",
    );
    const detail = readFileSync(
      join(here, "../components/clients/ClientDetail.tsx"),
      "utf8",
    );
    const create = readFileSync(
      join(here, "../components/clients/CreateClientForm.tsx"),
      "utf8",
    );
    const upload = readFileSync(
      join(here, "../components/upload/UploadForm.tsx"),
      "utf8",
    );
    const workspace = readFileSync(
      join(here, "../components/statutory/StatutoryDraftWorkspace.tsx"),
      "utf8",
    );
    assert.equal(form.includes("initialValues?: CompanyEntityInitialValues"), true);
    assert.equal(form.includes("currencyChangeWarning"), true);
    assert.equal(form.includes('data-testid="company-currency-change-ack"'), true);
    assert.equal(form.includes('data-testid="company-form-country"'), true);
    assert.equal(form.includes("Country of incorporation"), true);
    assert.equal(
      form.includes(
        "initialValues?.countryOfIncorporation ?? defaultCountryOfIncorporation",
      ),
      true,
    );
    assert.equal(detail.includes("editCompanyInitialValues(company)"), true);
    assert.equal(detail.includes("currencyChangeWarning="), true);
    assert.equal(
      detail.includes(
        "defaultCountryOfIncorporation={practiceCurrency.countryOfIncorporation}",
      ),
      true,
    );
    assert.equal(create.includes("defaultCurrency={practiceCurrency.currency}"), true);
    assert.equal(
      create.includes(
        "defaultCountryOfIncorporation={practiceCurrency.countryOfIncorporation}",
      ),
      true,
    );
    assert.equal(
      upload.includes(
        "defaultCountryOfIncorporation={practiceCurrency.countryOfIncorporation}",
      ),
      true,
    );
    assert.equal(workspace.includes('check.code === "V-CO-008"'), true);
    assert.equal(workspace.includes('check.code === "V-CO-009"'), true);
    assert.equal(
      workspace.includes('data-testid="country-incorporation-notice"') ||
        workspace.includes('"country-incorporation-notice"'),
      true,
    );
    assert.equal(workspace.includes("{check.message}"), true);
  });
});
