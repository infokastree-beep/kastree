# Statutory set of accounts — design for approval

**Status:** decisions recorded 7 October 2026. Phase 2 step 1 is only the
workspace error banner. The rest of this note is not built.

**Decisions.**

1. A 1A.9 disagreement warns. It does not block FINAL. Two disclosure
   questions are added: gains or losses in other comprehensive income
   exist; equity changed other than through profit or loss (including
   dividends or share issues). Unanswered blocks FINAL, the same as other
   disclosures. "Yes" with the matching statement switched off is a warning.
2. Principal activity is a new `principal_activity` text column. `industry`
   is not reused.
3. Business address is one multi-line text field.
4. Advisers wait. The new company columns are `business_address`,
   `incorporated_on`, and `principal_activity`.
5. The screen says "source not confirmed". The accounts print no legal
   citation until a reviewer or solicitor confirms it. Citations live in
   the pack file, not in code.
6. Members may edit company details. Each change writes an audit-log entry.
   Finalise stays admin or owner (`require_client_admin` on the existing
   finalise route).
7. Phase 2 step 1 surfaces the dashboard and statements errors, with the
   exact API sentence and a link to Sub-line review. No other product
   change in that step. That step adds no migration.

**Statement of income and retained earnings.** FRS 102 (September 2024)
paragraph 6.4, pointing at paragraph 3.18, permits one statement of income
and retained earnings in place of a statement of comprehensive income and
a statement of changes in equity only when the only changes to equity
during the periods presented are profit or loss, payment of dividends,
corrections of prior period material errors, and changes in accounting
policy. Paragraph 6.5 then requires opening retained earnings, dividends
declared and paid or payable, restatements for material errors, restatements
for accounting-policy changes, and closing retained earnings, plus the
income statement. A small entity is not required to comply with paragraph
3.18 or with Section 6 (paragraphs 1A.7 and 6.1A). Paragraph 1A.9(b) is
the operative "may need" rule, and it names either a statement of changes
in equity or a statement of income and retained earnings.

`check_re_rollforward` (`V-RE-001`) already uses opening retained earnings,
profit, dividends, and closing retained earnings. Those four figures are
enough for a basic statement of income and retained earnings when the check
passes and share capital and share premium did not move. They are not a
full statement of changes in equity: there is no other comprehensive
income, no classified share issue or own-share movement, and the
transition adjustment on the check is not passed by the reconciliation
caller. Dividends alone still fit paragraph 6.4. A share issue does not.
That basic statement is ahead of waiting for a new 1A.9 evaluator. It is
not part of step 1.

**Page.** One address stays: `/year-ends/{id}/draft`, one component
`StatutoryDraftWorkspace`, one framework dropdown. No route per framework.
Statutory drafts stay behind the platform-admin gate until reviewer sign-off.

**Figures.** Python and the statement engine own every amount. Section
toggles, report setup, and company details never change a calculation. No
LLM writes a fact or a sentence in this work. Narrative drafting stays out
until the DPA and EU-residency review are done.

**Cuts that stay cut.** Auditor's report (row 13). Free-text note overrides
and text blocks. Bank reconciliation. UK pack. Strategic report, ESG,
consolidation, XBRL, workpapers, styles, comments, notepad, roll forward,
compare reports, cash-flow builder, FX. Roll forward and compare must not
be blocked by this shape: Home lists drafts and does not own the only copy
of a year end.

---

## 1. Sections the FRS 102 pack would declare

The pack file `findraft/content/frs102-1a-ie/2024.09/pack.json` gains a
`sections` array. The sidebar reads that array through the existing
`GET /year-ends/frameworks` catalogue. `WorkspaceSidebar` keeps receiving
`sections` as props and still must not contain a framework name.

Form 11 Summary stays `available: false`. It does not inherit this list.
An unknown framework id stays Report setup plus Review dashboard.

