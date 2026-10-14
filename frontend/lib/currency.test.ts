import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import { formatCurrency, formatStoredAmount } from "./currency.ts";

test("formatCurrency matches the backend penny format", () => {
  assert.equal(formatCurrency("1234567.89", "GBP"), "£1,234,567.89");
  assert.equal(formatCurrency("1234567.89", "USD"), "$1,234,567.89");
  assert.equal(formatCurrency("1234567.89", "EUR"), "€1,234,567.89");
  assert.equal(formatCurrency("-100.50", "EUR"), "-€100.50");
  assert.equal(formatCurrency("30000", "GBP"), "£30,000.00");
  assert.equal(formatCurrency("30000", "EUR"), "€30,000.00");
  assert.equal(formatCurrency("455812.00", "EUR"), "€455,812.00");
  assert.equal(formatCurrency("157650.00", "EUR"), "€157,650.00");
});

test("cents round half to even without using a binary float", () => {
  assert.equal(formatCurrency("1.005", "EUR"), "€1.00");
  assert.equal(formatCurrency("1.015", "EUR"), "€1.02");
  assert.equal(formatCurrency("1.025", "EUR"), "€1.02");
  assert.equal(formatCurrency("9.995", "GBP"), "£10.00");
  assert.equal(formatCurrency("-0.001", "EUR"), "€0.00");
});

test("a missing figure is a dash and a present figure keeps the stored string", () => {
  assert.equal(formatStoredAmount(null, "EUR"), "—");
  assert.equal(formatStoredAmount("", "EUR"), "—");
  assert.equal(formatStoredAmount("455812.00", null), "455,812.00");
});

test("the review dashboard renders the key figures through the shared formatter", () => {
  const workspace = readFileSync(
    new URL("../components/statutory/StatutoryDraftWorkspace.tsx", import.meta.url),
    "utf8",
  );
  const card = readFileSync(
    new URL("../components/statutory/KeyFiguresCard.tsx", import.meta.url),
    "utf8",
  );
  assert.equal(workspace.includes("KeyFiguresCard"), true);
  assert.equal(workspace.includes('data-testid="statutory-review-dashboard"'), true);
  assert.equal(card.includes("formatStoredAmount"), true);
  assert.equal(card.includes("parseFloat"), false);
  assert.equal(card.includes("Net assets"), true);
  assert.equal(card.includes("Balance sheet total"), true);
});
