"use client";

import Link from "next/link";
import { SignUp } from "@clerk/nextjs";
import { KastreeLogo } from "@/components/brand/KastreeLogo";
import { clerkReady } from "@/lib/clerk";
import { POST_AUTH_PATH } from "@/lib/constants";

export default function SignUpPage() {
  if (!clerkReady) {
    return (
      <main className="mx-auto flex min-h-screen max-w-lg flex-col justify-center gap-4 px-4">
        <h1 className="text-xl font-semibold">Sign up</h1>
        <p className="text-sm text-stone-600">
          Configure Clerk keys and set{" "}
          <code className="font-mono text-xs">NEXT_PUBLIC_CLERK_READY=true</code> to
          enable sign-up.
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
      <SignUp
        routing="path"
        path="/sign-up"
        signInUrl="/sign-in"
        forceRedirectUrl={POST_AUTH_PATH}
      />
    </main>
  );
}