| Order | id | Label | Group | Default | Lock | Source |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | `cover` | Cover | usually-required | on | user toggle | Company law / convention. Citation stored, confirmed at reviewer sign-off, not assumed. |
| 2 | `contents` | Contents | usually-required | on | user toggle | Generated from enabled sections. Same source rule. |
| 3 | `directors-info` | Directors and other information | usually-required | on | user toggle | Same source rule. |
| 4 | `directors-report` | Directors' report | usually-required | on | user toggle | Same source rule. Week 11 page is reused. |
| 5 | `directors-responsibilities` | Directors' responsibilities statement | usually-required | on | user toggle | Same source rule. |
| 6 | `compilation` | Compilation report | usually-required | on | user toggle | Professional convention, not FRS 102. Week 11 page is reused. The page already says it is not an audit and not a review. |
| 7 | `income` | Income statement | frs-locked | on | locked on | FRS 102 (September 2024) 1A.8(b). |
| 8 | `oci` | Statement of comprehensive income | engine-conditional | engine | user toggle | 1A.9(a), only if other comprehensive income exists. |
| 9 | `sofp` | Statement of financial position | frs-locked | on | locked on | 1A.8(a), including the 1A.6A compliance statement already rendered above the face. |
| 10 | `socie` | Statement of changes in equity | engine-conditional | engine | user toggle | 1A.9(b), only if equity moves other than through profit or loss. |
| 11 | `cash-flow` | Cash flow statement | off | off | user toggle | Not required, 1A.7A. No cash-flow builder in this work. |
| 12 | `notes` | Notes | frs-locked | on | locked on | 1A.8(c). Includes basis of preparation (1AD.3) and accounting policies (1AD.4). Note *blocks* stay on disclosure answers. |
| 13 | `trading` | Supplementary trading statement | off | off | user toggle | Not an FRS 102 Section 1A statement. |

Auditor's report is absent from the array.

**Engine signals that do not exist yet.** `statutory_statements.py` and
`StatementResponse` return income, SoFP, notes, and the Week 11 pages.
They do not return a statement of comprehensive income or a statement of
changes in equity. Product 1's SOCIE is a different builder and is not
called by this pack. Until the statutory engine exposes two booleans —
other comprehensive income exists, and equity moved other than through
profit or loss — both conditional sections default **off** and the
dashboard says the engine has not evaluated 1A.9(a) or 1A.9(b). The
toggle must not invent either statement.

**Cash flow and the trading statement.** Turning one on does not build
it. The section shows a plain "not built" panel and a dashboard notice.
No figures are created.

**Two levels.** Section on/off is this design. Inside Notes, which blocks
appear stays on `ANSWER_FLAGS` and the checklist `includeWhen` rules.
Unanswered stays unanswered. Free-text editing stays cut.

### Toggle storage

Toggle state is a map on the existing `findraft_year_ends.report_setup`
JSON, beside rounding, face dates, statement type, and column headers.
Shape:

```json
{ "sections": { "cover": true, "cash-flow": false } }
```

Absent keys mean "use the pack default", including the engine default for
`oci` and `socie`. Saving the map replaces presentation JSON only.

The statement **engine** (`build_statutory_statements` and anything that
sums a trial balance) must not import `report_setup`. A separate composer
reads the saved map after the engine has returned a document, and decides
which already-built sections are copied into the PDF. Turning a section
off drops it from that copy. Turning it back on copies it again. The
stored document and the API amounts stay complete, so a hidden section's
data is still there.

Locked ids (`income`, `sofp`, `notes`) are rejected with HTTP 422 if the
body sets them false. The stored map is not overwritten by that request.

Turning off a usually-required section is allowed. It raises a dashboard
**notice**, not a block, and does not by itself stop FINAL.

1A.9 is a "may need", not an automatic requirement. Turning `oci` or
`socie` off while the matching disclosure is Yes raises a warning and
does not block FINAL. Leaving either new disclosure unanswered blocks
FINAL, the same as the other disclosure questions. Cash flow and the
trading statement never block FINAL.

---

## 2. Sidebar

`WorkspaceSidebar` stays a list of buttons. It does not know FRS 102.
Grouping, locks, and the preview switch are data on each entry plus a
workspace mode. Proposed tree, in this order:

### Home

| Entry | What fills it | New? |
| --- | --- | --- |
| Draft list | Versions for this year end: version number, status, locked/frozen. Open stays on `?section=`. | New list over the existing draft version rows. |
| Start new report | Existing `statutory-new-report`. | Reused. |
| Lock | Existing `statutory-lock` / next-version button. | Reused. |

Roll forward and compare are not buttons. The list does not prevent a
later screen from reading the same drafts.

### Report options

