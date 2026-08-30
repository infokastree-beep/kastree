"use client";

import { ClerkProvider } from "@clerk/nextjs";
import type { ReactNode } from "react";
import { QueryProvider } from "@/components/providers/QueryProvider";
import { ClerkAuthBridge, MockAuthBridge } from "@/hooks/useAuth";

export const clerkReady = process.env.NEXT_PUBLIC_CLERK_READY === "true";

/**
 * When clerkReady is false (env unset or not exactly "true"):
 * - No ClerkProvider / no real session
 * - MockAuthBridge exposes isSignedIn=false and getToken→null (not a fake user)
 * - Middleware separately redirects all dashboard routes to `/`
 * So there is no authenticated-app path without explicitly enabling Clerk.
 */
export function AppProviders({ children }: { children: ReactNode }) {
  const withQuery = <QueryProvider>{children}</QueryProvider>;

  if (!clerkReady) {
    return <MockAuthBridge>{withQuery}</MockAuthBridge>;
  }

  return (
    <ClerkProvider>
      <ClerkAuthBridge>{withQuery}</ClerkAuthBridge>
    </ClerkProvider>
  );
}
