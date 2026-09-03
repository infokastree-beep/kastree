# Privacy Policy

**Last updated:** 3 September 2026  
**Contact:** [infokastree@gmail.com](mailto:infokastree@gmail.com)

This policy describes how Kastree handles data on kastree.ie and in the Kastree
product as it works today. It is not legal advice. If anything here becomes
inaccurate as the product changes, we will update this page.

**Who is responsible.** Kastree (contact above) determines how the website,
waitlist, and product accounts are run. If an accountancy practice uses Kastree
for its clients’ books, that practice is typically the controller of those
client financial records and Kastree processes them to provide the service. A
formal Data Processing Agreement for practices is planned; it is not published
on this site yet.

## What we collect

**Waitlist (public form).** When you join the waitlist we store: name, email,
firm, role, and optionally approximate client count and a short note about your
main pain point. We also see technical request metadata (such as IP address)
used for rate limiting and abuse prevention.

**Accounts.** Sign-up and sign-in are provided by **Clerk**. Clerk holds your
authentication credentials and session. Via Clerk (including webhooks) we
receive identifiers and profile fields such as email address, name, Clerk user
id, and organisation membership/role, and we store matching **user** and
**organisation** rows in our application database so the product can authorise
access.

**Product data you create or upload.** Inside a signed-in organisation we
process:

- client groups and companies you create;
- trial-balance files you upload (Excel or CSV) and the parsed account rows;
- account mappings you confirm;
- generated statements (SOPL, SOFP, SOCIE), variance and risk outputs;
- export jobs and the generated Excel/PDF/CSV files;
- operational records needed to run the service (for example processing status
  and audit-style logs of important actions).

**Website analytics.** See the “Website analytics” section below.

We do not sell personal data.

## How we use it

- To run the waitlist and email you about access (and, when configured, to
  notify our team of a new signup).
- To authenticate you through Clerk and enforce organisation boundaries
  (including database row-level isolation between organisations).
- To parse trial balances, build statements, and generate downloads you request.
- To keep soft-deleted records and archive snapshots when you delete a client
  or company (see Retention).
- To secure and operate the service (rate limits, error handling, audit trails).
- To measure aggregate traffic on the public site via cookieless analytics.

## Who processes data for us

These providers process data only to run their part of Kastree:

| Provider | What they do for Kastree today |
|----------|--------------------------------|
| **Clerk** | Authentication, sessions, organisation membership |
| **Railway** | Hosts the Kastree API, the PostgreSQL database, and a persistent volume used for uploaded trial-balance files |
| **Vercel** | Hosts the kastree.ie frontend and provides Web Analytics |
| **Cloudflare R2** | Stores **generated export files** (not the primary trial-balance upload store) |
| **Resend** | Sends transactional email such as waitlist confirmation (from our configured Kastree sender address) |

**OpenAI** may be used later for optional AI commentary or mapping assistance
when that integration is enabled. Core statement generation does not require
OpenAI. When used, our prompts are designed not to include raw monetary
amounts. Stripe billing is designed in the product but is **not** active as a
live payment processor on the current deployment.

Some providers (notably Clerk, Resend, Vercel, Cloudflare, and OpenAI if
enabled) may process data in the United States or other regions outside
Ireland/the EEA. Where they do, we rely on their published contractual
safeguards (including Standard Contractual Clauses where they provide them).
We will maintain a formal sub-processor list and DPA pack as we onboard paying
practices.

We may disclose data if required by law or to protect the service against
security threats or abuse.

## Where data lives

- **Identity / login:** Clerk.
- **Application database** (users, organisations, clients, companies, trial
  balances metadata, mappings, statements, waitlist rows, archive snapshots,
  logs): PostgreSQL on **Railway**.
- **Uploaded trial-balance files:** stored as files on a **Railway volume**
  attached to the API service (not in R2).
- **Generated export files:** **Cloudflare R2** bucket used for exports.
- **Public website:** **Vercel**.
- **Email delivery:** **Resend**.

## Retention and deletion

| Data | What we do today |
|------|------------------|
| Waitlist entries | Kept so we can manage early access; remove on request where straightforward |
| Account profile in our database | Kept while the account/organisation exists |
| Trial-balance files on the Railway volume | Kept while needed for processing and ongoing use of that upload in the product |
| Statement data, mappings, and related database records | Kept to provide the product and preserve working history; we do not treat a casual delete as wiping the underlying accounting trail |
| **Client or company delete** | **Soft-delete** (`is_deleted` / `deleted_at`) plus an **`archived_records` snapshot** (hash-verified archive row) — not an immediate hard delete of that record |
| **Generated export files in R2** | Subject to a bucket lifecycle rule on the **`exports/`** prefix: objects expire after **30 days**. Other prefixes (including **`db-backups/`**) are not covered by that export expiry rule |
| Website analytics | Anonymised/aggregate only; retained under Vercel’s analytics practices |

Not every entity type in the product yet writes an archive snapshot on delete
(for example trial balances). Where archival is wired today, it is for **client
and company** soft-deletes as described above.

If you ask us to erase personal data we will remove or anonymise waitlist and
account PII where we can. Financial working data may be retained or anonymised
rather than fully erased where we need a continuing accounting or security
record.

## Website analytics

We use **Vercel Web Analytics** on kastree.ie. It is cookieless and collects
only anonymised, aggregate visitor statistics — such as page views, referrers,
and general location or device type. It does not collect personal identifiers,
does not track you across other sites, and does not tie analytics data to
individuals. Nothing is written to your device for this purpose, so no cookie
consent banner is required for this analytics alone.

## Your rights

Depending on applicable law (including UK/EU GDPR), you may have rights to
access, correct, or delete personal data, to object to or restrict certain
processing, and to complain to a supervisory authority (in Ireland, the
[Data Protection Commission](https://www.dataprotection.ie/en/individuals/exercising-your-rights/raising-concern-commission)).
Email [infokastree@gmail.com](mailto:infokastree@gmail.com).

Clerk and the logged-in product may use cookies or similar storage that are
necessary for authentication and app function. Those are separate from the
cookieless Vercel Web Analytics described above.

## Changes

We may update this policy when the product or our providers change. The “Last
updated” date at the top will change when we do.
