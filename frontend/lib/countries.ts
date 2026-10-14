import countries from "./countries.json" with { type: "json" };

export type CountryChoice = {
  code: string;
  name: string;
};

const LIST = countries as CountryChoice[];

/** Ireland first, then English name order. An unlisted stored code stays visible. */
export function countryChoices(current: string): CountryChoice[] {
  const ireland = LIST.filter((row) => row.code === "IE");
  const rest = LIST.filter((row) => row.code !== "IE").sort((left, right) =>
    left.name.localeCompare(right.name, "en"),
  );
  const ordered = [...ireland, ...rest];
  const code = current.trim().toUpperCase();
  if (code !== "" && !ordered.some((row) => row.code === code)) {
    ordered.push({ code, name: code });
  }
  return ordered;
}
