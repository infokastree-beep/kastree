"use client";

import Link from "next/link";
import { SignInNavLink } from "@/components/auth/SignInNavLink";
import { clerkReady } from "@/lib/clerk";
import { ProductSwitcher } from "@/components/layout/ProductSwitcher";
import { useAuth } from "@/hooks/useAuth";
import { APP_NAME, DISCLAIMER_TEXT, POST_AUTH_PATH } from "@/lib/constants";

const WHAT_YOU_GET = [
  {
    title: "Upload & map",
    body: "Upload a trial balance, then review suggested account → line mappings and confirm before anything generates.",
  },
  {
    title: "Statements",
    body: "SOPL, SOFP, and SOCIE generate in the browser — switch tabs, review line amounts, regenerate when mappings change.",
  },
  {
    title: "Performance overview",
    body: "KPIs, trend charts, and expense mix for the period so you see the shape of the numbers before diving into line detail.",
  },
  {
    title: "Business health",
    body: "A short executive read grounded in this period’s evidence — trends and ratios, not a spreadsheet dump.",
  },
  {
    title: "Variance",
    body: "Period-on-period movements when a prior trial balance exists for the same company, ready for review.",
  },
  {
    title: "Risk flags",
    body: "Deterministic checks (for example negative cash or anomalous balances) surfaced alongside the statements.",
  },
  {
    title: "Ask",
    body: "Ask questions answered only from this period’s evidence, with citations back to performance, variance, or risk.",
  },
  {
    title: "Export",
    body: "Download Excel, PDF, or CSV packs with the statements — currency formatting and tier-aware watermarking included.",
  },
] as const;

const FAQ = [
  {
    q: "Do I need to connect to Xero or QuickBooks?",
    a: "No. Upload the trial balance export you already have.",
  },
  {
    q: "What file formats?",
    a: ".xlsx and .csv.",
  },
  {
    q: "Does AI map everything automatically?",
    a: "It suggests mappings; you confirm before statements generate. Unmapped or low-confidence lines need a human decision.",
  },
  {
    q: "Can I use this for audit or Companies House filing?",
    a: "No. Internal management review only.",
  },
  {
    q: "Can I ask about next year or forecasts?",
    a: "No. Ask only uses evidence for the selected period. Out-of-scope questions get a clear refusal, not a guess.",
  },
] as const;

