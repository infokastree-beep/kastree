import type { Metadata } from "next";
import Link from "next/link";
import { MarketingFooter } from "@/components/landing/MarketingFooter";
import { MarketingNav } from "@/components/landing/MarketingNav";
import { APP_NAME } from "@/lib/constants";

export const metadata: Metadata = {
  title: `About — ${APP_NAME}`,
  description:
    "Why Kastree exists — deterministic statements for internal management review, with AI that narrates but never invents numbers.",
};

export default function AboutPage() {
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
            <p className="font-display text-3xl font-medium tracking-tight text-accent sm:text-4xl">
              {APP_NAME}
            </p>
            <h1 className="font-display mt-6 max-w-3xl text-display-lg text-ink sm:text-display-xl">
              Why Kastree
            </h1>
            <p className="mt-6 max-w-2xl text-lg leading-relaxed text-ink-secondary sm:text-xl">
              Built for accounting practices that want reviewable management
              accounts from a trial balance — without a spreadsheet rebuild every
              month.
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
                Most month-end work isn&apos;t the thinking — it&apos;s the
                repetition: reformatting the same trial balance export, manually
                grouping accounts into P&amp;L and balance sheet lines, checking
                the balance sheet still ties, and starting variance notes from
                scratch when a client asks why a line moved.
              </p>
              <p>
                That work is fine once. It doesn&apos;t scale when you&apos;re
                carrying ten similar clients with comparable charts.
              </p>
            </div>
          </div>
        </section>

        <section className="border-b border-line bg-surface-elevated">
          <div className="mx-auto max-w-content px-6 py-section-sm sm:px-8 sm:py-section">
            <h2 className="font-display text-heading-lg text-ink sm:text-[2.25rem]">
              What we built
            </h2>
            <div className="mt-8 max-w-2xl space-y-6 text-lg leading-relaxed text-ink-secondary">
              <p>
                Kastree takes a trial balance you already have, suggests account
                mappings you confirm, and generates SOPL, SOFP, and SOCIE with
                performance, variance, risk, and export — in one place.
              </p>
              <p>
                Every figure is computed in a deterministic engine. The model
                only drafts narrative. You stay in control of mappings and what
                leaves the building.
              </p>
            </div>
          </div>
        </section>

        <section className="border-b border-line">
          <div className="mx-auto max-w-content px-6 py-section-sm sm:px-8 sm:py-section">
            <h2 className="font-display text-heading-lg text-ink sm:text-[2.25rem]">
              Philosophy
            </h2>
            <ul className="mt-8 max-w-2xl space-y-6 text-lg leading-relaxed text-ink-secondary">
              <li>
                <strong className="font-semibold text-ink">
                  Numbers come from the engine, never from the model.
                </strong>{" "}
                Python does the math. The LLM does the narrative — never the
                reverse.
              </li>
              <li>
                <strong className="font-semibold text-ink">
                  AI drafts commentary; it doesn&apos;t invent balances.
                </strong>{" "}
                Prompts carry directions and percentages, not raw monetary
                amounts. If the model fails, statements still generate.
              </li>
              <li>
                <strong className="font-semibold text-ink">
                  Internal management review only.
                </strong>{" "}
                Not statutory accounts, not an audit product, not for regulatory
                filing.
              </li>
            </ul>
          </div>
        </section>

        <section className="border-b border-line bg-surface-elevated">
          <div className="mx-auto max-w-content px-6 py-section-sm sm:px-8 sm:py-section">
            <h3 className="text-xs font-semibold uppercase tracking-[0.16em] text-soft">
              What it is not
            </h3>
            <ul className="mt-5 max-w-2xl list-disc space-y-2 pl-5 text-ink-secondary">
              <li>Not statutory accounts or a filing tool</li>
              <li>
                Not “push button, send to client” — every mapping is confirmed by
                a person
              </li>
              <li>
                Not a general ledger — you still work from the client&apos;s TB
                export
              </li>
              <li>
                Not a crystal ball — Ask refuses questions outside this
                period&apos;s evidence
              </li>
            </ul>
            <div className="mt-12 flex flex-wrap items-center gap-4">
              <Link
                href="/sign-up"
                className="inline-flex rounded-md bg-accent px-6 py-3 text-sm font-semibold text-accent-foreground transition-colors hover:bg-accent-hover"
              >
                Create account
              </Link>
              <Link
                href="/pricing"
                className="inline-flex rounded-md border border-line bg-surface px-6 py-3 text-sm font-semibold text-ink transition-colors hover:border-accent hover:text-accent"
              >
                See pricing
              </Link>
            </div>
          </div>
        </section>
      </main>
      <MarketingFooter />
    </div>
  );
}
