"use client";

import Link from "next/link";
import { ClerkSignInPanel } from "@/components/auth/ClerkSignInPanel";
import { KastreeLogo } from "@/components/brand/KastreeLogo";
import { clerkReady } from "@/lib/clerk";

export default function SignInPage() {
  if (!clerkReady) {
    return (
      <main className="mx-auto flex min-h-screen max-w-lg flex-col justify-center gap-4 px-4">
        <Link href="/" className="inline-flex">
          <KastreeLogo className="h-16 w-auto" />
        </Link>
        <h1 className="text-xl font-semibold">Sign in</h1>
        <p className="text-sm text-stone-600">
          Configure Clerk keys and set{" "}
          <code className="font-mono text-xs">NEXT_PUBLIC_CLERK_READY=true</code> to
          enable sign-in.
        </p>
        <Link href="/" className="text-sm text-stone-900 underline">
          Back home
        </Link>
      </main>
    );
  }

  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-8 px-4 py-10">
      <Link href="/" className="inline-flex">
        <KastreeLogo className="h-16 w-auto" />
      </Link>
      <ClerkSignInPanel />
    </main>
  );
}
