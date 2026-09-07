# Data Processing Agreement (DPA) Template — Kastree

> **DRAFT — pending solicitor review, not yet legally reviewed.**  
> This document is an internal draft / template only. It is **not** published
> on kastree.ie and must **not** be offered to customers as a binding DPA until
> reviewed and approved by a qualified solicitor (Ireland / GDPR). Do not treat
> this as legal advice.

**Draft version:** 0.1  
**Draft date:** 7 September 2026  
**Related live policy:** https://www.kastree.ie/privacy  

---

## Parties

This Data Processing Agreement (“**DPA**”) is entered into between:

1. **Customer** — the accounting practice or other organisation that uses
   Kastree and determines the purposes and means of processing Client Personal
   Data (the “**Controller**”); and  
2. **Kastree** — contact: [infokastree@gmail.com](mailto:infokastree@gmail.com)
   (the “**Processor**”).

(Collectively, the “**Parties**”.)

This DPA supplements the Kastree Terms of Service (once executed / accepted)
and the Privacy Policy. If there is a conflict regarding personal-data
processing terms, this DPA prevails for that subject matter.

---

## 1. Definitions

- **Client Personal Data** — personal data relating to the Controller’s clients
  (and related individuals) that the Controller uploads to or generates in the
  Service (for example names embedded in trial-balance account descriptions,
  client/company labels, user account data within the Controller’s
  organisation, and content of uploaded files).
- **Data Protection Law** — GDPR (Regulation (EU) 2016/679), and applicable
  Irish / UK data-protection law as relevant to the processing.
- **Service** — the Kastree B2B SaaS application (trial-balance upload, mapping,
  statement generation, variance/risk/performance features, exports, and related
  functionality).
- **Sub-processor** — a third party engaged by Processor to process Client
  Personal Data on behalf of Controller in providing the Service.

Terms such as “personal data”, “processing”, “controller”, “processor”, and
“personal data breach” have the meanings in GDPR Article 4.

---

## 2. Roles of the Parties

1. Controller determines the purposes and means of processing Client Personal
   Data (including which client files to upload and how long to retain working
   papers within the Service).
2. Processor processes Client Personal Data **only** to provide, secure, and
   support the Service, and on documented instructions from Controller (including
   these Terms / this DPA and configuration / use of the Service).
3. Processor shall not process Client Personal Data for its own marketing of
   unrelated products, and shall not sell Client Personal Data.

---

## 3. Scope, nature, and purpose of processing

| Item | Description |
|------|-------------|
| **Subject matter** | Hosting and processing of data necessary to operate Kastree for Controller |
| **Duration** | For the term of Controller’s use of the Service, plus retention required by the DPA / Privacy Policy / legal obligation |
| **Nature** | Collection (via upload), storage, organisation, retrieval, transmission (e.g. exports), restriction, erasure, and related automated processing |
| **Purpose** | Providing the Service: account access, trial-balance parsing, mapping, statement/variance/risk/performance generation, optional AI-assisted narrative/mapping features where enabled, export generation, support, security, and audit logging |
| **Types of personal data** | Account identifiers (e.g. name, email, role); organisation membership; client/company names and related labels; content of uploaded trial-balance files and derived statement artefacts that may include personal data; IP / technical logs as needed for security; export files |
| **Categories of data subjects** | Controller’s users; Controller’s clients and individuals identifiable in uploaded or derived financial records |

Controller is responsible for ensuring it has a lawful basis and any required
notices/consents to upload Client Personal Data into the Service.

---

## 4. Processor obligations (GDPR Article 28)

Processor shall:

1. process Client Personal Data only on documented instructions from Controller,
   unless required by EU or Member State law (in which case Processor will
   inform Controller before processing where legally permitted);
2. ensure persons authorised to process Client Personal Data are bound by
   confidentiality;
3. implement appropriate technical and organisational measures (Section 5);
4. engage Sub-processors only under Section 6;
5. taking into account the nature of processing, assist Controller by
   appropriate technical and organisational measures, insofar as possible, with
   Controller’s obligations to respond to data-subject requests;
6. assist Controller with security, breach, DPIA, and prior-consultation
   obligations under Articles 32–36, taking into account the nature of
   processing and information available to Processor;
7. at Controller’s choice, delete or return Client Personal Data after the end
   of provision of services relating to processing, and delete existing copies
   unless EU/Member State law requires storage (Section 8);
8. make available to Controller information necessary to demonstrate compliance
   with Article 28, and allow for and contribute to audits under Section 9;
9. promptly inform Controller if, in Processor’s opinion, an instruction
   infringes Data Protection Law.

---

## 5. Security measures (current Service controls)

Processor maintains, among other measures appropriate to the Service as built:

| Control | Description (as implemented / intended in production) |
|---------|--------------------------------------------------------|
| **Access control & auth** | Authentication via Clerk; organisation-scoped authorisation |
| **Row-level isolation** | PostgreSQL row-level security (RLS) and application-layer filters by organisation / ownership paths |
| **Encryption in transit** | TLS for the public website and API |
| **Encryption at rest** | Encryption provided by hosting / storage providers for database and object storage (provider-managed) |
| **Least privilege** | Role-based access within organisations; operational secrets via environment/secret stores |
| **Auditability** | Audit-style logging of important actions; soft-delete and hash-verified `archived_records` snapshots for certain delete flows |
| **Export retention** | Generated export objects under the `exports/` prefix subject to a **30-day** lifecycle expiry in Cloudflare R2 |
| **AI prompt hygiene** | Where OpenAI (or similar) is used for commentary/mapping assistance, prompts are designed **not** to include raw monetary amounts |

