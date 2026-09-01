"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { SignIn } from "@clerk/nextjs";
import { useAuth } from "@/hooks/useAuth";
import { POST_AUTH_PATH } from "@/lib/constants";

const LOAD_TIMEOUT_MS = 10_000;

/**
 * Clerk's <SignIn> renders nothing until the browser SDK finishes loading.
 * Show SSR-visible fallback copy immediately, then swap in the widget or an
 * actionable error if initialization stalls (e.g. origin not allowed).
 */
export function ClerkSignInPanel() {
  const { isLoaded } = useAuth();
  const [timedOut, setTimedOut] = useState(false);

  useEffect(() => {
    if (isLoaded) {
      setTimedOut(false);
      return;
    }
    const timer = window.setTimeout(() => setTimedOut(true), LOAD_TIMEOUT_MS);
    return () => window.clearTimeout(timer);
  }, [isLoaded]);

  if (isLoaded) {
    return (
      <SignIn
        routing="path"
        path="/sign-in"
        signUpUrl="/sign-up"
        forceRedirectUrl={POST_AUTH_PATH}
      />
    );
  }

  return (
    <div className="w-full max-w-md space-y-4 text-center">
      <h1 className="text-xl font-semibold text-stone-900">Sign in</h1>
      {timedOut ? (
        <>
          <p className="text-sm text-stone-600">
            The sign-in form did not load. This usually means the current site
            URL is not listed in your Clerk application&apos;s allowed domains
            (e.g. add your Vercel preview URL or custom domain in the Clerk
            dashboard).
          </p>
          <p className="text-xs text-stone-500">
            Check the browser console for an &quot;Invalid HTTP Origin
            header&quot; error from Clerk.
          </p>
        </>
      ) : (
        <p className="text-sm text-stone-600">Loading sign-in…</p>
      )}
      <Link href="/" className="inline-block text-sm text-stone-900 underline">
        Back home
      </Link>
    </div>
  );
}
