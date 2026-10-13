/** Practice letterhead. The compilation report prints these three facts. */

export type PracticeLetterhead = {
  name: string;
  letterhead_address: string;
  letterhead_contact: string;
};

export const LETTERHEAD_HINT =
  "Printed on the compilation report. The report wording is pending the professional body's illustrative text.";

export function canEditPracticeLetterhead(role: string | null | undefined): boolean {
  return role === "owner" || role === "admin";
}

/** The settings save sends the legal name, address, and contact only. */
export function letterheadUpdateBody(value: PracticeLetterhead): PracticeLetterhead {
  return {
    name: value.name,
    letterhead_address: value.letterhead_address,
    letterhead_contact: value.letterhead_contact,
  };
}
