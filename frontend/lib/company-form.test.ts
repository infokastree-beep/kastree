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

describe("editCompanyInitialValues", () => {
  it("fills the edit form from the saved company, including blank optional fields", () => {
    assert.deepEqual(
      editCompanyInitialValues({
        name: "Acme Ltd",
        functional_currency: "EUR",
        company_number: null,
        industry: null,
        company_type: "holding",
      }),
      {
        name: "Acme Ltd",
        functionalCurrency: "EUR",
        companyNumber: "",
        industry: "",
        companyType: "holding",
      },
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
    assert.equal(form.includes("initialValues?: CompanyEntityInitialValues"), true);
    assert.equal(form.includes("currencyChangeWarning"), true);
    assert.equal(form.includes('data-testid="company-currency-change-ack"'), true);
    assert.equal(detail.includes("editCompanyInitialValues(company)"), true);
    assert.equal(detail.includes("currencyChangeWarning="), true);
    assert.equal(create.includes("defaultCurrency={practiceCurrency.currency}"), true);
  });
});
