import { notFound } from "next/navigation";
import type { ReactNode } from "react";

/**
 * These pages are local previews. A production build does not render them.
 * Middleware also answers 404 for /dev before Clerk's public bypass.
 */
export default function DevPreviewLayout({ children }: { children: ReactNode }) {
  if (process.env.NODE_ENV === "production") {
    notFound();
  }
  return children;
}
