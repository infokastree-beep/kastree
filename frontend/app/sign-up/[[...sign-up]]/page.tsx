"use client";

import Link from "next/link";
import { SignUp } from "@clerk/nextjs";
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
    <main className="flex min-h-screen items-center justify-center px-4">
      <SignUp
        routing="path"
        path="/sign-up"
        signInUrl="/sign-in"
        forceRedirectUrl={POST_AUTH_PATH}
      />
    </main>
  );
}
