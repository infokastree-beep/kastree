/**
 * Plain-English reason for one notes-library row.
 * The sentence names a line or a question. It does not name an amount.
 */

export type NoteReason =
  | "always"
  | "trial_balance"
  | "disclosure_yes"
  | "unanswered"
  | "disclosure_no"
  | "omitted"
  | "added";

export type NoteLibraryRow = {
  block_id: string;
  title: string;
  reason: NoteReason;
  sentence: string;
  can_omit: boolean;
  can_restore: boolean;
  can_add: boolean;
  can_remove: boolean;
};

export function reasonSentence(
  reason: NoteReason,
  subject: string,
  included: boolean,
): string {
  if (reason === "always") {
    return "This note is always included.";
  }
  if (reason === "trial_balance") {
    if (included) {
      return `Included because ${subject} has a balance.`;
    }
    return `Left out because ${subject} has no balance.`;
  }
  if (reason === "disclosure_yes") {
    return `Included because the answer to “${subject}” is Yes.`;
  }
  if (reason === "unanswered") {
    return `Waiting for an answer to “${subject}”.`;
  }
  if (reason === "disclosure_no") {
    return `Left out because the answer to “${subject}” is No.`;
  }
  if (reason === "omitted") {
    return `Omitted as immaterial. The answer to “${subject}” is still Yes.`;
  }
  return `Added by the preparer. The answer to “${subject}” is No.`;
}