export function LandingPage() {
  const { isSignedIn } = useAuth();

  return (
    <div className="min-h-screen bg-surface text-ink">
      <header className="border-b border-line/80 bg-surface-elevated/90 backdrop-blur-sm">
        <div className="mx-auto flex max-w-content items-center justify-between gap-4 px-6 py-5 sm:px-8">
          <ProductSwitcher />
          {clerkReady ? (
            <div className="flex items-center gap-4 text-sm">
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

      <main>
        <section className="relative overflow-hidden border-b border-line bg-surface-elevated">
          <div
            aria-hidden
            className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_top_right,_var(--accent-muted)_0%,_transparent_55%),linear-gradient(180deg,_#ffffff_0%,_var(--surface)_100%)]"
          />
          <div className="relative mx-auto max-w-content px-6 pb-6 pt-16 sm:px-8 sm:pb-8 sm:pt-24">
            <p className="landing-fade-up font-display text-3xl font-medium tracking-tight text-accent sm:text-4xl">
              {APP_NAME}
            </p>
            <p className="landing-fade-up mt-3 text-sm font-medium uppercase tracking-[0.14em] text-soft">
              For accounting practices &amp; fractional CFOs
            </p>
            <h1 className="landing-fade-up-delay font-display mt-6 max-w-3xl text-display-lg text-ink sm:text-display-xl">
              Trial balance in. Statements, variance, and risk out — ready for
              review.
            </h1>
            <p className="landing-fade-up-delay mt-6 max-w-2xl text-lg leading-relaxed text-ink-secondary sm:text-xl">
              Upload a trial balance, confirm account mappings, and review SOPL,
              SOFP, SOCIE, performance, variance, and risk in one place — with an
              Ask panel grounded in this period&apos;s evidence.
            </p>
            <div className="landing-fade-up-delay mt-10 flex flex-wrap items-center gap-4">
              <Link
                href="/sign-up"
                className="inline-flex rounded-md bg-accent px-6 py-3 text-sm font-semibold text-accent-foreground transition-colors hover:bg-accent-hover"
              >
                Create account
              </Link>
              <Link
                href="/sign-in"
                className="inline-flex rounded-md border border-line bg-surface-elevated px-6 py-3 text-sm font-semibold text-ink transition-colors hover:border-accent hover:text-accent"
              >
                Sign in
              </Link>
              <a
                href="#what-you-get"
                className="text-sm font-medium text-ink-secondary underline-offset-4 transition-colors hover:text-accent hover:underline"
              >
                See what it does
              </a>
            </div>
          </div>

          <div className="landing-fade-in relative mx-auto max-w-content px-6 pb-16 sm:px-8 sm:pb-24">
            <img
              src="/images/statements-dashboard.png"
              alt="Kastree statements dashboard showing performance overview, business health, statement tabs, and the Ask panel"
              className="w-full border border-line bg-surface-elevated shadow-[0_24px_60px_-28px_rgba(20,32,28,0.35)]"
              width={1280}
              height={900}
            />
            <p className="mt-4 text-sm text-soft">
              The statements dashboard — performance and business health above;
              SOPL, SOFP, SOCIE, Variance, and Risk below. Ask opens a grounded
              Q&amp;A panel for this period.
            </p>
          </div>
        </section>

        <section className="border-b border-line">
          <div className="mx-auto max-w-content px-6 py-section-sm sm:px-8 sm:py-section">
            <h2 className="font-display text-heading-lg text-ink sm:text-[2.25rem]">
              The problem
            </h2>
            <div className="mt-8 max-w-2xl space-y-6 text-lg leading-relaxed text-ink-secondary">
              <p>
                Most month-end work isn&apos;t the thinking — it&apos;s the repetition:
                reformatting the same trial balance export, manually grouping accounts
                into P&amp;L and balance sheet lines, checking the balance sheet still
                ties, and starting variance notes from scratch when a client asks why a
                line moved.
              </p>
              <p>
                That work is fine once. It doesn&apos;t scale when you&apos;re carrying
                ten similar clients with comparable charts.
              </p>
              <p>
                Kastree doesn&apos;t replace your judgement. It removes the mechanical
                steps between{" "}
                <strong className="font-semibold text-ink">trial balance</strong> and{" "}
                <strong className="font-semibold text-ink">reviewable statements</strong>,
                so you spend time on mapping edge cases and client questions — not
                copy-paste.
              </p>
            </div>
          </div>
        </section>

        <section
          id="what-you-get"
          className="border-b border-line bg-surface-elevated"
        >
          <div className="mx-auto max-w-content px-6 py-section-sm sm:px-8 sm:py-section">
            <h2 className="font-display text-heading-lg text-ink sm:text-[2.25rem]">
              What you get
            </h2>
            <ul className="mt-12 grid gap-x-12 gap-y-10 sm:grid-cols-2">
              {WHAT_YOU_GET.map((item) => (
                <li key={item.title} className="border-t border-line pt-5">
                  <p className="font-display text-heading-md text-ink">{item.title}</p>
                  <p className="mt-2 text-[0.95rem] leading-relaxed text-ink-secondary">
                    {item.body}
                  </p>
                </li>
              ))}
            </ul>

            <h3 className="mt-16 text-xs font-semibold uppercase tracking-[0.16em] text-soft">
              What it is not
            </h3>
            <ul className="mt-5 max-w-2xl list-disc space-y-2 pl-5 text-ink-secondary">
              <li>Not statutory accounts or a filing tool</li>
              <li>
                Not “push button, send to client” — every mapping is confirmed by a
                person
              </li>
              <li>Not a general ledger — you still work from the client&apos;s TB export</li>
              <li>
                Not a crystal ball — Ask refuses questions outside this period&apos;s
                evidence
              </li>
            </ul>
          </div>
        </section>

        <section className="border-b border-line">
          <div className="mx-auto max-w-content px-6 py-section-sm sm:px-8 sm:py-section">
            <h2 className="font-display text-heading-lg text-ink sm:text-[2.25rem]">
              How it works
            </h2>
            <ol className="mt-12 max-w-2xl space-y-10">
              {[
                {
                  n: "1",
                  title: "Upload the trial balance",
                  body: "Same file you'd normally drop into a template.",
                },
                {
                  n: "2",
                  title: "Confirm mappings",
                  body: "Fix anything the suggestions got wrong — unusual accounts, one-offs, reclasses.",
                },
                {
                  n: "3",
                  title: "Generate and review",
                  body: "Generate and review statements, performance, variance, and risk. Use Ask when you want a cited answer from the evidence.",
                },
              ].map((step) => (
                <li key={step.n} className="flex gap-5">
                  <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-accent text-sm font-semibold text-accent-foreground">
                    {step.n}
                  </span>
                  <div className="pt-0.5">
                    <p className="font-display text-heading-md text-ink">{step.title}</p>
                    <p className="mt-1.5 leading-relaxed text-ink-secondary">{step.body}</p>
                  </div>
                </li>
              ))}
            </ol>
          </div>
        </section>

        <section className="border-b border-line bg-surface-elevated">
          <div className="mx-auto max-w-content px-6 py-section-sm sm:px-8 sm:py-section">
            <h2 className="font-display text-heading-lg text-ink sm:text-[2.25rem]">
              Who it&apos;s for
            </h2>
            <ul className="mt-8 max-w-2xl list-disc space-y-3 pl-5 text-lg text-ink-secondary">
              <li>
                Small and mid-size accounting practices doing regular management
                accounts
              </li>
              <li>Fractional CFOs with several similar clients on comparable charts</li>
              <li>Teams tired of maintaining one master spreadsheet per client</li>
            </ul>
            <p className="mt-8 max-w-2xl leading-relaxed text-ink-secondary">
              Best fit: clients where a standard chart maps cleanly to management lines.
              Messy or highly bespoke charts of accounts still work — you&apos;ll just
              spend longer on mapping review.
            </p>
          </div>
        </section>

        <section id="get-started" className="border-b border-line">
          <div className="mx-auto max-w-content px-6 py-section-sm sm:px-8 sm:py-section">
            <h2 className="font-display text-heading-lg text-ink sm:text-[2.25rem]">
              Start with your next trial balance
            </h2>
            <p className="mt-5 max-w-2xl text-lg leading-relaxed text-ink-secondary">
              Create an account to upload a client TB, or sign in if you already have
              one.
            </p>
            <div className="mt-10 flex flex-wrap items-center gap-4">
              <Link
                href="/sign-up"
                className="inline-flex rounded-md bg-accent px-6 py-3 text-sm font-semibold text-accent-foreground transition-colors hover:bg-accent-hover"
              >
                Create account
              </Link>
              <Link
                href="/sign-in"
                className="inline-flex rounded-md border border-line bg-surface-elevated px-6 py-3 text-sm font-semibold text-ink transition-colors hover:border-accent hover:text-accent"
              >
                Sign in
              </Link>
            </div>
          </div>
        </section>

        <section className="bg-surface-elevated">
          <div className="mx-auto max-w-content px-6 py-section-sm sm:px-8 sm:py-section">
            <h2 className="font-display text-heading-lg text-ink sm:text-[2.25rem]">
              FAQ
            </h2>
            <dl className="mt-12 max-w-2xl space-y-10">
              {FAQ.map((item) => (
                <div key={item.q} className="border-t border-line pt-6">
                  <dt className="font-display text-heading-md text-ink">{item.q}</dt>
                  <dd className="mt-2 leading-relaxed text-ink-secondary">{item.a}</dd>
                </div>
              ))}
            </dl>
          </div>
        </section>
      </main>

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
          </p>
        </div>
      </footer>
    </div>
  );
}
