"use client";

import Link from "next/link";
import { MarketingFooter } from "@/components/landing/MarketingFooter";
import { MarketingNav } from "@/components/landing/MarketingNav";
import { APP_NAME } from "@/lib/constants";

const PILLARS = [
  {
    title: "Plan the period",
    body: "Upload the trial balance you already export. Kastree turns it into a reviewable pack — without another spreadsheet rebuild.",
  },
  {
    title: "Protect judgement",
    body: "AI suggests account mappings. You confirm. Statements and variance stay deterministic — numbers never come from the model.",
  },
  {
    title: "Finish the narrative",
    body: "Variance, risk flags, business health, and Ask Copilot — grounded in this period’s evidence, ready for client review.",
  },
] as const;

const WHAT_YOU_GET = [
  {
    title: "Upload",
    body: "Excel/CSV trial balance, PDF trial balance, or general ledger. Extraction and review stay in one flow.",
  },
  {
    title: "AI-assisted mapping",
    body: "Suggested account → line mappings you confirm. Remembered per client for the next period.",
  },
  {
    title: "Statements",
    body: "SOPL, SOFP, and SOCIE from confirmed mappings — amounts from the engine, not the model.",
  },
  {
    title: "Variance & commentary",
    body: "Period-on-period movements plus narrative grounded in those movements. No invented numbers.",
  },
  {
    title: "Risk & health",
    body: "Deterministic checks, KPIs, and a short executive read from this period’s evidence.",
  },
  {
    title: "Ask & export",
    body: "Questions answered only from period evidence, then Excel, PDF, or CSV packs for the client.",
  },
] as const;

const STEPS = [
  {
    n: "01",
    title: "Upload the trial balance",
    body: "Drop the same .xlsx or .csv export you’d normally paste into a template.",
  },
  {
    n: "02",
    title: "Confirm mappings",
    body: "Review suggested account → line mappings. Fix one-offs before anything generates.",
  },
  {
    n: "03",
    title: "Generate statements",
    body: "SOPL, SOFP, and SOCIE build from confirmed mappings — deterministic amounts only.",
  },
  {
    n: "04",
    title: "Review, ask, export",
    body: "Performance, variance, risk, Ask Copilot, then download the pack.",
  },
] as const;

