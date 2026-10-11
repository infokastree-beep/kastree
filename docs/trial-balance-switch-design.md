# Correcting a statutory period — design

Status: **design only**. Do not build until this is approved.

The statutory period is the Product 1 trial balance's period start and period end. Report setup face dates only relabel the printed face. Today the only way to fix a wrong period is to delete that trial balance and upload it again. This design adds a read-only Inputs page and a confirmed re-adopt. It does not add a date field on the year end.

No LLM. Python `Decimal` stays the only arithmetic. Golden figures stay 455812.00 net assets and 157650.00 profit, because the engine and the golden file do not change. Adopting a different file changes that draft's figures because the source rows changed.

## What is true today

`continue_from_trial_balance` copies `period_start` and `period_end` from the trial balance onto a new `findraft_year_ends` row, pins pack `frs102-1a-ie` `2024.09`, and adopts that trial balance. A later continuation for the same `period_end` finds the existing year end and does not change its dates.

`adopt_confirmed_trial_balance` refuses unless `trial_balances.period_end` equals `findraft_year_ends.period_end`. `GET /year-ends/{id}/adoptable-trial-balances` lists only complete trial balances with that same period end. An active trial balance is unique per company and period end (`trial_balances_company_id_period_end_active_key`). A year end is unique per organisation, company, and period end (`findraft_year_ends_period_key`).

Face dates live in `findraft_year_ends.report_setup` and are documented as display settings the statement engine does not use to select a trial balance. The composer prints a face date when one is set, and otherwise prints the year-end period.

Mappings and statutory sub-lines live on `account_mappings`, unique per company, source code, and source name. They are not copied onto the draft. Adjustment journals, disclosure answers, and `note_library` live on `findraft_draft_versions`. A frozen draft keeps `frozen_inputs`. A FINAL draft keeps `snapshot` and is not recomputed. Printed period dates are still read from the year end when a statement is built, including for a frozen draft's live rebuild path. That is why a period change is refused once any draft on the year end is frozen, locked, or final.

The upload form labels the two fields "Period start" and "Period end" and does not say they become the statutory period. The API still accepts a missing period start. Continuation already refuses a trial balance with no period start. Pack `2024.09` has `effective_from` `2026-01-01`. `pin_pack_version` refuses an earlier start at continuation, not at upload.

The stored file path is `file://…/{uuid}.{ext}`. The original upload name is not on `trial_balances`.

## 1. Inputs > Trial balance

Add a workspace section in `backend/app/services/report_setup.py` `_WORKSPACE_BEFORE`, and the same row in the dev statutory sidebar fixture:

| id | label | group | order |
| --- | --- | --- | --- |
| `trial-balance` | Trial balance | Inputs | 3 |

Shift Mapping, Adjustments, Disclosures, and Company details to orders 4–7. Pack `pack.json` sections are the printed pages. This row is workspace chrome, not a pack section.

Route in the workspace: `/year-ends/{yearEndId}/draft?section=trial-balance`.

The page shows the adopted trial balance and does not edit it:

- Period start and period end, read from the trial balance (the same dates stored on the year end after a successful adopt).
- Source file name. Until the filename column exists, and for every row where it is null: "File name was not recorded."
- Upload date: `trial_balances.created_at`.
- Account count: rows carried from `parsed_data` through the confirmed mappings, the same count `list_adoptable_trial_balances` already computes.
- Currency code.
- Link "Open in Statements" to `/dashboard/{trialBalanceId}/statements?tab=Statutory`, the same destination the workspace header uses today.
- One sentence: "Report setup face dates only change the words printed on the face. They do not change this period."

When `adopted_trial_balance_id` is null (the adopted row was soft-deleted; the foreign key sets the column to null): "No trial balance is selected." The candidate list is the way to select the replacement. This page does not delete a trial balance. Deleting stays on the Product 1 client.

### Use a different trial balance

The action lists the company's other active, `complete` trial balances, including other period ends. The adopted id is omitted. A soft-deleted row is omitted. Each row shows period start, period end, file name, upload date, account count, and currency.

