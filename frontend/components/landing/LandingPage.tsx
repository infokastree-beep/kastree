"use client";

import Link from "next/link";
import { SignInNavLink } from "@/components/auth/SignInNavLink";
import { clerkReady } from "@/lib/clerk";
import { WaitlistForm } from "@/components/landing/WaitlistForm";
import { ProductSwitcher } from "@/components/layout/ProductSwitcher";
import { useAuth } from "@/hooks/useAuth";
import { APP_NAME, DISCLAIMER_TEXT, POST_AUTH_PATH } from "@/lib/constants";

const LIVE_STEPS = [
  {
    title: "Upload",
    body: "Drop a trial balance (Excel or CSV) for a client company and period.",
  },
  {
    title: "Map",
    body: "Kastree suggests account → line mappings. You review, override anything odd, and confirm — nothing generates until you sign off.",
  },
  {
    title: "Validate",
    body: "Basic integrity checks run (TB balances, balance sheet ties, etc.) before statements build.",
  },
  {
    title: "Statements",
    body: "SOPL, SOFP, and SOCIE generate in minutes. View them in the app, tab by tab.",
  },
  {
    title: "Export",
    body: "Download Excel, PDF, or CSV packs with the statements — currency formatting and tier-aware watermarking included.",
  },
  {
    title: "Clients",
    body: "Organise work by client group and company (GBP / EUR / USD functional currency per company).",
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
    q: "Is variance commentary live?",
    a: "The engine exists on the backend; we're putting the review UI in front of pilot users now. Join the waitlist if that's the part you care about most.",
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
                <SignInNavLink className="font-medium text-ink-secondary underline-offset-4 transition-colors hover:text-accent hover:underline" />
              )}
            </div>
          ) : null}
        </div>
      </header>

      <main>
        {/* Hero — brand, headline, support, CTA, then dominant product image */}
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
              Trial balance in. SOPL, SOFP, and SOCIE out — without rebuilding the
              same spreadsheet every month.
            </h1>
            <p className="landing-fade-up-delay mt-6 max-w-2xl text-lg leading-relaxed text-ink-secondary sm:text-xl">
              Upload <code className="rounded bg-accent-muted/70 px-1.5 py-0.5 text-base text-accent">.xlsx</code>{" "}
              or{" "}
              <code className="rounded bg-accent-muted/70 px-1.5 py-0.5 text-base text-accent">.csv</code>
              , confirm how accounts map to standard lines, and review the three
              statements in the browser.
            </p>
            <p className="landing-fade-up-delay mt-4 text-sm text-soft">
              Early access — we&apos;re onboarding a small number of practices for
              live feedback.
            </p>
            <div className="landing-fade-up-delay mt-10 flex flex-wrap items-center gap-4">
              <a
                href="#waitlist"
                className="inline-flex rounded-md bg-accent px-6 py-3 text-sm font-semibold text-accent-foreground transition-colors hover:bg-accent-hover"
              >
                Join the waitlist
              </a>
              <a
                href="#what-you-get"
                className="text-sm font-medium text-ink-secondary underline-offset-4 transition-colors hover:text-accent hover:underline"
              >
                See what&apos;s live
              </a>
            </div>
          </div>

          <div className="landing-fade-in relative mx-auto max-w-content px-6 pb-16 sm:px-8 sm:pb-24">
            <img
              src="/images/statements-dashboard.png"
              alt="Kastree statements dashboard showing SOPL, SOFP, and SOCIE tabs with a Statement of Financial Position in EUR"
              className="w-full border border-line bg-surface-elevated shadow-[0_24px_60px_-28px_rgba(20,32,28,0.35)]"
              width={1280}
              height={900}
            />
            <p className="mt-4 text-sm text-soft">
              The statements dashboard — switch between SOPL, SOFP, and SOCIE, then
              export Excel, PDF, or CSV when you&apos;re ready.
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

            <h3 className="mt-14 text-xs font-semibold uppercase tracking-[0.16em] text-accent">
              Live now
            </h3>
            <ul className="mt-8 grid gap-x-12 gap-y-10 sm:grid-cols-2">
              {LIVE_STEPS.map((step) => (
                <li key={step.title} className="border-t border-line pt-5">
                  <p className="font-display text-heading-md text-ink">{step.title}</p>
                  <p className="mt-2 text-[0.95rem] leading-relaxed text-ink-secondary">
                    {step.body}
                  </p>
                </li>
              ))}
            </ul>

            <div className="mt-16 border-l-4 border-amber-500 bg-amber-50/80 px-6 py-5 text-sm text-amber-950">
              <p className="font-semibold tracking-tight">
                In pilot / rolling out to early users
              </p>
              <ul className="mt-3 list-disc space-y-2 pl-5 text-amber-950/85">
                <li>
                  Period-on-period variance when a prior trial balance exists for the
                  same company
                </li>
                <li>
                  AI-drafted commentary on material movements — suggested wording only;
                  you review and edit before anything goes to a client
                </li>
              </ul>
              <p className="mt-4 text-amber-900/75">
                Upload, map, statements, and export are live. Variance commentary UI is
                what pilot users are helping us finish.
              </p>
            </div>

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
                  body: "SOPL, SOFP, SOCIE in the dashboard. Typical first run: mapping review is where you spend time; regenerate is one click once mappings are right.",
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

        <section id="waitlist" className="border-b border-line">
          <div className="mx-auto max-w-content px-6 py-section-sm sm:px-8 sm:py-section">
            <h2 className="font-display text-heading-lg text-ink sm:text-[2.25rem]">
              Get early access
            </h2>
            <p className="mt-5 max-w-2xl text-lg leading-relaxed text-ink-secondary">
              We&apos;re opening Kastree to a handful of practices for structured
              feedback — not a public launch. Tell us who you are and we&apos;ll reach
              out when there&apos;s a slot.
            </p>
            <div className="mt-12 max-w-xl">
              <WaitlistForm />
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
          <p className="mt-4 font-medium text-white/90">
            © {new Date().getFullYear()} {APP_NAME}
          </p>
        </div>
      </footer>
    </div>
  );
}