const FAQ = [
  {
    q: "Is this just another AI wrapper?",
    a: "No. Statements and variance come from a deterministic engine on confirmed mappings — every figure traces to source trial-balance rows. AI suggests mappings and drafts commentary; it never calculates amounts, invents movements, or freelances outside this period’s evidence. Ask runs over an evidence graph, not a blank chat on your books.",
  },
  {
    q: "Do I need to connect to Xero or QuickBooks?",
    a: "No. Upload the trial balance export you already have.",
  },
  {
    q: "What file formats?",
    a: ".xlsx and .csv for trial balances. General ledgers and PDF trial balances are supported in the upload flow.",
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
  return (
    <div className="min-h-screen bg-surface text-ink">
      <MarketingNav />

      <main>
        {/* Hero — one composition: brand, claim, support, CTAs, product plane */}
        <section className="relative overflow-hidden border-b border-line">
          <div
            aria-hidden
            className="landing-hero-atmosphere pointer-events-none absolute inset-0"
          />
          <div className="relative mx-auto max-w-content px-6 pb-10 pt-16 sm:px-8 sm:pb-12 sm:pt-20 lg:pt-24">
            <p className="landing-fade-up font-display text-4xl font-medium tracking-tight text-accent sm:text-5xl">
              {APP_NAME}
            </p>
            <p className="landing-fade-up mt-4 text-xs font-semibold uppercase tracking-[0.18em] text-soft">
              Financial intelligence for accounting practices
            </p>
            <h1 className="landing-fade-up-delay font-display mt-6 max-w-4xl text-[2.35rem] font-medium leading-[1.08] tracking-tight text-ink sm:text-display-xl">
              Turn every trial balance into a review-ready pack — without rebuilding Excel.
            </h1>
            <p className="landing-fade-up-delay mt-6 max-w-2xl text-lg leading-relaxed text-ink-secondary sm:text-xl">
              Mapping suggestions you confirm. Statements, variance, and commentary
              generated for you. Spend the hour on judgement — not reformatting.
            </p>
            <div className="landing-fade-up-delay mt-10 flex flex-wrap items-center gap-3 sm:gap-4">
              <Link
                href="/sign-up"
                className="inline-flex rounded-full bg-accent px-7 py-3.5 text-sm font-semibold text-accent-foreground shadow-[0_12px_32px_-16px_rgba(15,92,76,0.65)] transition-colors hover:bg-accent-hover"
              >
                Start free
              </Link>
              <a
                href="#how-it-works"
                className="inline-flex rounded-full border border-line bg-surface-elevated/80 px-7 py-3.5 text-sm font-semibold text-ink backdrop-blur-sm transition-colors hover:border-accent hover:text-accent"
              >
                See how it works
              </a>
              <Link
                href="/pricing"
                className="px-2 text-sm font-medium text-ink-secondary underline-offset-4 transition-colors hover:text-accent hover:underline"
              >
                Pricing
              </Link>
            </div>
          </div>

          <div className="landing-fade-in relative mx-auto max-w-content px-4 pb-16 sm:px-8 sm:pb-24">
            <div className="landing-product-frame overflow-hidden rounded-2xl border border-line/80 bg-surface-elevated shadow-[0_40px_100px_-40px_rgba(20,32,28,0.45)]">
              <img
                src="/images/statements-dashboard.png"
                alt="Kastree statements dashboard showing performance overview, business health, statement tabs, and the Ask panel"
                className="w-full"
                width={1280}
                height={900}
              />
            </div>
            <p className="mt-5 px-2 text-center text-sm text-soft sm:px-0">
              After upload: confirm mappings, then SOPL, SOFP, SOCIE, variance, and
              commentary on one dashboard.
            </p>
          </div>
        </section>

        {/* System pillars — Superfocus-style “method” strip */}
        <section className="border-b border-line bg-surface-elevated">
          <div className="mx-auto max-w-content px-6 py-section-sm sm:px-8 sm:py-section">
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-accent">
              A system, not another spreadsheet
            </p>
            <h2 className="font-display mt-4 max-w-3xl text-heading-lg text-ink sm:text-[2.5rem] sm:leading-tight">
              From trial balance to client-ready review — in one calm loop.
            </h2>
            <div className="mt-14 grid gap-10 md:grid-cols-3 md:gap-8">
              {PILLARS.map((pillar, index) => (
                <div key={pillar.title} className="relative border-t border-line pt-6">
                  <span className="font-display text-sm font-medium text-accent">
                    {String(index + 1).padStart(2, "0")}
                  </span>
                  <h3 className="font-display mt-3 text-heading-md text-ink">
                    {pillar.title}
                  </h3>
                  <p className="mt-3 text-[0.95rem] leading-relaxed text-ink-secondary">
                    {pillar.body}
                  </p>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* Problem */}
        <section className="relative overflow-hidden border-b border-line">
          <div
            aria-hidden
            className="pointer-events-none absolute -right-24 top-10 h-72 w-72 rounded-full bg-accent-muted/60 blur-3xl"
          />
          <div className="relative mx-auto max-w-content px-6 py-section-sm sm:px-8 sm:py-section">
            <h2 className="font-display max-w-2xl text-heading-lg text-ink sm:text-[2.35rem] sm:leading-tight">
              Month-end shouldn’t mean rebuilding the same pack in Excel.
            </h2>
            <div className="mt-8 max-w-2xl space-y-5 text-lg leading-relaxed text-ink-secondary">
              <p>
                Most of the time isn’t the thinking — it’s the repetition:
                reformatting the export, grouping accounts into P&amp;L and balance
                sheet lines, checking the balance sheet still ties, and starting
                variance notes from scratch.
              </p>
              <p>
                That work is fine once. It doesn’t scale when you’re carrying ten
                similar clients with comparable charts.
              </p>
              <p>
                {APP_NAME} doesn’t replace your judgement. It removes the mechanical
                steps between{" "}
                <strong className="font-semibold text-ink">trial balance</strong> and{" "}
                <strong className="font-semibold text-ink">
                  reviewable statements
                </strong>
                .
              </p>
            </div>
          </div>
        </section>

        {/* What you get */}
        <section
          id="what-you-get"
          className="border-b border-line bg-surface-elevated"
        >
          <div className="mx-auto max-w-content px-6 py-section-sm sm:px-8 sm:py-section">
            <div className="max-w-2xl">
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-accent">
                What’s included
              </p>
              <h2 className="font-display mt-4 text-heading-lg text-ink sm:text-[2.35rem] sm:leading-tight">
                One platform from intake through export.
              </h2>
              <p className="mt-4 text-[0.95rem] leading-relaxed text-ink-secondary sm:text-base">
                Everything below ships in a Kastree subscription — no bolt-on
                converters, no separate commentary tool.
              </p>
            </div>
            <ul className="mt-14 grid gap-x-12 gap-y-10 sm:grid-cols-2 lg:grid-cols-3">
              {WHAT_YOU_GET.map((item) => (
                <li key={item.title} className="border-t border-line pt-5">
                  <p className="font-display text-heading-md text-ink">{item.title}</p>
                  <p className="mt-2 text-[0.95rem] leading-relaxed text-ink-secondary">
                    {item.body}
                  </p>
                </li>
              ))}
            </ul>

            <div className="mt-16 rounded-2xl border border-line bg-surface px-6 py-7 sm:px-8">
              <h3 className="text-xs font-semibold uppercase tracking-[0.16em] text-soft">
                What it is not
              </h3>
              <ul className="mt-4 grid gap-2 text-ink-secondary sm:grid-cols-2">
                <li className="flex gap-2">
                  <span className="text-accent">—</span>
                  Not statutory accounts or a filing tool
                </li>
                <li className="flex gap-2">
                  <span className="text-accent">—</span>
                  Not “push button, send to client” — mappings stay human-confirmed
                </li>
                <li className="flex gap-2">
                  <span className="text-accent">—</span>
                  Not a general ledger — you still start from the client’s TB export
                </li>
                <li className="flex gap-2">
                  <span className="text-accent">—</span>
                  Not a crystal ball — Ask refuses questions outside this period
                </li>
              </ul>
            </div>
          </div>
        </section>

        {/* How it works */}
        <section id="how-it-works" className="border-b border-line">
          <div className="mx-auto max-w-content px-6 py-section-sm sm:px-8 sm:py-section">
            <div className="max-w-2xl">
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-accent">
                How it works
              </p>
              <h2 className="font-display mt-4 text-heading-lg text-ink sm:text-[2.35rem] sm:leading-tight">
                Four steps. Confirm once. Review with confidence.
              </h2>
            </div>
            <ol className="mt-14 grid gap-8 lg:grid-cols-2">
              {STEPS.map((step) => (
                <li
                  key={step.n}
                  className="flex gap-5 rounded-2xl border border-line bg-surface-elevated p-6 sm:p-7"
                >
                  <span className="font-display text-2xl font-medium text-accent">
                    {step.n}
                  </span>
                  <div>
                    <p className="font-display text-heading-md text-ink">{step.title}</p>
                    <p className="mt-2 leading-relaxed text-ink-secondary">{step.body}</p>
                  </div>
                </li>
              ))}
            </ol>
            <div className="mt-14">
              <div className="overflow-hidden rounded-2xl border border-line bg-surface-elevated shadow-[0_28px_70px_-36px_rgba(20,32,28,0.4)]">
                <img
                  src="/images/statements-dashboard.png"
                  alt="Kastree statements dashboard after generate — performance, business health, statement tabs, and Ask"
                  className="w-full"
                  width={1280}
                  height={900}
                />
              </div>
              <p className="mt-4 text-sm text-soft">
                After generate: performance and business health above; SOPL, SOFP,
                SOCIE, Variance, and Risk below. Ask opens grounded Q&amp;A for this
                period.
              </p>
            </div>
          </div>
        </section>

        {/* Principle / proof band */}
        <section className="relative overflow-hidden border-b border-line bg-[var(--ink)] text-white">
          <div
            aria-hidden
            className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_top_left,_rgba(228,240,236,0.14)_0%,_transparent_55%)]"
          />
          <div className="relative mx-auto max-w-content px-6 py-section-sm sm:px-8 sm:py-section">
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-white/55">
              Built on a hard rule
            </p>
            <blockquote className="font-display mt-6 max-w-3xl text-[1.65rem] font-medium leading-snug tracking-tight sm:text-[2.15rem] sm:leading-[1.2]">
              “Python does the math. The model does the narrative. Never the reverse.”
            </blockquote>
            <p className="mt-8 max-w-2xl text-base leading-relaxed text-white/70">
              Every statement figure traces to source TB rows. AI never invents
              amounts, never invents variance, and never answers outside this
              period’s evidence. That’s how practices can trust the pack.
            </p>
          </div>
        </section>

        {/* Who */}
        <section className="border-b border-line bg-surface-elevated">
          <div className="mx-auto max-w-content px-6 py-section-sm sm:px-8 sm:py-section">
            <h2 className="font-display text-heading-lg text-ink sm:text-[2.35rem] sm:leading-tight">
              Built for people who live in month-end.
            </h2>
            <ul className="mt-10 grid gap-6 sm:grid-cols-3">
              {[
                "Small and mid-size accounting practices doing regular management accounts",
                "Fractional CFOs with several similar clients on comparable charts",
                "Teams tired of maintaining one master spreadsheet per client",
              ].map((item) => (
                <li
                  key={item}
                  className="rounded-2xl border border-line bg-surface px-5 py-6 text-[0.95rem] leading-relaxed text-ink-secondary"
                >
                  {item}
                </li>
              ))}
            </ul>
            <p className="mt-8 max-w-2xl leading-relaxed text-ink-secondary">
              Best fit: clients where a standard chart maps cleanly to management
              lines. Messy or highly bespoke charts still work — you’ll just spend
              longer on mapping review.
            </p>
          </div>
        </section>

        {/* Final CTA */}
        <section id="get-started" className="relative overflow-hidden border-b border-line">
          <div
            aria-hidden
            className="landing-cta-atmosphere pointer-events-none absolute inset-0"
          />
          <div className="relative mx-auto max-w-content px-6 py-section-sm sm:px-8 sm:py-section">
            <h2 className="font-display max-w-3xl text-heading-lg text-ink sm:text-[2.75rem] sm:leading-tight">
              Start with your next trial balance.
            </h2>
            <p className="mt-5 max-w-2xl text-lg leading-relaxed text-ink-secondary">
              Create an account, upload a client TB, confirm mappings, and review
              the pack — usually in the time you’d spend fighting a template.
            </p>
            <div className="mt-10 flex flex-wrap items-center gap-3 sm:gap-4">
              <Link
                href="/sign-up"
                className="inline-flex rounded-full bg-accent px-7 py-3.5 text-sm font-semibold text-accent-foreground shadow-[0_12px_32px_-16px_rgba(15,92,76,0.65)] transition-colors hover:bg-accent-hover"
              >
                Create account
              </Link>
              <Link
                href="/sign-in"
                className="inline-flex rounded-full border border-line bg-surface-elevated/90 px-7 py-3.5 text-sm font-semibold text-ink transition-colors hover:border-accent hover:text-accent"
              >
                Sign in
              </Link>
              <Link
                href="/pricing"
                className="px-2 text-sm font-medium text-ink-secondary underline-offset-4 hover:text-accent hover:underline"
              >
                Compare plans
              </Link>
            </div>
          </div>
        </section>

        {/* FAQ */}
        <section className="bg-surface-elevated">
          <div className="mx-auto max-w-content px-6 py-section-sm sm:px-8 sm:py-section">
            <h2 className="font-display text-heading-lg text-ink sm:text-[2.35rem]">
              Questions, answered plainly
            </h2>
            <dl className="mt-12 max-w-3xl divide-y divide-line border-t border-line">
              {FAQ.map((item) => (
                <div key={item.q} className="py-7">
                  <dt className="font-display text-heading-md text-ink">{item.q}</dt>
                  <dd className="mt-2 max-w-2xl leading-relaxed text-ink-secondary">
                    {item.a}
                  </dd>
                </div>
              ))}
            </dl>
          </div>
        </section>
      </main>

      <MarketingFooter />
    </div>
  );
}
