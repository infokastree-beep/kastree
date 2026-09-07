"use client";

import { useMutation } from "@tanstack/react-query";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { SignInNavLink } from "@/components/auth/SignInNavLink";
import { clerkReady } from "@/lib/clerk";
import { ProductSwitcher } from "@/components/layout/ProductSwitcher";
import { useAuth } from "@/hooks/useAuth";
import { apiFetch } from "@/lib/api";
import { APP_NAME, DISCLAIMER_TEXT, POST_AUTH_PATH } from "@/lib/constants";

const CAPABILITIES = [
  "Variance",
  "Commentary",
  "Risk",
  "Business Health",
  "Performance Overview",
  "Ask Copilot",
  "Export",
  "SOPL / SOFP / SOCIE",
] as const;

const TIER_FEATURES = [
  "Upload & confirm mappings",
  "SOPL, SOFP, SOCIE",
  "Variance, Risk, Commentary",
  "Business Health & Performance Overview",
  "Ask Copilot",
  "Export packs (Excel / PDF / CSV)",
] as const;

const TIERS = [
  {
    id: "starter",
    apiTier: "starter" as const,
    name: "Starter",
    eyebrow: "For getting started",
    price: "€69",
    clients: 10,
    blurb:
      "Map, statements, variance, risk, Ask, and export — for a focused client list.",
    emphasized: false,
  },
  {
    id: "growth",
    apiTier: "pro" as const,
    name: "Growth",
    eyebrow: "Most practices",
    price: "€175",
    clients: 30,
    blurb:
      "Same complete product for a growing book of work.",
    emphasized: true,
  },
  {
    id: "practice",
    apiTier: "scale" as const,
    name: "Practice",
    eyebrow: "Larger books",
    price: "€349",
    clients: 75,
    blurb:
      "Same complete product when you’re carrying a full practice load.",
    emphasized: false,
  },
] as const;

const FAQ = [
  {
    q: "What’s a “client”?",
    a: "A client group in Kastree — your practice’s client record. Companies and trial balances under that client sit inside the same engagement. Plan limits are on clients, not on companies or individual uploads.",
  },
  {
    q: "Do higher tiers unlock more features?",
    a: "No. All paid tiers include the full toolkit. You choose a tier for client capacity only.",
  },
  {
    q: "Is there a free trial?",
    a: "Yes — create an account with no card required. New organisations start on Free with up to 3 clients and the full toolkit. Upgrade here when you need more capacity.",
  },
  {
    q: "What if I outgrow my plan?",
    a: "Upgrade when you approach the client limit. Need more than 75 clients — talk to us about Custom.",
  },
  {
    q: "Annual billing?",
    a: "Monthly prices are shown. For annual options, contact us.",
  },
] as const;