A row is selectable only when every check below passes. A row that fails is still listed, with the refusal sentence, and has no adopt control. The existing `POST /year-ends/{id}/adopt-trial-balance` stays as it is: same period end, no date change, no new audit shape. The correction uses a new route so that behaviour does not widen by accident.

`POST /year-ends/{year_end_id}/trial-balance/adopt`

Body: `trial_balance_id`, `row_version` of the active draft, `confirm`.

`confirm: false` returns 422 and writes nothing. The body lists, with counts and no amounts:

- the period that will be stored
- how many of this draft's adjustment journals will be kept, and how many of those journals name an account that is not on the new trial balance
- how many disclosure answers will be kept
- whether a note library is stored
- the draft id and version number, which will not change

`confirm: true` with the current `row_version` performs the switch in one transaction. A stale `row_version` is 409 and writes nothing.

### What the switch does to existing work

The year end stays the same row. `adopted_trial_balance_id`, `period_start`, and `period_end` are updated from the chosen trial balance. The pack pin does not change.

The active draft stays the same row, the same `version_number`, and status `draft`. `row_version` increments by 1. `mappings_sha256` is refreshed from the live mapping of the new file. `note_library` is not cleared.

Mappings and sub-lines are not deleted and not copied. They stay on `account_mappings`. An account that is on the new file with the same source code and source name keeps its canonical line and statutory sub-line. An account that was only on the old file stays mapped on the company and is not in this draft. The new file must already be `complete`, so every account it contains has a confirmed mapping or is ignored. A file that still needs a sub-line is not selectable; the row says which account needs a statutory sub-line, using the existing refusal text.

Adjustment journals and their lines stay on this draft. A journal whose nominal code is not on the new file still posts, because adjustment lines store their own canonical line and are appended to the trial balance. The confirmation names that count so the preparer can delete the journal on Adjustments afterwards. The switch does not delete journals and does not re-map them.

Disclosure answers stay on this draft. Stored Yes and No are not rewritten. Applicability is recomputed from the new balances the next time the dashboard is built, by the existing `V-DISC-001` rule.

Prior-year comparative lines and the fixed-asset register stay on the year end. When the period dates change, the page shows: "Comparative figures and the fixed-asset note were entered for the previous period. Review them on Prior-year comparatives, or mark the first financial period if that is still right." Those rows are not deleted. `first_financial_period` is not changed by the switch.

Face dates, column headers, rounding, and section switches in `report_setup` are not changed. If `face_dates.current_start` or `face_dates.current_end` is set and differs from the trial balance, the page shows: "The printed face dates differ from the trial balance period. Clear them in Report setup if the face should follow the trial balance."

Figures on this draft follow the new file. The golden file is not switched by any test. Engine tests stay on 455812.00 and 157650.00.

## 2. The period is not edited on its own

Agreed: the period cannot be edited without changing the trial balance. Dates must follow the trial balance.

A date field on the year end would print one period over another period's rows. Face dates already exist for a printed label and must stay labels. The year end's period end is the row's identity (`findraft_year_ends_period_key`). The trial balance's period end is the file's identity. The pack effective date is defined on the accounting period's start, which is the trial balance's start.

There is no exception for a missing period start. A trial balance with a null start is not a candidate. The correction is to upload a file that has both dates.

### Upload form

Under Period start and Period end, on the trial-balance upload (the general-ledger upload keeps its own period control):

"These dates are the accounting period. Statutory accounts use them as the period. They cannot be edited later. To correct them, upload another trial balance and adopt it from Inputs > Trial balance."

When the start is before 1 January 2026, an inline warning, and the upload still proceeds, because Product 1 management accounts may use that file:

"This period starts before 1 January 2026. The Irish statutory pack cannot use it. Management accounts can."

When the span is longer than 18 months, a warning, and the upload still proceeds:

"This period is longer than 18 months. Statutory accounts will use these dates."

Period end before period start stays the existing error and blocks the upload.

