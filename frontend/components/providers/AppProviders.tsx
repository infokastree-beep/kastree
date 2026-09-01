"use client";

import { ClerkProvider } from "@clerk/nextjs";
import type { ReactNode } from "react";
import { QueryProvider } from "@/components/providers/QueryProvider";
import { ClerkAuthBridge, MockAuthBridge } from "@/hooks/useAuth";
import { clerkReady } from "@/lib/clerk";
import { POST_AUTH_PATH } from "@/lib/constants";

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
    <ClerkProvider
      signInForceRedirectUrl={POST_AUTH_PATH}
      signUpForceRedirectUrl={POST_AUTH_PATH}
    >
      <ClerkAuthBridge>{withQuery}</ClerkAuthBridge>
    </ClerkProvider>
  );
}
