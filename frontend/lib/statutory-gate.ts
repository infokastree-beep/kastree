/** Copy under the statutory sign-off sentence. Does not decide access. */

export const STATUTORY_SIGNOFF =
  "Draft statutory packs stay limited to platform administrators until a qualified reviewer signs off the wording.";

const MISSING_EMAIL =
  "We could not read your account email. Sign out and back in.";

/**
 * Names the signed-in account `/users/me` already returned.
 * Pass only that account's email. An empty value means the profile had none.
 */
export function statutoryGateDiagnosis(
  email: string | null | undefined,
): string {
  const trimmed = typeof email === "string" ? email.trim() : "";
  if (trimmed.length === 0) {
    return MISSING_EMAIL;
  }
  return `Signed in as ${trimmed}. This account is not on the platform administrator list.`;
}
