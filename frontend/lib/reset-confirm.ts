/** Reset stays local until the practice confirms. */

export const RESET_CONFIRM_MESSAGE =
  "Reset to pack defaults? Saved settings on this draft will be cleared.";

export type ResetConfirmState = "closed" | "open";
export type ResetConfirmAction = "open" | "cancel" | "reset";

export function resetConfirmAfter(
  state: ResetConfirmState,
  action: ResetConfirmAction,
): { state: ResetConfirmState; send: boolean } {
  if (action === "open") {
    return { state: "open", send: false };
  }
  if (action === "cancel") {
    return { state: "closed", send: false };
  }
  return { state: "closed", send: state === "open" };
}