| Entry | What fills it | New? |
| --- | --- | --- |
| Report setup | Existing `ReportSetupForm`: basis (read-only pack pin), rounding, face dates, statement type draft or compilation, column headers. | Reused. |
| Sections setup | One row per pack section: label, lock or "usually required" or "engine", toggle. | New form. |
| Signatories | Which recorded directors sign, and the approval date. No signature image, no workflow. | New form. |
| Events | Read-only audit rows for this year end (`report_setup_saved`, company details, disclosures, mark-all-no, signatories). | New read view over `audit_logs`. |

### Inputs

| Entry | What fills it | New? |
| --- | --- | --- |
| Trial balance | Read-only adopted Product 1 trial balance. Link back to Statements. No upload. | New read view over the adopted TB. |
| Mapping | Existing `StatutorySublineReview`. | Reused. |
| Adjustments | Existing narration, lines, post, lock. | Reused. |
| Prior-year comparatives | Existing prior-year gate, including "This is the first financial period". | New screen over the existing API. |
| Disclosures | Redesign below. | New panel, same answers. |
| Company details | Form in section 3. | New. |

### Sections

The pack order from section 1. The selected entry shows that part of the
document. Income and SoFP reuse the existing face tables. Directors'
report, compilation, and approval reuse the Week 11 paragraphs already
returned on the statement payload (`StatutoryPageOut`). Cover, contents,
and directors-and-other-information are new presentations of data the
composer already has. Notes reuse the note payload. OCI, SOCIE, cash
flow, and the trading statement show the engine result or the not-built
panel. They do not get a second calculator.

**Preview.** A workspace toggle, not a stored report setting. On: hide
sections whose saved toggle is off, and hide note blocks the disclosure
rules already exclude. Off: the preparer still sees a switched-off
section, marked off, so they can turn it back on. Preview never deletes
data.

**Locked and optional.** A locked row has no toggle. A usually-required
row shows "Usually required for filing" and the stored citation status
(`pending-reviewer-signoff` until sign-off). An engine-conditional row
shows the engine's current default next to the user's choice.

**Toggled off, preview off.** The row stays in the sidebar, dimmed, and
the panel says the section is off and its data is kept.

### Outputs

| Entry | What fills it | New? |
| --- | --- | --- |
| Draft PDF | Existing download. After the composer lands, the file follows the toggles and report-setup display. | Reused route, new compose step. |
| Product 1 risk export | Link to the existing risk export for the adopted trial balance, when that TB exists. | Link only. |
| Product 1 mapping export | Link to the existing mapping export for that TB. | Link only. |

Word is later. It is not a button.

### Disclosures checklist

Questions are the preparer flags in `ANSWER_FLAGS`
(`findraft/engine/notes.py`). Derived facts (`DERIVED`, including
`DIRECTOR_LOANS`, `FIXED_ASSETS_NBV`, `CREDITORS`, `DIVIDENDS_PAID`) are
not questions. Unanswered is never stored as No, and still blocks FINAL
through the existing `V-DISC-001` path.

Groups follow the checklist `note` field. Plain-English label is the
checklist topic, shortened only where the topic is the question itself.
Each row shows the note code and the checklist id. Each group header
shows answered and unanswered counts. Flags with no single checklist row
sit in "Other".

