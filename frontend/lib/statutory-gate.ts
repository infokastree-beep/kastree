/** Copy under the statutory sign-off sentence. Does not decide access. */

export const STATUTORY_SIGNOFF =
  "Draft statutory packs stay limited to platform administrators until a qualified reviewer signs off the wording.";

export const ASK_OWNER =
  "Ask an owner or admin of this practice to turn on statutory drafts.";

export const UNREVIEWED_WORDING_BANNER =
  "The statutory wording is unreviewed and this practice reviews every output itself.";

export type Product2Access = {
  enabled: boolean;
  acknowledged: boolean;
  source: "practice" | "admin" | null;
  wording_signed_off: boolean;
};

export type StatutoryUser = {
  email: string;
  role: "owner" | "admin" | "member" | "viewer";
  is_platform_admin: boolean;
  product2_access?: Product2Access;
};

/** Workspace opens when the practice has turned drafts on, or the caller is a platform admin.

An absent product2_access means this frontend is talking to an older API, so the
previous platform-admin check still applies.
*/
export function statutoryWorkspaceOpen(
  me: StatutoryUser | undefined,
): boolean {
  if (!me) {
    return false;
  }
  if (me.product2_access) {
    return me.product2_access.enabled;
  }
  return me.is_platform_admin === true;
}

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
