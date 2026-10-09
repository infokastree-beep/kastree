/**
 * A currency change is not sent until the acknowledgement is checked
 * when the company already has trial balances.
 * Run: node --experimental-strip-types --test lib/company-form.test.ts
 */
import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { currencyChangeAllowed, defaultCompanyCurrency } from "./company-form.ts";

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
