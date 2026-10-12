/** Companies Act 2014 company types. The first form choice is "Not recorded". */

export const LEGAL_FORM_CHOICES: ReadonlyArray<{ code: string; name: string }> = [
  { code: "ltd", name: "Private company limited by shares" },
  { code: "dac", name: "Designated activity company" },
  { code: "plc", name: "Public limited company" },
  { code: "clg", name: "Company limited by guarantee" },
  { code: "ulc", name: "Private unlimited company" },
  { code: "puc", name: "Public unlimited company" },
  {
    code: "pulc",
    name: "Public unlimited company with no share capital",
  },
];

export function legalFormCode(value: string): string | null {
  const text = value.trim().toLowerCase();
  if (text === "") return null;
  return LEGAL_FORM_CHOICES.some((row) => row.code === text) ? text : null;
}
