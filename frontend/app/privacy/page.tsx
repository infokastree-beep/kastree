import type { Metadata } from "next";
import Link from "next/link";
import { APP_NAME } from "@/lib/constants";

export const metadata: Metadata = {
  title: `Privacy Policy — ${APP_NAME}`,
  description:
    "How Kastree collects, stores, and shares data for waitlist, accounts, and the product.",
};

export default function PrivacyPage() {
  return (
    <div className="min-h-screen bg-surface text-ink">
      <header className="border-b border-line">
        <div className="mx-auto flex max-w-content items-center justify-between px-6 py-5 sm:px-8">
          <Link
            href="/"
            className="font-display text-lg font-medium tracking-tight text-ink"
          >
            {APP_NAME}
          </Link>
          <Link
            href="/"
            className="text-sm text-ink-secondary underline-offset-4 hover:underline"
          >
            Home
          </Link>
        </div>
      </header>

      <main className="mx-auto max-w-content px-6 py-section-sm sm:px-8 sm:py-section">
        <p className="text-sm text-ink-secondary">Last updated: 3 September 2026</p>
        <h1 className="mt-3 font-display text-heading-lg text-ink sm:text-[2.25rem]">
          Privacy Policy
        </h1>
        <div className="mt-10 max-w-2xl space-y-8 text-base leading-relaxed text-ink-secondary">
          <p>
            This policy describes how Kastree handles data on kastree.ie and in
            the Kastree product as it works today. It is not legal advice. If
            anything here becomes inaccurate as the product changes, we will
            update this page.
          </p>
          <p>
            <strong className="font-medium text-ink">Who is responsible.</strong>{" "}
            Kastree (
            <a
              href="mailto:infokastree@gmail.com"
              className="text-ink underline-offset-4 hover:underline"
            >
              infokastree@gmail.com
            </a>
            ) determines how the website, waitlist, and product accounts are
            run. If an accountancy practice uses Kastree for its clients&apos;
            books, that practice is typically the controller of those client
            financial records and Kastree processes them to provide the
            service. A formal Data Processing Agreement for practices is
            planned; it is not published on this site yet.
          </p>

          <section>
            <h2 className="font-display text-heading-md text-ink">
              What we collect
            </h2>
            <p className="mt-3">
              <strong className="font-medium text-ink">Waitlist (public form).</strong>{" "}
              When you join the waitlist we store: name, email, firm, role, and
              optionally approximate client count and a short note about your
              main pain point. We also see technical request metadata (such as
              IP address) used for rate limiting and abuse prevention.
            </p>
            <p className="mt-3">
              <strong className="font-medium text-ink">Accounts.</strong> Sign-up
              and sign-in are provided by{" "}
              <strong className="font-medium text-ink">Clerk</strong>. Clerk holds
              your authentication credentials and session. Via Clerk (including
              webhooks) we receive identifiers and profile fields such as email
              address, name, Clerk user id, and organisation membership/role,
              and we store matching user and organisation rows in our
              application database so the product can authorise access.
            </p>
            <p className="mt-3">
              <strong className="font-medium text-ink">
                Product data you create or upload.
              </strong>{" "}
              Inside a signed-in organisation we process: client groups and
              companies you create; trial-balance files you upload (Excel or
              CSV) and the parsed account rows; account mappings you confirm;
              generated statements (SOPL, SOFP, SOCIE), variance and risk
              outputs; export jobs and the generated Excel/PDF/CSV files; and
              operational records needed to run the service (for example
              processing status and audit-style logs of important actions).
            </p>
            <p className="mt-3">
              <strong className="font-medium text-ink">Website analytics.</strong>{" "}
              See the “Website analytics” section below.
            </p>
            <p className="mt-3">We do not sell personal data.</p>
          </section>

          <section>
            <h2 className="font-display text-heading-md text-ink">
              How we use it
            </h2>
            <ul className="mt-3 list-disc space-y-2 pl-5">
              <li>
                To run the waitlist and email you about access (and, when
                configured, to notify our team of a new signup).
              </li>
              <li>
                To authenticate you through Clerk and enforce organisation
                boundaries (including database row-level isolation between
                organisations).
              </li>
              <li>
                To parse trial balances, build statements, and generate
                downloads you request.
              </li>
              <li>
                To keep soft-deleted records and archive snapshots when you
                delete a client or company (see Retention).
              </li>
              <li>
                To secure and operate the service (rate limits, error handling,
                audit trails).
              </li>
              <li>
                To measure aggregate traffic on the public site via cookieless
                analytics.
              </li>
            </ul>
          </section>

          <section>
            <h2 className="font-display text-heading-md text-ink">
              Who processes data for us
            </h2>
            <p className="mt-3">
              These providers process data only to run their part of Kastree:
            </p>
            <ul className="mt-3 list-disc space-y-2 pl-5">
              <li>
                <strong className="font-medium text-ink">Clerk</strong> —
                authentication, sessions, organisation membership
              </li>
              <li>
                <strong className="font-medium text-ink">Railway</strong> — hosts
                the Kastree API, the PostgreSQL database, and a persistent
                volume used for uploaded trial-balance files
              </li>
              <li>
                <strong className="font-medium text-ink">Vercel</strong> — hosts
                the kastree.ie frontend and provides Web Analytics
              </li>
              <li>
                <strong className="font-medium text-ink">Cloudflare R2</strong> —
                stores generated export files (not the primary trial-balance
                upload store)
              </li>
              <li>
                <strong className="font-medium text-ink">Resend</strong> — sends
                transactional email such as waitlist confirmation (from our
                configured Kastree sender address)
              </li>
            </ul>
            <p className="mt-3">
              <strong className="font-medium text-ink">OpenAI</strong> may be used
              later for optional AI commentary or mapping assistance when that
              integration is enabled. Core statement generation does not require
              OpenAI. When used, our prompts are designed not to include raw
              monetary amounts. Stripe billing is designed in the product but is{" "}
              <strong className="font-medium text-ink">not</strong> active as a
              live payment processor on the current deployment.
            </p>
            <p className="mt-3">
              Some providers (notably Clerk, Resend, Vercel, Cloudflare, and
              OpenAI if enabled) may process data in the United States or other
              regions outside Ireland/the EEA. Where they do, we rely on their
              published contractual safeguards (including Standard Contractual
              Clauses where they provide them). We will maintain a formal
              sub-processor list and DPA pack as we onboard paying practices.
            </p>
            <p className="mt-3">
              We may disclose data if required by law or to protect the service
              against security threats or abuse.
            </p>
          </section>

          <section>
            <h2 className="font-display text-heading-md text-ink">
              Where data lives
            </h2>
            <ul className="mt-3 list-disc space-y-2 pl-5">
              <li>
                <strong className="font-medium text-ink">Identity / login:</strong>{" "}
                Clerk.
              </li>
              <li>
                <strong className="font-medium text-ink">Application database</strong>{" "}
                (users, organisations, clients, companies, trial balances
                metadata, mappings, statements, waitlist rows, archive
                snapshots, logs): PostgreSQL on Railway.
              </li>
              <li>
                <strong className="font-medium text-ink">
                  Uploaded trial-balance files:
                </strong>{" "}
                stored as files on a Railway volume attached to the API service
                (not in R2).
              </li>
              <li>
                <strong className="font-medium text-ink">
                  Generated export files:
                </strong>{" "}
                Cloudflare R2 bucket used for exports.
              </li>
              <li>
                <strong className="font-medium text-ink">Public website:</strong>{" "}
                Vercel.
              </li>
              <li>
                <strong className="font-medium text-ink">Email delivery:</strong>{" "}
                Resend.
              </li>
            </ul>
          </section>

          <section>
            <h2 className="font-display text-heading-md text-ink">
              Retention and deletion
            </h2>
            <ul className="mt-3 list-disc space-y-2 pl-5">
              <li>
                <strong className="font-medium text-ink">Waitlist entries</strong> —
                kept so we can manage early access; remove on request where
                straightforward.
              </li>
              <li>
                <strong className="font-medium text-ink">Account profile</strong> in
                our database — kept while the account/organisation exists.
              </li>
              <li>
                <strong className="font-medium text-ink">
                  Trial-balance files
                </strong>{" "}
                on the Railway volume — kept while needed for processing and
                ongoing use of that upload in the product.
              </li>
              <li>
                <strong className="font-medium text-ink">
                  Statement data, mappings, and related database records
                </strong>{" "}
                — kept to provide the product and preserve working history; we
                do not treat a casual delete as wiping the underlying accounting
                trail.
              </li>
              <li>
                <strong className="font-medium text-ink">
                  Client, company, or trial balance delete
                </strong>{" "}
                — soft-delete (<code className="text-ink">is_deleted</code> /{" "}
                <code className="text-ink">deleted_at</code>) plus an{" "}
                <code className="text-ink">archived_records</code> snapshot
                (hash-verified archive row) — not an immediate hard delete of
                that record.
              </li>
              <li>
                <strong className="font-medium text-ink">
                  Generated export files in R2
                </strong>{" "}
                — subject to a bucket lifecycle rule on the{" "}
                <code className="text-ink">exports/</code> prefix: objects expire
                after <strong className="font-medium text-ink">30 days</strong>.
                Other prefixes (including{" "}
                <code className="text-ink">db-backups/</code>) are not covered by
                that export expiry rule.
              </li>
              <li>
                <strong className="font-medium text-ink">Website analytics</strong> —
                anonymised/aggregate only; retained under Vercel’s analytics
                practices.
              </li>
            </ul>
            <p className="mt-3">
              Statement regenerate still replaces rows in place without a
              separate archive write. Soft-delete archival is wired today for{" "}
              <strong className="font-medium text-ink">
                clients, companies, and trial balances
              </strong>{" "}
              as described above.
            </p>
            <p className="mt-3">
              If you ask us to erase personal data we will remove or anonymise
              waitlist and account PII where we can. Financial working data may
              be retained or anonymised rather than fully erased where we need a
              continuing accounting or security record.
            </p>
          </section>

          <section>
            <h2 className="font-display text-heading-md text-ink">
              Website analytics
            </h2>
            <p className="mt-3">
              We use{" "}
              <strong className="font-medium text-ink">Vercel Web Analytics</strong>{" "}
              on kastree.ie. It is cookieless and collects only anonymised,
              aggregate visitor statistics — such as page views, referrers, and
              general location or device type. It does not collect personal
              identifiers, does not track you across other sites, and does not
              tie analytics data to individuals. Nothing is written to your
              device for this purpose, so no cookie consent banner is required
              for this analytics alone.
            </p>
          </section>

          <section>
            <h2 className="font-display text-heading-md text-ink">Your rights</h2>
            <p className="mt-3">
              Depending on applicable law (including UK/EU GDPR), you may have
              rights to access, correct, or delete personal data, to object to
              or restrict certain processing, and to complain to a supervisory
              authority (in Ireland, the{" "}
              <a
                href="https://www.dataprotection.ie/en/individuals/exercising-your-rights/raising-concern-commission"
                className="text-ink underline-offset-4 hover:underline"
                target="_blank"
                rel="noopener noreferrer"
              >
                Data Protection Commission
              </a>
              ). Email{" "}
              <a
                href="mailto:infokastree@gmail.com"
                className="text-ink underline-offset-4 hover:underline"
              >
                infokastree@gmail.com
              </a>
              .
            </p>
            <p className="mt-3">
              Clerk and the logged-in product may use cookies or similar storage
              that are necessary for authentication and app function. Those are
              separate from the cookieless Vercel Web Analytics described above.
            </p>
          </section>

          <section>
            <h2 className="font-display text-heading-md text-ink">Changes</h2>
            <p className="mt-3">
              We may update this policy when the product or our providers
              change. The “Last updated” date at the top will change when we do.
            </p>
          </section>
        </div>
      </main>
    </div>
  );
}