The upload API starts requiring `period_start` on new uploads (422, "Enter a period start and period end."). The form already requires it. Rows that already have a null start are left as they are. Continuation and the new adopt both keep refusing a null start.

## 3. Rules

All of these are decided before any row is updated. A failure leaves the year end, the draft, journals, disclosures, and the note library untouched.

**Not after FINAL.** If any draft on this year end has status `final` or `locked`, or `is_frozen` is true, the switch is 409: "This statutory draft is final, locked, or frozen. The period cannot be changed." A frozen or final draft still takes its printed period from the year end, so changing the year end would relabel a report whose figures were already captured. Opening another period is `continue_from_trial_balance`, which creates or finds the year end for that period end. It does not rewrite this one.

The active draft must be status `draft`, not frozen, and the latest version number. `row_version` must match.

**Pack effective date.** The year end keeps its pinned pack. The chosen trial balance's `period_start` must be on or after that pack's `effective_from`. For `frs102-1a-ie` `2024.09` that date is 1 January 2026. Refusal, 422:

"This pack applies to periods beginning on or after 1 January 2026. This trial balance starts on {date}."

The same sentence is the upload warning, with the management-accounts clause only on the upload form. The switch does not re-pin and does not call `pin_pack_version` to write a new pack id.

**Contiguity.** Other year ends of the same company, excluding this one:

- If another year end already has this `period_end`, 409: "A statutory draft already exists for the period ending {period_end}. Open that draft." Do not merge the two year ends.
- If any other year end's span overlaps `[period_start, period_end]`, 409: "This period overlaps the statutory draft that ends on {other period_end}." A year end with a null `period_start` overlaps only when its `period_end` falls inside the new span.
- Previous period: the other year end with the greatest `period_end` strictly before the new `period_end`. If it exists, the new `period_start` must be the day after that `period_end`. Otherwise 409: "This trial balance starts on {start}. The previous period ended on {previous end}. The next period must start on {day after}."
- Following period: the other year end with the least `period_end` strictly after the new `period_end`. If it has a `period_start`, that start must be the day after the new `period_end`. Otherwise the same shape of 409, naming the following period.
- If this year end has `first_financial_period` and a previous year end exists, 409: "This draft is marked as the company's first financial period, and another period already ends on {previous end}." The switch does not clear the flag. Clear the flag on the existing first-period control, then adopt.
- If there is no other year end, the switch is allowed. Missing comparatives stay the existing `V-GATE-001` check. They do not block the adopt.

**Currency.** If the trial balance's currency is set and it is not the company's functional currency, 422: "This trial balance is in {code}. The company reports in {company code}. Amounts are not converted." A null currency on an old row does not refuse.

**Same file.** Adopting the id that is already adopted, with the same dates, is 422: "This trial balance is already selected." No audit row.

**Audit.** One `audit_logs` row, action `trial_balance_readopted`, entity type `year_end`, entity id the year end. `old_value` and `new_value` are `{adopted_trial_balance_id, period_start, period_end}` plus, on `new_value` only, `draft_id`. No amounts, no account names, no file name.

**Roles.** `GET` uses the existing reader dependency (viewer and above). `POST` uses `require_member_work` (owner, admin, member). A viewer POST is 403, "You don't have permission to access this resource." Another organisation's year end is 404.

## Routes

| Method | Path | Who | Effect |
| --- | --- | --- | --- |
| GET | `/year-ends/{year_end_id}/trial-balance` | viewer and above | Adopted trial balance, or a null adopted id. Includes `can_switch` and the refusal sentence when switching is closed. |
| GET | `/year-ends/{year_end_id}/trial-balance/candidates` | viewer and above | Other complete trial balances and, for each, either `ready` or the refusal sentence. |
| POST | `/year-ends/{year_end_id}/trial-balance/adopt` | member and above | `confirm: false` previews. `confirm: true` switches. |

Existing routes kept unchanged:

- `GET /year-ends/{year_end_id}/adoptable-trial-balances`
- `POST /year-ends/{year_end_id}/adopt-trial-balance`
- `POST` continuation from a Product 1 trial balance