| Group | Flag | Plain-English question | Note |
| --- | --- | --- | --- |
| Accounting policies | `FORMAT_CHANGE` | Did the SoFP or income statement format change? | N1_POLICIES (1AD.8) |
| Accounting policies | `POLICY_CHANGE` | Did an accounting policy change? | N1_POLICIES (1AD.9) |
| Accounting policies | `PRIOR_RECLASS` | Are any prior-year amounts not comparable? | N1_POLICIES (1AD.10) |
| Accounting policies | `GOING_CONCERN_DEPARTURE` | Have the accounts departed from the going-concern basis? | N1_POLICIES (1AD.11) |
| Fixed assets | `GOODWILL` | Is goodwill recognised? | N2_FA (1AD.7) |
| Fixed assets | `DEV_COSTS` | Are development costs capitalised? | N2_FA (1AD.5) |
| Fixed assets | `DEV_COSTS_UNREALISED` | Are capitalised development costs not treated as a realised loss? | N2_FA (1AD.6) |
| Fixed assets | `REVALUATION_RESERVE` | Is there a revaluation reserve? | N2_FA (1AD.15–1AD.16) |
| Fixed assets | `REVAL_TRANSFER` | Was there a transfer to or from the revaluation reserve? | N6_CAPITAL (1AD.17) |
| Fixed assets | `CAPITALISED_BORROWING` | Were borrowing costs capitalised into an asset? | N2_FA (1AD.19) |
| Fixed assets | `IMPAIRMENT` | Was a fixed asset impaired? | N2_FA (1AD.20) |
| Fixed assets | `IMPAIRMENT_REVERSAL` | Was an impairment reversed? | N2_FA (1AD.21) |
| Fair value | `FI_FVPL` | Are financial instruments carried at fair value through profit or loss? | N3_DEBTORS (1AD.22) |
| Fair value | `NONFI_FV` | Are any non-financial assets at fair value? | N3_DEBTORS (1AD.23) |
| Fair value | `FV_VS_HC_DIFFERS` | Does fair value differ from historical cost for a carried item? | N3_DEBTORS (1AD.24) |
| Fair value | `FV_DESIGNATION` | Were instruments designated at fair value under an IFRS-consistent treatment? | 1AD.25 |
| Creditors | `SECURED_CREDITORS` | Are any creditors secured? | N4_CREDITORS (1AD.27) |
| Commitments | `CHARGES_EXIST` | Are there charges on assets? | N9_COMMITMENTS (1AD.28) |
| Commitments | `GUARANTEES_EXIST` | Has the company given guarantees or security? | N9_COMMITMENTS (1AD.29–1AD.30) |
| Commitments | `UNCOMMITTED` | Are there commitments not provided for? | N9_COMMITMENTS (1AD.31) |
| Commitments | `PENSION_COMMITMENT` | Are there retirement-benefit commitments? | N9_COMMITMENTS (1AD.32) |
| Commitments | `OFF_BALANCE_ARRANGEMENT` | Are there off-balance-sheet arrangements? | N9_COMMITMENTS (1AD.34) |
| Commitments | `COMMITMENTS_EXIST` | Are there other commitments the notes should pick up? | N9_COMMITMENTS |
| Commitments | `SUBSEQUENT_EVENTS` | Are there material events after the balance sheet date? | N9_COMMITMENTS (1AD.54) |
| Directors | `PAST_DIRECTOR_PENSION_COMMITMENTS` | Are there retirement-benefit commitments to past directors? | N7_RPT (1AD.33) |
| Directors | `PAST_DIRECTOR_BENEFITS` | Were retirement benefits paid or committed to past directors? | N7_RPT (1AD.39) |
| Directors | `THIRD_PARTY_DIRECTOR_SERVICES` | Was a third party paid to provide a director's services? | N5_LOANS (1AD.40) |
| Directors | `CONNECTED_LOANS` | Are there loans or credits with persons connected to directors? | N5_LOANS (1AD.42) |
| Directors | `DIRECTOR_LOAN_AGREEMENTS` | Are there agreements to enter into director loans or credits? | N5_LOANS (1AD.43) |
| Directors | `DIRECTOR_GUARANTEES` | Has the company guaranteed or secured a director or connected person? | N5_LOANS (1AD.44) |
| Directors | `DIRECTOR_GUARANTEE_AGREEMENTS` | Are there agreements to give those guarantees? | N5_LOANS (1AD.45) |
| Directors | `DIRECTOR_MATERIAL_INTEREST` | Does a director have a material interest in another arrangement? | N7_RPT (1AD.48) |
| Capital and group | `SMALL_GROUP_EXEMPTION` | Is a parent taking the small-group exemption? | N6_CAPITAL (1AD.47) |
| Capital and group | `OWN_SHARES_HELD` | Does the company or a nominee hold the company's own shares? | N6_CAPITAL (1AD.49) |
| Capital and group | `IS_SUBSIDIARY` | Is the company a subsidiary? | N6_CAPITAL (1AD.50) |
| Related parties | `RPT_EXISTS` | Were there related-party transactions? | N7_RPT (1AD.51) |
| Employees | `HAS_EMPLOYEES` | Did the company have employees in the period? | N8_EMPLOYEES (1AD.37) |
| Other | `DIRECTORS_EXIST` | Did any directors serve during the period? | N0_ENTITY (1AD.52) |
| Other | `REQUIRED_BY_FORMAT` | Do Schedule 3A format rules require an income-statement amount in the notes? | 1AD.36 |
| Other | `FORMAT_COMBINED` | Were format lines combined? | 1AD.53 |
| Other | `SET_OFF_USED` | Were amounts set off within an asset or income item? | 1AD.55 |
| Other | `MULTI_ITEM_ASSET` | Does one asset or liability relate to more than one SoFP line? | 1AD.12 |
| Other | `HAS_FOREIGN` | Did the company have foreign-currency items? | Policies, foreign currencies |

