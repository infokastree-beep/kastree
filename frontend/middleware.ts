import { clerkMiddleware, createRouteMatcher } from "@clerk/nextjs/server";
import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

/** Protect every route under the (dashboard) group (URL paths, not the group name). */
const isDashboardRoute = createRouteMatcher([
  "/upload(.*)",
  "/mapping(.*)",
  "/dashboard(.*)",
  "/clients(.*)",
  "/notifications(.*)",
  "/settings(.*)",
  "/onboarding(.*)",
]);

/**
 * Strict equality: unset / missing / any value other than the string "true"
 * means Clerk is NOT ready. That is the safe default for misconfigured deploys.
 *
 * When false: dashboard routes are redirected home — no session bypass, no
 * preview path into the authenticated app. When true: Clerk middleware runs
 * and auth().protect() gates those routes.
 */
import { clerkReady } from "@/lib/clerk";

const clerkHandler = clerkMiddleware(async (auth, request) => {
  if (isDashboardRoute(request)) {
    await auth().protect();
  }
});

function safePlaceholderMiddleware(request: NextRequest) {
  if (isDashboardRoute(request)) {
    const home = new URL("/", request.url);
    home.searchParams.set("clerk", "required");
    return NextResponse.redirect(home);
  }
  return NextResponse.next();
}

export default clerkReady ? clerkHandler : safePlaceholderMiddleware;

export const config = {
  matcher: [
    "/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)",
    "/(api|trpc)(.*)",
  ],
};