## Migration

One revision, and only for the file name. The switch itself needs no new column.

`n0o1p2q3r4`, `down_revision` `m9n0o1p2q3`.

`trial_balances.original_filename VARCHAR(255) NULL`. No server default. No backfill. No check constraint. Existing rows stay null. Upgrade and downgrade reapply `backend/scripts/findraft_table_privileges.sql`. The executable contains no `GRANT ALL` and no `SELECT` of the column. `trial_balances` already grants `SELECT, INSERT, UPDATE, DELETE` to `findraft`. A new column inherits that table grant. No new table, so no new policy and no new grant.

The migration pull request does not map the column on the SQLAlchemy model. Mapping it would make every trial-balance load select the column and fail production until the migration is applied. The following pull request maps it, and it merges only after production `/health` shows `revision_matches` true for `n0o1p2q3r4`.

Upload writes `safe_filename` of the original name into the column. The page shows that name. A null stays "File name was not recorded."

## Tests

- Upload helper text contains the accounting-period sentence. A start before 2026-01-01 warns and still uploads. A missing `period_start` on the API is 422. An existing null start is unchanged.
- Migration source has no `GRANT ALL` and no `SELECT`. Model mapping is absent in that pull request and present in the reader pull request.
- Read-only page: period, upload date, account count, statements link, null file name copy. No adopted id shows the empty state. `test_report_setup.py` today expects the Inputs labels to start Mapping, Adjustments, Disclosures, Company details. That assertion gains Trial balance in front of Mapping.
- `confirm: false` writes no audit row and does not change `adopted_trial_balance_id` or the dates.
- Same-period replacement (old row soft-deleted, new complete row, same period end) keeps the draft id, version number, disclosure answers, adjustment journals, and note library, and updates `adopted_trial_balance_id`.
- A different period updates `period_start` and `period_end` and keeps the same draft id. Mappings and sub-lines for a shared code and name are still the ones on `account_mappings`.
- An adjustment whose nominal code is absent from the new file is counted in the preview and is still stored after confirm.
- Pack start of 2025-12-31 is 422 with the 1 January 2026 sentence, and the year end is unchanged.
- Overlap, a non-contiguous previous period, a non-contiguous following period, and first-financial-period plus a previous year end are each 409, and the year end is unchanged.
- A colliding period end names the other draft and does not merge.
- A currency mismatch is 422 and does not convert.
- Viewer POST is 403. Another organisation is 404. `final`, `locked`, and `frozen` are 409. Stale `row_version` is 409.
- Face dates in `report_setup` are unchanged by the switch.
- Golden engine tests still report net assets 455812.00 and profit 157650.00. No test switches the golden file.

## Least privilege

No `GRANT ALL`. No new table. The filename migration reapplies the existing privileges script and does not grant a wider set. Audit inserts go through `append_audit_log`. Application queries filter by `org_id`. Cross-organisation access stays 404.

## Build order

Each pull request is merged on its own, with the required checks green, including `npm run build` when the frontend changes. Golden figures stay unchanged. No LLM.

1. **Upload wording and a required period start.** Frontend copy and warnings. API 422 when a new upload omits `period_start`. No migration. No adopt change.
2. **Migration `n0o1p2q3r4` only.** Nullable `original_filename`. The model does not map it. After merge, the first line of the report is `MIGRATION REQUIRED: n0o1p2q3r4. Production is failing until you apply it.` Do not merge pull request 3 until `/health` shows `revision_matches` true.
3. **Store and show the file name.** Map the column. Upload writes it. No switch yet.
4. **Read-only Trial balance page.** Section, GET, empty state, statements link, face-date notice. No POST.
5. **Re-adopt.** Candidates, preview, confirm, period update, contiguity, pack date, currency, audit, role and status refusals. No migration.

Pull requests 1 and 2 can be reviewed in that order. Pull request 3 waits on the migration. Pull requests 4 and 5 wait on 3 so the page can show the name.