**Mark all remaining as No.** A button on this panel only. The dialog
names the unanswered flags and asks for confirmation. The server writes
No for those flags only, in one transaction, with the draft `row_version`.
Derived facts are not writable. The audit action is
`disclosures_marked_remaining_no`. A viewer receives 403. Until the POST
succeeds, unanswered flags still block FINAL.

---

## 3. Company details

The trial balance does not know the people or the registered office. The
company row is the durable record. The year end holds facts that change
with the period. The draft holds journals and disclosure answers, not the
letterhead.

### On `companies` (entered once, reused every year)

| Field | Storage | Required for |
| --- | --- | --- |
| Company name | existing `name` | Cover, every page |
| Company number | existing `company_number` | Directors and other information, note N0 |
| Registered office | existing `registered_office` | Directors and other information, note N0 |
| Business address | **new** `business_address` text, nullable, one multi-line field | Directors and other information |
| Date of incorporation | **new** `incorporated_on` date, nullable | Directors and other information |
| Principal activity | **new** `principal_activity` text, nullable. Do not reuse `industry` | Directors' report |
| Functional currency | existing `functional_currency` | Faces and the directors' report profit line |
| Financial year end | existing `financial_year_end` | Not a substitute for this draft's `period_end` |
| Average employees | existing `average_employees` | Employee note when the disclosure says there are employees |
| Secretary | existing `secretary` | Directors and other information, directors' report |
| Directors | existing `directors` JSONB | Directors' report, N0, signatories |
| Advisers | Not in this build | Wait. No column until a later decision. |

`directors` stays JSON. Each object is `{ "name", "appointed_on", "resigned_on" }`.
`appointed_on` and `resigned_on` are dates or null. No new column.
`_directors_list` today stringifies a dict that has no `name`. Phase 2
must stop that: a director without a name is missing, not a JSON blob on
the page.

`CompanyResponse` and `CompanyUpdateRequest` do not expose
`registered_office`, `directors`, `secretary`, `financial_year_end`, or
`average_employees` today, even though the columns exist. The company
form needs those fields on the API. That is a schema change, not a
migration.

### On `findraft_year_ends` (this period)

| Field | Storage | Required for |
| --- | --- | --- |
| Approval date | **new** `approval_date` date, nullable | Approval page, signatories |
| Who signs | **new** `signing_directors` JSONB, nullable, names that must match current company directors | Approval page, cover signature line |

These are not report-setup fields. The Week 11 approval page has to read
them, and the statement engine is not allowed to import `report_setup`.
The page builder receives them as arguments the router already has, the
same way it receives `directors` and `period_end` today.

A new draft version of the same year end keeps the same approval date.
A later year is a different year-end row.

### Fail closed

