/**
 * The company-details country control lists names and posts a two-letter code.
 * Run: node --experimental-strip-types --test lib/countries.test.ts
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";
import { countryChoices } from "./countries.ts";

const here = dirname(fileURLToPath(import.meta.url));

describe("countryChoices", () => {
  it("lists Ireland first and shows the English name for a code", () => {
    const choices = countryChoices("");
    assert.equal(choices[0]?.code, "IE");
    assert.equal(choices[0]?.name, "Ireland");
    assert.equal(
      choices.find((row) => row.code === "US")?.name,
      "United States of America",
    );
    const names = choices.map((row) => row.name);
    assert.ok(names.indexOf("Afghanistan") < names.indexOf("Zimbabwe"));
    assert.equal(new Set(choices.map((row) => row.code)).size, choices.length);
  });

  it("keeps a stored code that is not in the list", () => {
    const choices = countryChoices("xx");
    assert.equal(choices.at(-1)?.code, "XX");
    assert.equal(choices.at(-1)?.name, "XX");
    assert.equal(
      countryChoices("US").filter((row) => row.code === "US").length,
      1,
    );
  });
});

describe("company details form", () => {
  it("offers country names on the page the Fix link opens", () => {
    const source = readFileSync(
      join(here, "../components/statutory/CompanyDetailsForm.tsx"),
      "utf8",
    );
    assert.match(source, /Country of incorporation/);
    assert.match(source, /data-testid="company-country-of-incorporation"/);
    assert.match(source, /<select/);
    assert.match(source, /Not recorded/);
    assert.match(source, /countryChoices\(country\)/);
    assert.match(source, /\{row\.name\}/);
    assert.match(source, /country_of_incorporation: country\.trim\(\) === "" \? null : country\.trim\(\)/);
    const server = readFileSync(
      join(here, "../../backend/app/data/countries.json"),
      "utf8",
    );
    const browser = readFileSync(join(here, "countries.json"), "utf8");
    assert.equal(browser, server);
  });
});
