/**
 * Real date-range checks for GL period presets.
 * Run: node --experimental-strip-types --test lib/period-presets.test.ts
 */
import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  detectPeriodPreset,
  formatPresetRangeLabel,
  lastDayOfMonth,
  quarterMonthBounds,
  rangeForPreset,
} from "./period-presets.ts";

describe("rangeForPreset", () => {
  it("Full year → Jan 1 – Dec 31 of the relevant year", () => {
    const today = new Date(2026, 8, 11); // 11 Sep 2026
    assert.deepEqual(rangeForPreset("full_year", today), {
      start: "2026-01-01",
      end: "2026-12-31",
    });
  });

  it("This month → first and last day of the current month", () => {
    const today = new Date(2026, 8, 11); // September
    assert.deepEqual(rangeForPreset("this_month", today), {
      start: "2026-09-01",
      end: "2026-09-30",
    });
  });

  it("This month handles February in a leap year", () => {
    const today = new Date(2024, 1, 15); // 15 Feb 2024
    assert.deepEqual(rangeForPreset("this_month", today), {
      start: "2024-02-01",
      end: "2024-02-29",
    });
  });

  it("This month handles February in a common year", () => {
    const today = new Date(2026, 1, 10);
    assert.deepEqual(rangeForPreset("this_month", today), {
      start: "2026-02-01",
      end: "2026-02-28",
    });
  });

  it("This quarter → Q1 (Jan–Mar)", () => {
    const today = new Date(2026, 1, 20); // February
    assert.deepEqual(rangeForPreset("this_quarter", today), {
      start: "2026-01-01",
      end: "2026-03-31",
    });
  });

  it("This quarter → Q2 (Apr–Jun)", () => {
    const today = new Date(2026, 4, 1); // May
    assert.deepEqual(rangeForPreset("this_quarter", today), {
      start: "2026-04-01",
      end: "2026-06-30",
    });
  });

  it("This quarter → Q3 (Jul–Sep)", () => {
    const today = new Date(2026, 8, 11); // September
    assert.deepEqual(rangeForPreset("this_quarter", today), {
      start: "2026-07-01",
      end: "2026-09-30",
    });
  });

  it("This quarter → Q4 (Oct–Dec)", () => {
    const today = new Date(2026, 11, 25); // December
    assert.deepEqual(rangeForPreset("this_quarter", today), {
      start: "2026-10-01",
      end: "2026-12-31",
    });
  });
});

describe("detectPeriodPreset", () => {
  const today = new Date(2026, 8, 11);

  it("recognises Full year, This month, and This quarter", () => {
    assert.equal(
      detectPeriodPreset("2026-01-01", "2026-12-31", today),
      "full_year",
    );
    assert.equal(
      detectPeriodPreset("2026-09-01", "2026-09-30", today),
      "this_month",
    );
    assert.equal(
      detectPeriodPreset("2026-07-01", "2026-09-30", today),
      "this_quarter",
    );
  });

  it("falls back to Custom for a narrower manual window", () => {
    // The exact failure mode: user typed a short window and thought
    // the smaller TB was a full-year bug.
    assert.equal(
      detectPeriodPreset("2026-09-01", "2026-09-11", today),
      "custom",
    );
  });
});

describe("helpers", () => {
  it("lastDayOfMonth and quarterMonthBounds stay calendar-correct", () => {
    assert.equal(lastDayOfMonth(2026, 0), 31);
    assert.equal(lastDayOfMonth(2026, 1), 28);
    assert.equal(lastDayOfMonth(2024, 1), 29);
    assert.deepEqual(quarterMonthBounds(8), { startMonth: 6, endMonth: 8 });
  });

  it("formatPresetRangeLabel is human-readable", () => {
    assert.equal(
      formatPresetRangeLabel("2026-01-01", "2026-12-31"),
      "1 Jan 2026 → 31 Dec 2026",
    );
  });
});
