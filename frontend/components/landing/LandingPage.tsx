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
    <div className="min-h-screen bg-stone-50 text-stone-900">
      <header className="border-b border-stone-200 bg-white">
        <div className="mx-auto flex max-w-5xl items-center justify-between gap-4 px-6 py-4">
          <ProductSwitcher />
          {clerkReady ? (
            <div className="flex items-center gap-3 text-sm">
              {isSignedIn ? (
                <Link
                  href={POST_AUTH_PATH}
                  className="rounded bg-stone-900 px-3 py-1.5 font-medium text-white"
                >
                  Go to app
                </Link>
              ) : (
                <SignInNavLink className="font-medium text-stone-700 underline-offset-2 hover:underline" />
              )}
            </div>
          ) : null}
        </div>
      </header>

      <main>
        <section className="border-b border-stone-200 bg-white">
          <div className="mx-auto max-w-5xl px-6 py-16 sm:py-20">
            <p className="text-sm font-medium uppercase tracking-wide text-stone-500">
              For accounting practices &amp; fractional CFOs
            </p>
            <h1 className="mt-3 max-w-3xl text-4xl font-semibold tracking-tight sm:text-5xl">
              Trial balance in. SOPL, SOFP, and SOCIE out — without rebuilding the
              same spreadsheet every month.
            </h1>
            <p className="mt-5 max-w-2xl text-lg text-stone-600">
              Upload <code className="text-base">.xlsx</code> or{" "}
              <code className="text-base">.csv</code>, confirm how accounts map to
              standard lines, and review the three statements in the browser.
            </p>
            <p className="mt-4 text-sm text-stone-500">
              Early access — we&apos;re onboarding a small number of practices for
              live feedback.
            </p>
            <a
              href="#waitlist"
              className="mt-8 inline-block rounded bg-stone-900 px-5 py-2.5 text-sm font-medium text-white"
            >
              Join the waitlist
            </a>
          </div>
        </section>

        <section className="border-b border-stone-200">
          <div className="mx-auto max-w-5xl px-6 py-14">
            <h2 className="text-2xl font-semibold tracking-tight">The problem</h2>
            <div className="mt-4 max-w-3xl space-y-4 text-stone-600">
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
                steps between <strong className="font-medium text-stone-800">trial balance</strong>{" "}
                and <strong className="font-medium text-stone-800">reviewable statements</strong>,
                so you spend time on mapping edge cases and client questions — not
                copy-paste.
              </p>
            </div>
          </div>
        </section>

        <section className="border-b border-stone-200 bg-white">
          <div className="mx-auto max-w-5xl px-6 py-14">
            <h2 className="text-2xl font-semibold tracking-tight">What you get</h2>
            <h3 className="mt-8 text-sm font-semibold uppercase tracking-wide text-stone-500">
              Live now
            </h3>
            <ul className="mt-4 grid gap-4 sm:grid-cols-2">
              {LIVE_STEPS.map((step) => (
                <li
                  key={step.title}
                  className="rounded-lg border border-stone-200 bg-stone-50 p-4"
                >
                  <p className="font-medium text-stone-900">{step.title}</p>
                  <p className="mt-1 text-sm text-stone-600">{step.body}</p>
                </li>
              ))}
            </ul>
            <div className="mt-8 rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-950">
              <p className="font-medium">In pilot / rolling out to early users</p>
              <ul className="mt-2 list-disc space-y-1 pl-5 text-amber-900/90">
                <li>
                  Period-on-period variance when a prior trial balance exists for the
                  same company
                </li>
                <li>
                  AI-drafted commentary on material movements — suggested wording only;
                  you review and edit before anything goes to a client
                </li>
                <li>Export packs (Excel / PDF) including statements and variance notes</li>
              </ul>
              <p className="mt-3 text-amber-900/80">
                The core loop — upload, map, statements — is what we&apos;re validating
                with practices first. Commentary and exports are wired on the backend;
                the in-app review flow is what pilot users are helping us finish.
              </p>
            </div>
            <h3 className="mt-8 text-sm font-semibold uppercase tracking-wide text-stone-500">
              What it is not
            </h3>
            <ul className="mt-3 list-disc space-y-1 pl-5 text-stone-600">
              <li>Not statutory accounts or a filing tool</li>
              <li>Not “push button, send to client” — every mapping is confirmed by a person</li>
              <li>Not a general ledger — you still work from the client&apos;s TB export</li>
            </ul>
          </div>
        </section>

        <section className="border-b border-stone-200">
          <div className="mx-auto max-w-5xl px-6 py-14">
            <h2 className="text-2xl font-semibold tracking-tight">How it works</h2>
            <ol className="mt-6 space-y-4">
              <li className="flex gap-4">
                <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-stone-900 text-sm font-medium text-white">
                  1
                </span>
                <div>
                  <p className="font-medium">Upload the trial balance</p>
                  <p className="text-sm text-stone-600">
                    Same file you&apos;d normally drop into a template.
                  </p>
                </div>
              </li>
              <li className="flex gap-4">
                <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-stone-900 text-sm font-medium text-white">
                  2
                </span>
                <div>
                  <p className="font-medium">Confirm mappings</p>
                  <p className="text-sm text-stone-600">
                    Fix anything the suggestions got wrong — unusual accounts, one-offs,
                    reclasses.
                  </p>
                </div>
              </li>
              <li className="flex gap-4">
                <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-stone-900 text-sm font-medium text-white">
                  3
                </span>
                <div>
                  <p className="font-medium">Generate and review</p>
                  <p className="text-sm text-stone-600">
                    SOPL, SOFP, SOCIE in the dashboard. Typical first run: mapping review
                    is where you spend time; regenerate is one click once mappings are
                    right.
                  </p>
                </div>
              </li>
            </ol>
          </div>
        </section>

        <section className="border-b border-stone-200 bg-white">
          <div className="mx-auto max-w-5xl px-6 py-14">
            <h2 className="text-2xl font-semibold tracking-tight">Who it&apos;s for</h2>
            <ul className="mt-4 list-disc space-y-2 pl-5 text-stone-600">
              <li>Small and mid-size accounting practices doing regular management accounts</li>
              <li>Fractional CFOs with several similar clients on comparable charts</li>
              <li>Teams tired of maintaining one master spreadsheet per client</li>
            </ul>
            <p className="mt-4 text-sm text-stone-600">
              Best fit: clients where a standard chart maps cleanly to management lines.
              Messy or highly bespoke charts of accounts still work — you&apos;ll just spend
              longer on mapping review.
            </p>
          </div>
        </section>

        <section id="waitlist" className="border-b border-stone-200">
          <div className="mx-auto max-w-5xl px-6 py-14">
            <h2 className="text-2xl font-semibold tracking-tight">Get early access</h2>
            <p className="mt-3 max-w-2xl text-stone-600">
              We&apos;re opening Kastree to a handful of practices for structured
              feedback — not a public launch. Tell us who you are and we&apos;ll reach out
              when there&apos;s a slot.
            </p>
            <div className="mt-8 max-w-xl">
              <WaitlistForm />
            </div>
          </div>
        </section>

        <section className="bg-white">
          <div className="mx-auto max-w-5xl px-6 py-14">
            <h2 className="text-2xl font-semibold tracking-tight">FAQ</h2>
            <dl className="mt-6 space-y-6">
              {FAQ.map((item) => (
                <div key={item.q}>
                  <dt className="font-medium text-stone-900">{item.q}</dt>
                  <dd className="mt-1 text-sm text-stone-600">{item.a}</dd>
                </div>
              ))}
            </dl>
          </div>
        </section>
      </main>

      <footer className="border-t border-stone-200 bg-stone-100">
        <div className="mx-auto max-w-5xl px-6 py-8 text-xs text-stone-500">
          <p>{DISCLAIMER_TEXT}</p>
          <p className="mt-2">© {new Date().getFullYear()} {APP_NAME}</p>
        </div>
      </footer>
    </div>
  );
}
