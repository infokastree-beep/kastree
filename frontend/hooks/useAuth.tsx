"use client";

import { createContext, useContext, type ReactNode } from "react";
import { useAuth as useClerkAuth } from "@clerk/nextjs";

export type AuthValue = {
  isLoaded: boolean;
  isSignedIn: boolean;
  userId: string | null;
  orgId: string | null;
  getToken: () => Promise<string | null>;
};

const AuthContext = createContext<AuthValue | null>(null);

const mockAuth: AuthValue = {
  isLoaded: true,
  isSignedIn: false,
  userId: null,
  orgId: null,
  getToken: async () => null,
};

export function ClerkAuthBridge({ children }: { children: ReactNode }) {
  const { isLoaded, isSignedIn, userId, orgId, getToken } = useClerkAuth();
  const value: AuthValue = {
    isLoaded,
    isSignedIn: Boolean(isSignedIn),
    userId: userId ?? null,
    orgId: orgId ?? null,
    getToken,
  };
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function MockAuthBridge({ children }: { children: ReactNode }) {
  return <AuthContext.Provider value={mockAuth}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used within AppProviders");
  }
  return ctx;
}