**DRAFT NOTE FOR SOLICITOR / SECURITY:** Expand into a formal TOMs schedule
(Article 32) with named standards, backup RPO/RTO, vulnerability management,
and staff access procedures before customer signature.

Controller is responsible for securing its own user credentials and for
classifying what it uploads.

---

## 6. Sub-processors

Controller authorises Processor to use the following **current** Sub-processors
(and their relevant infrastructure affiliates) to provide the Service:

| Sub-processor | Role in Kastree |
|---------------|-----------------|
| **Clerk** | Authentication, sessions, organisation membership |
| **Railway** | Hosts API, PostgreSQL database, and volume storage for uploaded trial-balance files |
| **Vercel** | Hosts the kastree.ie frontend; cookieless Web Analytics on the public site |
| **Cloudflare R2** | Object storage for generated export files |
| **Resend** | Transactional email triggered by the Kastree API (e.g. founder/ops alerts on organisation signup) |
| **OpenAI** | Optional AI commentary / mapping assistance **when that integration is enabled** (not required for core deterministic statement math) |

Stripe may be used later for billing when a paywall is enabled; until live, it
is not an active Sub-processor for Client Personal Data in production.

### 6.1 Changes to Sub-processors

Processor will maintain an up-to-date list (including via the Privacy Policy
and/or a Sub-processor page once published). Processor will give Controller
notice of intended additions or replacements of Sub-processors and a reasonable
objection window (suggested draft: **14 days**) before the change applies to
Controller’s Tenant data, except for emergency security replacements.

### 6.2 Sub-processor flow-down

Processor will impose data-protection obligations on Sub-processors materially
no less protective than those in this DPA, including Article 28(3) requirements
where applicable. Processor remains responsible to Controller for
Sub-processor performance.

### 6.3 International transfers

Where Sub-processors process data outside Ireland/the EEA (including the United
States), Processor will ensure an appropriate transfer mechanism is in place
(for example Standard Contractual Clauses and any required supplementary
measures offered by that Sub-processor).

---

## 7. Personal data breaches

Processor shall notify Controller **without undue delay** after becoming aware
of a personal data breach affecting Client Personal Data (suggested draft
target: **within 72 hours** where feasible), and provide information
reasonably available to assist Controller with its Article 33/34 obligations,
including nature of the breach, likely consequences, and measures taken or
proposed.

---

## 8. Return and deletion on termination

Upon termination of the Service or earlier written request:

1. Controller should export any data it requires using product export features
   while access remains available.
2. Processor will, at Controller’s choice and subject to technical feasibility:
   - enable return/export of Client Personal Data; and/or
   - delete or anonymise Client Personal Data from active systems,
   except where retention is required by law or by documented security /
   accounting-trail needs described in the Privacy Policy (including soft-delete
   and archive snapshot practices).
3. Generated export files in R2 under `exports/` expire under the **30-day**
   lifecycle rule; other backups/prefixes may follow separate retention.

**DRAFT NOTE FOR SOLICITOR:** Align deletion timelines, archive retention, and
“anonymise vs erase” language with Irish/EU expectations for financial working
papers held by a processor.

---

## 9. Audit rights

Upon reasonable written notice (suggested draft: **30 days**), no more than
once per twelve-month period (unless a competent authority or documented breach
requires more), Controller may:

- request information and security documentation reasonably necessary to
  demonstrate compliance with this DPA; and/or
- conduct an audit (or appoint an independent auditor bound by
  confidentiality), during business hours, without unreasonably disrupting
  operations.

Processor may satisfy audit requests in whole or part via third-party
certifications, SOC/ISO reports from Sub-processors, or written questionnaires,
where those adequately address the request.

Controller bears its own audit costs unless the audit reveals material breach
of this DPA by Processor.

---

## 10. Liability

Liability under this DPA is subject to the limitations and exclusions in the
Terms of Service, except where prohibited by Data Protection Law. Each Party
remains responsible for its own fines under GDPR to the extent attributable to
its own breach.

**DRAFT NOTE FOR SOLICITOR:** Indemnities (controller↔processor) need explicit
drafting for Irish B2B SaaS.

---

## 11. Term

This DPA takes effect on the date of last signature (or electronic acceptance)
and continues until Processor ceases processing Client Personal Data for
Controller.

---

## 12. Governing law

This DPA is governed by the laws of **Ireland**, unless mandatory Data
Protection Law requires otherwise for specific provisions.

---

## 13. Contact

**Processor privacy / DPA contact:** [infokastree@gmail.com](mailto:infokastree@gmail.com)

---

## Signature block (template)

| | Controller | Processor (Kastree) |
|--|------------|---------------------|
| Signature | | |
| Name | | |
| Title | | |
| Date | | |
| Entity name | | Kastree |
| Email | | infokastree@gmail.com |

---

## Document control

| Field | Value |
|-------|--------|
| Status | **DRAFT — pending solicitor review, not yet legally reviewed** |
| Live on kastree.ie? | **No — do not publish until approved** |
| Replaces | One-line placeholder previously in this file |
| Related | Privacy Policy (live), Terms of Service draft (`docs/terms-of-service.md`) |