A missing required fact is a visible blank or the sentence the Week 11
builder already uses ("The directors who served during the year have not
been recorded.", "Approval date has not been recorded."). Nothing is
defaulted and nothing is written by a model. The dashboard adds a check.
The PDF shows the blank. It does not skip the sentence in a way that
looks finished.

### CRO pre-fill (not built)

Three public routes exist. None is wired.

- CRO Open Services (`https://services.cro.ie/overview.aspx`) is a free
  REST API after signup, a signed terms copy emailed to
  `itcro@enterprise.gov.ie`, and an API key. Calls use Basic auth of the
  email and key. The documented company call is
  `GET /cws/company/{number}/c`. That is the only route worth a later
  spike, and only after the payload is checked against the fields above.
  Director appointment dates are not promised by that one call.
- CRO bulk data is a paid licence (€31,000 a year for the daily company
  file; scanned documents are a separate €47,520). Wrong shape for
  looking up one company number.
- `opendata.cro.ie` company records are a daily snapshot under CC BY 4.0,
  with attribution. Useful as a cross-check of what a free file contains.
  It is not a substitute for an authorised live lookup.

Pre-fill, if it is ever approved, writes only into empty fields and never
overwrites a value the practice has saved. It is out of this design's
build.

---

## 4. Cover and directors pages

**Cover.** Composer output, not a new calculator. Company name from
`companies.name`. Statement title from the pack ("Financial statements").
Period from report-setup face dates when saved, otherwise the year-end
period. The trial-balance period stays visible when the face dates differ,
which `ReportSetupForm` already warns about. The DRAFT or Compilation
label comes from report-setup `statement_type`. Compilation never changes
the engine watermark into an audit or a review opinion.

**Directors and other information.** A new page beside the Week 11 pages,
filled only from the company and year-end fields above: registered office,
business address, company number, incorporation date, secretary, directors
with appointed and resigned dates, and advisers when present. Missing
lines stay labelled as not recorded.

**Directors' report, compilation report, approval, audit exemption.**
`build_statutory_pages` stays the writer. Phase 2 passes the approval date
and the signing directors into `_approval`, which today always says the
approval date has not been recorded. It does not gain a second template.
The directors' report keeps using the profit figure the engine already
computed. Audit exemption stays the current fail-closed text: size
eligibility is not a section 335 statement, and no auditor's report is
attached.

**Contents.** A list of sections whose saved toggle is on, in pack order.
It is generated at compose time. It is not stored as a second document.

---

## 5. Review-dashboard checks

These sit next to the existing reconciliation checks. They do not change
traffic colours except where the table says block.

| Code | When | Severity | Blocks FINAL? |
| --- | --- | --- | --- |
| `V-CO-001` | No director name on the company | warning | yes, when directors' report or directors-and-other-information is on |
| `V-CO-002` | Registered office or company number missing | warning | yes, when those sections or notes are on |
| `V-CO-003` | Secretary missing | notice | no |
| `V-CO-004` | Principal activity missing | notice | no |
| `V-CO-005` | Approval date missing | warning | yes, when the approval page is on |
| `V-CO-006` | No signing director, or a name that is not on the company | warning | yes, when the approval page is on |
| `V-SEC-001` | Usually-required section is off | notice | no |
| `V-SEC-002` | Disclosure "yes" for OCI or for an equity change, and the matching statement is off | warning | no |
| `V-SEC-003` | User turned OCI or SOCIE on and the engine says it is not required | notice | no |
| `V-SEC-004` | Engine has not evaluated 1A.9(a) or 1A.9(b) | notice | no |
| `V-SEC-005` | Cash flow or trading statement is on | notice | no. Copy: this pack does not build that statement. |
| `V-DISC-001` | Existing unanswered-disclosure check | unchanged | yes |

Locked sections have no "turned off" check because the API refuses the
write.

---

## 6. Report setup and the PDF today

Checked on `522ef03`. The PDF HTML in `statutory_statements.py` is not
reading `report_setup`.

- Column headers are the literals `Current` and `Prior`.
- Amounts are the exact engine strings, not `display_amount`.
- Face dates are not printed. The directors' report uses `period_end`.
- `statement_type` is not read. The watermark is the engine's DRAFT
  constant.
- Section toggles do not exist, so every built page is included.
  Comprehensive income and changes in equity are not built, so they are
  absent for every company, not because a toggle hid them.

Phase 2 wires display in the composer: rounding via the existing
`display_amount` (a new string, the Decimal untouched), face dates and
headers as labels, statement type as the cover and watermark label, and
the section map as the include list. The JSON API keeps exact
`amount_text` values so the UI can keep `data-stored` exact.

---

## 7. Backend for every entry

Platform-admin gate stays on the product 2 router
(`enforce_product2_production_access`). Inside that gate:

- Reader (`viewer` and above): GET.
- Member (`member`, `admin`, `owner`): POST and PUT that change data.
- A viewer PUT or POST returns 403.
- Cross-org reads stay 404.

Audit actions carry no monetary amounts.

| Entry | Routes | Model | Pack / engine | PDF | Audit | Tests |
| --- | --- | --- | --- | --- | --- | --- |
| Home list | Reuse `GET /year-ends/{id}/draft` and the version list the lock flow already reads. Add `GET /year-ends/{id}/drafts` if the list is not already returned. | None | None | None | None | List is scoped to org. |
| Start new report / Lock | Reuse the existing POSTs. | None | None | None | Existing | Existing lock tests stay green. |
| Report setup | Reuse `GET` and `PUT /year-ends/{id}/report-setup`. | Existing `report_setup` JSON | Engine does not import it | Composer reads it | Existing `report_setup_saved` | Existing figure test plus PDF label test. |
| Sections setup | Same PUT, `sections` map added to the body. | Same JSON. No new column. | Pack `sections` array is the allowed id set. Engine does not import the map. | Composer include list | `report_setup_saved` | 422 on locked off. PDF drops and restores a heading. Figures unchanged. |
| Signatories | `GET` and `PUT /year-ends/{id}/signatories` | New year-end columns | Page builder arguments only | Approval page | `signatories_saved` | Viewer 403. Unknown name 422. Figures unchanged. |
| Events | `GET /year-ends/{id}/events` | Read `audit_logs` | None | None | None | Other org 404. |
| Trial balance | `GET /year-ends/{id}/adopted-trial-balance` read-only rows | None | None | None | None | No POST on this path. |
| Mapping | Reuse sub-line GET and POST | Existing `statutory_line` | Existing resolver | Unchanged | Existing confirm audit if present; add `statutory_sublines_confirmed` if the confirm path is silent | Confirm does not change TB amounts. |
| Adjustments | Reuse POST adjustments | Existing journals | Engine applies journals as it does now | Rebuilt from the journal, not from a toggle | Existing | Golden figures move only when a journal is posted, never when a toggle is saved. |
| Prior year | Reuse first-financial-period and prior-year routes | Existing year-end flags | Existing gate | Existing | Existing | Existing gate tests. |
| Disclosures | Reuse POST one answer. **New** `POST /year-ends/{id}/drafts/{draft_id}/disclosures/mark-remaining-no` with `row_version` and `confirm: true`. | Existing disclosure answers | Existing `ANSWER_FLAGS` | Notes follow answers as they do now | `disclosure_answered` (existing) and `disclosures_marked_remaining_no` | Unanswered is not treated as No until the POST. Derived flags rejected. Viewer 403. |
| Company details | `GET` and `PUT /companies/{id}/statutory-details` | New columns plus existing columns exposed on the schema | `entity_from_company` reads them. No new arithmetic. | N0 and Week 11 pages | `company_statutory_details_saved` | Empty stays empty. Viewer 403. RLS on `companies`. |
| Section panels | Reuse `GET .../statements` | None | Composer filters a copy for PDF. JSON stays complete. | See section 6 | None | `data-stored` exact. |
| Preview | Client only | None | None | None | None | Off-state still in the JSON. |
| Outputs | Reuse PDF GET. Links to existing Product 1 export routes. | None | Composer | PDF follows toggles | Existing export audit | PDF fixture: cover off, then on. |

**Not wired today.** Report-setup display and section toggles do not affect
the downloaded PDF. The design above is the wiring. Until Phase 2 lands,
saving report setup still does not rebuild statements, which is what the
current tests lock in.

---

## 8. Files

**Add**

- `sections` on `findraft/content/frs102-1a-ie/2024.09/pack.json`
- `backend/app/services/statutory_compose.py` — include list, display
  strings, contents page. No sums.
- Company statutory-details schema and routes.
- Signatories schema and routes.
- Mark-remaining-no route.
- Events read route.
- Draft list route only if the current draft GET cannot already list
  versions.
- Frontend: section-setup form, company form, signatories form, disclosure
  groups, home list, preview switch, read-only trial balance, events list.
- Alembic revision after `c9d0e1f2a3`.

**Change**

- `report_setup` schema to carry the optional `sections` map.
- `framework_list()` to copy pack sections instead of the hardcoded
  `_FRS_SECTIONS` tuple. The tuple may remain as a test fixture; the
  served catalogue must come from the pack.
- `StatutoryDraftWorkspace` to render from that catalogue, including
  errors from the dashboard and statements queries (see the defect note
  below).
- `build_statutory_pages` `_approval` to accept an approval date and
  signing names when the router has them.
- PDF render call site to go through the composer.

**Reuse unchanged**

- `WorkspaceSidebar` props.
- `ReportSetupForm` five fields.
- `StatutorySublineReview`.
- Adjustment post and lock.
- `display_amount` and the Decimal statement engine.
- Note selection from disclosure answers.
- Audit-exemption wording.
- Platform-admin gate.

**Migration, in apply order**

1. `b8c9d0e1f2` — `account_mappings.statutory_line`. Already in the repo.
   Sub-line confirm cannot persist without it.
2. `c9d0e1f2a3` — `findraft_year_ends.report_setup` JSONB. Already in the
   repo. Toggles and the five report-setup fields live here. This
   environment did not apply it to production on 3 October 2026. Check
   `alembic current` before assuming it is there.
3. **New**, and not part of Phase 2 step 1. One nullable revision when
   company details are built:
   - `companies.business_address` text
   - `companies.incorporated_on` date
   - `companies.principal_activity` text

   Approval date and signing directors are a later revision, with
   signatories. Advisers are not in either revision. `b8c9d0e1f2` and
   `c9d0e1f2a3` are already applied on production. Step 1 has nothing to
   run.

No new table. Both tables already have row-level security. New columns
are covered by the existing policies. Tests still run as the
non-superuser role and print `current_user`.

Director dates do not need a migration. Exposing existing company columns
on the Pydantic schema does not need a migration.

---

## 9. Tests

- Saving a section toggle, a face date, a header, or a rounding mode does
  not change stored statement amounts, the trial-balance period, the pack
  pin, or the draft `row_version`, and does not call the statement rebuild.
  Extend `test_report_setup_does_not_change_stored_figures_or_rebuild`.
- PDF HTML for the same draft omits a toggled-off heading and contains it
  again after the toggle is turned on. Net assets in the API JSON stay
  the exact string throughout.
- PUT `income`, `sofp`, or `notes` to false returns 422 and leaves the
  saved map unchanged.
- A company with no directors renders the existing not-recorded sentence.
  The response contains no invented name.
- A director object without `name` does not fall back to `str(dict)`.
- Viewer PUT on company details, signatories, report setup, and
  mark-remaining-no returns 403.
- Mark-remaining-no writes No only for flags that were unanswered, writes
  one audit row, and leaves derived flags untouched. A second GET still
  shows those derived facts as derived.
- `GET /year-ends/frameworks` section ids equal the pack file's ids.
  `WorkspaceSidebar.tsx` contains no framework id and no section label
  literal from the pack.
- RLS: as the application role (name printed), org A cannot read org B's
  company advisers or year-end approval date. Expect 404 at the API.
- Golden statement fixtures stay byte-identical when the new columns are
  null and every toggle is at the pack default.

---

## 10. Build order

1. Show dashboard and statements errors on the workspace. Done as Phase 2
   step 1. No migration.
2. Statement of income and retained earnings from the V-RE-001 figures
   (opening retained earnings, profit, dividends, closing retained
   earnings), only when that check passes and share capital and share
   premium are unchanged. This comes before any new 1A.9 evaluator.
3. Company details API, fail-closed pages, dashboard checks `V-CO-*`.
   Migration: `business_address`, `incorporated_on`, `principal_activity`.
4. Pack section declaration, toggle map, locked-off 422, dashboard
   `V-SEC-*`, and the two new disclosure questions.
5. Composer: cover, contents, and the PDF include list, including the five
   report-setup display fields.
6. Sidebar groups, disclosure checklist, mark-remaining-no, signatories,
   events, read-only trial balance, preview.
7. A full statement of changes in equity only when a movement the retained
   earnings roll-forward does not classify is present (share issue, own
   shares, other comprehensive income, or a restatement).

---

## 11. Workspace errors

Phase 2 step 1 shows `dashboardQuery.error` and `statementsQuery.error`
on the draft page. The text is the API `detail` unchanged, including
`Product 1 line '…' on '…' needs a statutory sub-line`. That sentence
links to Sub-line review (`?section=sub-lines`).

## 11a. What was wrong before that step

On the deployed commit `522ef03` the sidebar is the seven working
entries. Statement of changes in equity is not among them, in
`backend/app/services/report_setup.py`. That is true for every draft.

`StatutoryDraftWorkspace` does not render `dashboardQuery.error` or
`statementsQuery.error`. The disclosures panel and the adjustment form
mount only when the dashboard payload is present. The income and SoFP
tables mount only when the statements payload is present. Both of those
calls go through `load_adopted_inputs`, which returns HTTP 400
`needs a statutory sub-line` whenever an adopted account still needs a
sub-line. `GET /year-ends/{id}/draft` does not. The page shell can
therefore load while adjustments, disclosures, and both faces look empty.
That is a shared code path, not evidence that one draft's rows were
corrupted. A live signed-in response for one draft was not available in
this environment (see the investigation note in the pull request).

---

## 12. Open questions

None of the seven questions are still open. They are recorded at the top
of this note.
