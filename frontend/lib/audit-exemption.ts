/** CRO Audit Exemption Statement page, printed on the balance sheet when the claim is true.
 * The workspace labels this wording source not confirmed.
 */

export const AUDIT_EXEMPTION_SOURCE_LABEL = "source not confirmed";

export const AUDIT_EXEMPTION_SOURCE = "CRO";

export const AUDIT_EXEMPTION_PROVISION = "Companies Act 2014, section 335";

export const AUDIT_EXEMPTION_SOURCE_STATUS = "researched (public source)";

export const AUDIT_EXEMPTION_PARAGRAPHS = [
  "I/We, as director(s) of (company name), state that:",
  "(a) the company is availing itself of the exemption provided for by Chapter 15 of Part 6 of the Companies Act 2014,",
  "(b) the company is availing itself of the exemption on the grounds that the conditions specified in s.358 are satisfied,",
  "(c) the shareholders of the company have not served a notice on the company under s.334(1) in accordance with s.334(2),",
  "(d) we acknowledge the company’s obligations under the Companies Act 2014, to keep adequate accounting records and prepare Financial Statements which give a true and fair view of the assets, liabilities and financial position of the company at the end of its financial year and of its profit or loss for such a year and to otherwise comply with the provisions of Companies Act 2014 relating to Financial Statements so far as they are applicable to the company,",
  "*(e) the company has relied on the specified exemption contained in s.352 Companies Act 2014;",
  "has done so on the grounds that the company is entitled to the benefit of that exemption as a small company and the abridged Financial Statements have been properly prepared in accordance with s.353 Companies Act 2014.",
  "(*In the above statement, use sections (a) – (d) if claiming audit exemption and add section (e) if claiming the small company/abridgement exemption. A small company can claim either or both exemptions in their Financial Statements if they qualify.)",
] as const;

export const AUDIT_EXEMPTION_NOTE = "This page is an explanatory note. The audit exemption statement is printed on the balance sheet, immediately above the directors' signatures, as section 335 of the Companies Act 2014 requires.";

export const AUDIT_POSITION_FINAL_LOCK = "Locked: this draft is final";

const _MONTHS = [
  "January",
  "February",
  "March",
  "April",
  "May",
  "June",
  "July",
  "August",
  "September",
  "October",
  "November",
  "December",
] as const;

function omitFromPrint(paragraph: string): boolean {
  return (
    paragraph.startsWith("(*") ||
    paragraph.includes("use sections (a)") ||
    paragraph.startsWith("*(e)") ||
    paragraph.startsWith("(e)") ||
    paragraph.startsWith("has done so on the grounds")
  );
}

/** Sections (a) to (d), with the recorded company name. This is what prints. */
export function printedAuditExemption(companyName: string): string[] {
  const recorded = companyName.trim() || "the company (name not recorded)";
  return AUDIT_EXEMPTION_PARAGRAPHS.filter((paragraph) => !omitFromPrint(paragraph)).map(
    (paragraph) => paragraph.replace("(company name)", recorded),
  );
}

/** The CRO sample lines that a document does not print.

The opening line is also kept here with the literal "(company name)". The
printed copy replaces that placeholder.
*/
export function unprintedAuditExemptionSource(): string[] {
  const template = AUDIT_EXEMPTION_PARAGRAPHS.filter((paragraph) =>
    paragraph.includes("(company name)"),
  );
  return [
    ...template,
    ...AUDIT_EXEMPTION_PARAGRAPHS.filter((paragraph) => omitFromPrint(paragraph)),
  ];
}

export function approvalDateLine(approvalDate: string | null): string {
  const recorded = approvalDate?.trim() ?? "";
  if (recorded === "") {
    return "Approval date has not been recorded.";
  }
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(recorded);
  if (match === null) {
    return `Approved on ${recorded}.`;
  }
  const month = _MONTHS[Number(match[2]) - 1];
  if (month === undefined) {
    return `Approved on ${recorded}.`;
  }
  return `Approved on ${Number(match[3])} ${month} ${match[1]}.`;
}

export const AUDIT_EXEMPTION_ABRIDGEMENT_NOTE =
  "Item (e), and the sentence that follows it, is the small-company abridgement exemption in sections 352 and 353 of the Companies Act 2014. The CRO sample adds it only when the company also claims that exemption. It needs a separate recorded claim. It is not printed.";
