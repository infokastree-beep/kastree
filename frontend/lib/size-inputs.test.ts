/**
 * Size inputs for the fictional QA company display as currency, never as a raw float.
 * Run: node --experimental-strip-types --test lib/size-inputs.test.ts
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";
import { formatCurrency } from "./currency.ts";
import {
  sizeAmountToApi,
  sizeEmployeesLabel,
  sizeEmployeesToApi,
  sizeMoneyLabel,
} from "./size-inputs.ts";

describe("QA company size inputs", () => {
  it("sends turnover 100,000 and balance sheet total 35,000 as exact cents", () => {
    assert.equal(sizeAmountToApi("100,000"), "100000.00");
    assert.equal(sizeAmountToApi("35000"), "35000.00");
    assert.equal(sizeAmountToApi("€35,000.00"), "35000.00");
    assert.equal(sizeEmployeesToApi("677"), 677);
  });

  it("shows those figures in the company currency and leaves a blank as not recorded", () => {
    assert.equal(sizeMoneyLabel("100000.00", "EUR", formatCurrency), "€100,000.00");
    assert.equal(sizeMoneyLabel("35000.00", "EUR", formatCurrency), "€35,000.00");
    assert.equal(sizeMoneyLabel("100000.00", "GBP", formatCurrency), "£100,000.00");
    assert.equal(sizeEmployeesLabel(677), "677");
    assert.equal(sizeMoneyLabel(null, "EUR", formatCurrency), "not recorded");
    assert.equal(sizeEmployeesLabel(null), "not recorded");
  });

  it("rejects a figure that is not exact cents", () => {
    assert.equal(sizeAmountToApi("100000.001"), null);
    assert.equal(sizeAmountToApi(""), null);
    assert.equal(sizeEmployeesToApi(""), null);
    assert.equal(sizeEmployeesToApi("-1"), null);
  });

  it("shows the stored size message and does not say eligible", () => {
    const root = dirname(fileURLToPath(import.meta.url));
    const component = readFileSync(
      join(root, "../components/statutory/SizeInputs.tsx"),
      "utf8",
    );
    const workspace = readFileSync(
      join(root, "../components/statutory/StatutoryDraftWorkspace.tsx"),
      "utf8",
    );
    assert.match(component, /data-testid="size-rule-message"/);
    assert.match(component, /data-testid="size-inputs-locked"/);
    assert.match(component, /const editable = canEdit && lockLabel == null/);
    assert.match(component, /\{message\}/);
    assert.equal(/eligible/i.test(component), false);
    assert.match(workspace, /message=\{yearEnd\.size_message\}/);
  });
});
