"use client";

import Link from "next/link";
import { SignInNavLink } from "@/components/auth/SignInNavLink";
import { MarketingBrandLink } from "@/components/landing/MarketingBrandLink";
import { clerkReady } from "@/lib/clerk";
import { useAuth } from "@/hooks/useAuth";
import { POST_AUTH_PATH } from "@/lib/constants";

const NAV_LINKS = [
  { href: "/pricing", label: "Pricing" },
  { href: "/about", label: "About" },
  { href: "/contact", label: "Contact" },
] as const;

export function MarketingNav() {
  const { isSignedIn } = useAuth();

  return (
    // Same stacking class as CopilotPanel vs Statements switcher:
    // 1) Header needs an explicit z-index so overflowing UI sits above later
    //    page layers (hero `position:relative`).
    // 2) backdrop-blur must NOT wrap interactive chrome — Chrome composites
    //    overflowing descendants of a backdrop-filter element as frost. Keep
    //    blur on a clipped inset layer; nav links stay outside.
    <header className="relative z-50 border-b border-line/80">
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 bg-surface-elevated/90 backdrop-blur-sm"
      />
      <div className="relative z-10 mx-auto flex max-w-content items-center justify-between gap-4 px-6 py-5 sm:px-8">
        <div className="flex items-center gap-6">
          <MarketingBrandLink />
          <nav className="hidden items-center gap-5 sm:flex">
            {NAV_LINKS.map((link) => (
              <Link
                key={link.href}
                href={link.href}
                className="text-sm font-medium text-ink-secondary underline-offset-4 transition-colors hover:text-accent hover:underline"
              >
                {link.label}
              </Link>
            ))}
          </nav>
        </div>
        {clerkReady ? (
          <div className="flex items-center gap-4 text-sm">
            <Link
              href="/pricing"
              className="font-medium text-ink-secondary underline-offset-4 transition-colors hover:text-accent hover:underline sm:hidden"
            >
              Pricing
            </Link>
            {isSignedIn ? (
              <Link
                href={POST_AUTH_PATH}
                className="rounded-md bg-accent px-4 py-2 font-medium text-accent-foreground transition-colors hover:bg-accent-hover"
              >
                Go to app
              </Link>
            ) : (
              <>
                <SignInNavLink className="font-medium text-ink-secondary underline-offset-4 transition-colors hover:text-accent hover:underline" />
                <Link
                  href="/sign-up"
                  className="rounded-md bg-accent px-4 py-2 font-medium text-accent-foreground transition-colors hover:bg-accent-hover"
                >
                  Create account
                </Link>
              </>
            )}
          </div>
        ) : null}
      </div>
    </header>
  );
}