function MarketingNav() {
  const { isSignedIn } = useAuth();

  return (
    <header className="border-b border-line/80 bg-surface-elevated/90 backdrop-blur-sm">
      <div className="mx-auto flex max-w-content items-center justify-between gap-4 px-6 py-5 sm:px-8">
        <div className="flex items-center gap-6">
          <ProductSwitcher />
          <Link
            href="/pricing"
            className="hidden text-sm font-medium text-ink-secondary underline-offset-4 transition-colors hover:text-accent hover:underline sm:inline"
          >
            Pricing
          </Link>
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

function MarketingFooter() {
  return (
    <footer className="border-t border-line bg-[var(--ink)] text-[var(--accent-muted)]">
      <div className="mx-auto max-w-content px-6 py-10 text-xs leading-relaxed sm:px-8">
        <p className="opacity-80">{DISCLAIMER_TEXT}</p>
        <p className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-2 font-medium text-white/90">
          <span>
            © {new Date().getFullYear()} {APP_NAME}
          </span>
          <Link
            href="/privacy"
            className="text-white/70 underline-offset-4 hover:text-white hover:underline"
          >
            Privacy
          </Link>
          <Link
            href="/terms"
            className="text-white/70 underline-offset-4 hover:text-white hover:underline"
          >
            Terms
          </Link>
          <Link
            href="/pricing"
            className="text-white/70 underline-offset-4 hover:text-white hover:underline"
          >
            Pricing
          </Link>
        </p>
      </div>
    </footer>
  );
}

export function PricingPage() {
  const { isSignedIn, getToken } = useAuth();
  const searchParams = useSearchParams();
  const checkoutState = searchParams.get("checkout");

  const checkoutMutation = useMutation({
    mutationFn: async (tier: "starter" | "pro" | "scale") => {
      return apiFetch<{ checkout_url: string; session_id: string; tier: string }>(
        "/billing/checkout",
        {
          method: "POST",
          getToken,
          body: JSON.stringify({ tier }),
        },
      );
    },
    onSuccess: (data) => {
      window.location.assign(data.checkout_url);
    },
  });

  return (
    <div className="min-h-screen bg-surface text-ink">
      <MarketingNav />

      <main>
        <section className="relative overflow-hidden border-b border-line bg-surface-elevated">
          <div
            aria-hidden
            className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_top_right,_var(--accent-muted)_0%,_transparent_55%),linear-gradient(180deg,_#ffffff_0%,_var(--surface)_100%)]"
          />
          <div className="relative mx-auto max-w-content px-6 pb-16 pt-16 sm:px-8 sm:pb-20 sm:pt-24">
            <p className="landing-fade-up font-display text-3xl font-medium tracking-tight text-accent sm:text-4xl">
              {APP_NAME}
            </p>
            <h1 className="landing-fade-up-delay font-display mt-6 max-w-3xl text-display-lg text-ink sm:text-display-xl">
              Pricing that scales with your client list
            </h1>
            <p className="landing-fade-up-delay mt-6 max-w-2xl text-lg leading-relaxed text-ink-secondary sm:text-xl">
              One complete Financial Intelligence Platform. Starter, Growth, and
              Practice differ only by how many clients you can manage — every
              plan includes Variance, Commentary, Risk, Business Health,
              Performance Overview, Ask Copilot, and Export.
            </p>
            {checkoutState === "success" ? (
              <p className="mt-6 rounded-md border border-accent/30 bg-accent-muted px-4 py-3 text-sm text-ink">
                Payment received — your plan updates when Stripe confirms the
                subscription (usually within a few seconds). Refresh if limits
                have not changed yet.
              </p>
            ) : null}
            {checkoutState === "cancelled" ? (
              <p className="mt-6 rounded-md border border-line bg-surface px-4 py-3 text-sm text-ink-secondary">
                Checkout cancelled — no charge was made. You can upgrade any
                time.
              </p>
            ) : null}
            {checkoutMutation.error ? (
              <p className="mt-6 rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
                {checkoutMutation.error instanceof Error
                  ? checkoutMutation.error.message
                  : "Could not start checkout"}
              </p>
            ) : null}
          </div>
        </section>

        <section className="border-b border-line">
          <div className="mx-auto max-w-content px-6 py-section-sm sm:px-8 sm:py-section">
            <h2 className="font-display text-heading-lg text-ink sm:text-[2rem]">
              Every plan includes the full Kastree toolkit
            </h2>
            <p className="mt-4 max-w-2xl text-ink-secondary">
              No feature gates between tiers — you pick a plan for how many
              clients you manage, not which screens you unlock.
            </p>
            <ul className="mt-8 flex flex-wrap gap-x-3 gap-y-2 text-sm text-ink">
              {CAPABILITIES.map((item) => (
                <li
                  key={item}
                  className="rounded-md border border-line bg-surface-elevated px-3 py-1.5 font-medium"
                >
                  {item}
                </li>
              ))}
            </ul>
          </div>
        </section>

        <section className="border-b border-line bg-surface-elevated">
          <div className="mx-auto max-w-content px-6 py-section-sm sm:px-8 sm:py-section">
            <div className="grid gap-6 lg:grid-cols-3">
              {TIERS.map((tier) => (
                <article
                  key={tier.id}
                  className={
                    tier.emphasized
                      ? "relative flex flex-col rounded-md border-2 border-accent bg-surface-elevated p-6 shadow-[0_16px_40px_-28px_rgba(20,32,28,0.35)]"
                      : "relative flex flex-col rounded-md border border-line bg-surface-elevated p-6"
                  }
                  data-testid={`pricing-tier-${tier.id}`}
                >
                  {tier.emphasized ? (
                    <p className="absolute -top-3 left-6 rounded-md bg-accent px-2.5 py-0.5 text-xs font-semibold uppercase tracking-[0.08em] text-accent-foreground">
                      Most practices
                    </p>
                  ) : null}
                  <p className="text-xs font-semibold uppercase tracking-[0.14em] text-soft">
                    {tier.eyebrow}
                  </p>
                  <h3 className="mt-2 font-display text-heading-md text-ink">
                    {tier.name}
                  </h3>
                  <p className="mt-4 flex items-baseline gap-1">
                    <span className="font-display text-4xl font-medium tracking-tight text-ink">
                      {tier.price}
                    </span>
                    <span className="text-sm text-ink-secondary">/ month</span>
                  </p>
                  <p className="mt-2 text-sm font-semibold text-accent">
                    Up to {tier.clients} clients
                  </p>
                  <p className="mt-4 text-sm leading-relaxed text-ink-secondary">
                    {tier.blurb}
                  </p>
                  <ul className="mt-6 flex-1 space-y-2 text-sm text-ink-secondary">
                    {TIER_FEATURES.map((feature) => (
                      <li key={feature} className="flex gap-2">
                        <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-accent" />
                        <span>{feature}</span>
                      </li>
                    ))}
                  </ul>
                  <p className="mt-4 text-sm font-medium text-ink">
                    Client capacity: {tier.clients}
                  </p>
                  {isSignedIn ? (
                    <button
                      type="button"
                      data-testid={`pricing-upgrade-${tier.id}`}
                      disabled={checkoutMutation.isPending}
                      onClick={() => checkoutMutation.mutate(tier.apiTier)}
                      className={
                        tier.emphasized
                          ? "mt-6 inline-flex items-center justify-center rounded-md bg-accent px-4 py-2.5 text-sm font-semibold text-accent-foreground transition-colors hover:bg-accent-hover disabled:opacity-50"
                          : "mt-6 inline-flex items-center justify-center rounded-md border border-line bg-surface px-4 py-2.5 text-sm font-semibold text-ink transition-colors hover:border-accent hover:text-accent disabled:opacity-50"
                      }
                    >
                      {checkoutMutation.isPending
                        ? "Starting checkout…"
                        : `Upgrade to ${tier.name}`}
                    </button>
                  ) : (
                    <Link
                      href="/sign-up"
                      className={
                        tier.emphasized
                          ? "mt-6 inline-flex items-center justify-center rounded-md bg-accent px-4 py-2.5 text-sm font-semibold text-accent-foreground transition-colors hover:bg-accent-hover"
                          : "mt-6 inline-flex items-center justify-center rounded-md border border-line bg-surface px-4 py-2.5 text-sm font-semibold text-ink transition-colors hover:border-accent hover:text-accent"
                      }
                    >
                      Start free trial
                    </Link>
                  )}
                  <p className="mt-3 text-xs leading-relaxed text-soft">
                    Free plan: up to 3 clients, no card required. Paid plans
                    start when you upgrade. Client limits apply to active
                    clients in your organisation.
                  </p>
                </article>              ))}
            </div>

            <div
              className="mt-10 flex flex-col gap-4 rounded-md border border-line bg-surface px-6 py-6 sm:flex-row sm:items-center sm:justify-between sm:px-8"
              data-testid="pricing-custom-band"
            >
              <div className="max-w-2xl">
                <h3 className="font-display text-heading-md text-ink">
                  Custom — talk to us
                </h3>
                <p className="mt-2 text-sm leading-relaxed text-ink-secondary">
                  Need more than 75 clients, multi-office rollout, or a tailored
                  onboarding plan? We’ll scope capacity and commercial terms with
                  you. Still the same Kastree product — higher client capacity
                  and support, not a different feature set.
                </p>
              </div>
              <a
                href="mailto:infokastree@gmail.com?subject=Kastree%20Custom%20plan"
                className="inline-flex shrink-0 items-center justify-center rounded-md border border-accent px-4 py-2.5 text-sm font-semibold text-accent transition-colors hover:bg-accent hover:text-accent-foreground"
              >
                Contact sales
              </a>
            </div>
          </div>
        </section>

        <section className="border-b border-line">
          <div className="mx-auto max-w-content px-6 py-section-sm sm:px-8 sm:py-section">
            <h2 className="font-display text-heading-lg text-ink sm:text-[2rem]">
              Pricing FAQ
            </h2>
            <dl className="mt-10 max-w-2xl space-y-8">
              {FAQ.map((item) => (
                <div key={item.q} className="border-t border-line pt-5">
                  <dt className="font-display text-heading-md text-ink">
                    {item.q}
                  </dt>
                  <dd className="mt-2 leading-relaxed text-ink-secondary">
                    {item.a}
                  </dd>
                </div>
              ))}
            </dl>
            <p className="mt-10 max-w-2xl text-sm text-soft">
              Prepared for internal management-accounts review — not statutory
              filing. See{" "}
              <Link
                href="/terms"
                className="text-ink underline-offset-4 hover:underline"
              >
                Terms
              </Link>
              .
            </p>
          </div>
        </section>
      </main>

      <MarketingFooter />
    </div>
  );
}
