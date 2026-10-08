/**
 * Auth-free pages under /dev are for local preview only.
 * /development is a different path and stays available.
 */
export function isDevPreviewPath(pathname: string): boolean {
  return pathname === "/dev" || pathname.startsWith("/dev/");
}

/** Production serves none of the /dev previews. Other environments still do. */
export function devPreviewBlocked(
  pathname: string,
  nodeEnv: string | undefined,
): boolean {
  return nodeEnv === "production" && isDevPreviewPath(pathname);
}
