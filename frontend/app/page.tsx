"use client";

import Link from "next/link";
import { SignInButton, UserButton } from "@clerk/nextjs";
import { useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { clerkReady } from "@/components/providers/AppProviders";
import { useAuth } from "@/hooks/useAuth";
import { APP_NAME } from "@/lib/constants";

function HomeContent() {
  const { isSignedIn } = useAuth();
  const params = useSearchParams();
  const redirectedForClerk = params.get("clerk") === "required";

  return (
    <main className="mx-auto flex min-h-screen max-w-3xl flex-col justify-center gap-6 px-6 py-16">
      <p className="text-sm font-medium uppercase tracking-wide text-stone-500">
        Financial intelligence
      </p>
      <h1 className="text-4xl font-semibold tracking-tight">{APP_NAME}</h1>
      <p className="max-w-xl text-lg text-stone-600">
        Upload a trial balance, confirm account mappings, and review SOPL / SOFP /
        SOCIE in minutes.
      </p>
      {!clerkReady ? (
        <div className="space-y-3">
          {redirectedForClerk ? (
            <p className="rounded border border-stone-300 bg-stone-100 px-3 py-2 text-sm text-stone-800">
              Sign-in is required. Clerk is not enabled in this environment.
            </p>
          ) : null}
          <p className="rounded border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-950">
            Clerk is not configured. Set{" "}
            <code className="font-mono text-xs">NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY</code>,{" "}
            <code className="font-mono text-xs">CLERK_SECRET_KEY</code>, and{" "}
            <code className="font-mono text-xs">NEXT_PUBLIC_CLERK_READY=true</code> in{" "}
            <code className="font-mono text-xs">.env.local</code>, then restart the
            frontend. Until then there is no path into upload, mapping, or the
            dashboard.
          </p>
        </div>
      ) : (
        <div className="flex flex-wrap gap-3">
          {!isSignedIn ? (
            <>
              <SignInButton mode="redirect">
                <button
                  type="button"
                  className="rounded bg-stone-900 px-4 py-2 text-sm font-medium text-white"
                >
                  Sign in
                </button>
              </SignInButton>
              <Link
                href="/sign-up"
                className="rounded border border-stone-300 px-4 py-2 text-sm font-medium"
              >
                Create account
              </Link>
            </>
          ) : (
            <>
              <Link
                href="/upload"
                className="rounded bg-stone-900 px-4 py-2 text-sm font-medium text-white"
              >
                Go to upload
              </Link>
              <UserButton afterSignOutUrl="/" />
            </>
          )}
        </div>
      )}
    </main>
  );
}

export default function HomePage() {
  return (
    <Suspense fallback={<main className="p-8 text-sm text-stone-600">Loading…</main>}>
      <HomeContent />
    </Suspense>
  );
}
