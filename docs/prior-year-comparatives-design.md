# Prior-year comparatives — design

Status: **design only**. Do not build until this is approved.

The comparative column is the previous period. Today a member either posts canonical lines to `POST /year-ends/{id}/prior-year` or marks the first financial period. Both set `prior_year_validated`, which opens `V-GATE-001`. There is no undo, no translation from a prior Product 1 trial balance, and no copy from a previous FINAL snapshot. The lines live on `findraft_prior_year_lines` by `year_end_id` and `canonical_line`. They do not store `period_end`.

No LLM. Python `Decimal` stays the only arithmetic. Golden figures stay 455812.00 net assets and 157650.00 profit. Confirming comparatives does not change the current trial balance.

## Page

Workspace section, same chrome as Trial balance. Not a pack section.

| id | label | group | order |
| --- | --- | --- | --- |
| `prior-year` | Prior-year comparatives | Inputs | 6 |

It sits after Adjustments and before Disclosures. Disclosures and Company details move to 7 and 8. Sections setup and the pack rows move down by one, the same way Trial balance moved them.

Route: `/year-ends/{yearEndId}/draft?section=prior-year`.

`V-GATE-001` Fix link becomes that route. The check message becomes: "This draft needs comparative figures. Choose a source on the Prior-year comparatives page, or mark this as the company's first financial period." The engine code `V-GATE-001` and the block stay. Only the words and the link change.

## Sources, in this order

The page lists four sources in this order. The first one that can be used is marked preferred. A source that cannot be used stays on the page with the refusal sentence and has no confirm control.

### 1. Previous Product 1 trial balance

The preferred source when it exists.

Same company. `trial_balances.period_end` is the day before this year end's `period_start`. Status `complete`. Not soft-deleted. Every account is confirmed or ignored, and every account that needs a statutory sub-line has one. Translation uses `carry_confirmed_accounts` and `engine_line_for_confirmed_mapping`, the same path as the adopted file. Amounts for one engine line are summed with `Decimal`.

The page shows those translated lines and asks for confirmation. It does not print them until confirm.

Refuse, and do not write, when:

- no trial balance has that period end: this source is absent, not an error
- the period is not contiguous (the prior period end is not the day before this period starts): "This trial balance ends on {end}. This period starts on {start}. The prior period must end the day before."
- any account is unconfirmed, ignored is not the case, or a sub-line is missing: the existing reconciliation sentence for that account
- a nominal code is duplicated, or a Product 1 line has no single statutory home: the existing refusal sentence

An unmapped or ambiguous file is not replaced by manual entry. The sentence tells the preparer to finish mapping on that trial balance.

**Confirmation snapshots.** `confirm: true` writes the translated totals onto `findraft_prior_year_lines`, sets `prior_year_validated`, and stores the source trial balance id and a sha256 of the translated lines. The printed column is that snapshot. A later change to the Product 1 file, its mappings, or its sub-lines does not move the column. The page then shows: "The prior trial balance has changed since these comparatives were confirmed." A member confirms again to replace the snapshot. The audit row records the replacement. The column is not live.

### 2. First financial period

Today's control, on this page, with an undo.

Plain English next to the control: "Choose this when the company has no earlier accounting period. The accounts will not show a comparative column. You can undo this until the draft is final."

Marking it deletes any prior-year lines, sets `first_financial_period` and `prior_year_validated`, and writes audit `first_financial_period_marked` with the year end id only.

If another year end for this company already exists, the mark is 409: "This draft is marked as the company's first financial period, and another period already ends on {previous end}." The flag is not set. The other year end is not changed.

Undo is `POST /year-ends/{year_end_id}/first-financial-period/undo`. It clears both flags. It does not invent comparative amounts, so `V-GATE-001` blocks again until a source is confirmed. It is 409 when any draft on the year end is final, locked, or frozen: "This statutory draft is final, locked, or frozen. The first-period choice cannot be undone." Audit `first_financial_period_cleared`, year end id only.

### 3. Manual entry by canonical line

Used when this company has no Product 1 trial balance for the previous period. If source 1 exists, manual confirm is 422: "A prior trial balance is available. Confirm that source."

Reuse `POST /year-ends/{id}/prior-year`. The body stays a list of canonical line and amount string. Amounts are `Decimal` to the cent, as today.

Before anything is stored, the entered column must pass three engine checks. A failure is 422, the year end is unchanged, and the response is that check's message:

- the prior column balances (`check_bs_balances` on those lines)
- retained earnings rolls forward (`check_re_rollforward`)
- the fixed-asset note rolls forward (`check_fa_rollforward`) when any fixed-asset line is present

The page shows the same three results before the member confirms. Confirm stores the lines, sets `prior_year_validated`, and sets the source to `manual`.

A second confirm on a draft that is not final replaces the lines. The current "Prior year is already validated" refusal remains for a final, locked, or frozen draft. Replacing lines writes audit `prior_year_replaced` with the year end id and the source kind. No amounts.

### 4. Previous FINAL snapshot

This is the roll-forward. It is offered when the previous year end (same company, `period_end` the day before this `period_start`) has a draft with status `final` and a snapshot.

The copy is that snapshot's current canonical figures, which become this year's comparative column. The previous FINAL row is not read live and is not updated. `confirm: true` writes those figures onto this year's `findraft_prior_year_lines` and stores `comparative_source_year_end_id` and `comparative_source_draft_id`.

That pair is the roll-forward link. It is not a `period_end` foreign key. A trial-balance switch cannot move a FINAL year end, so the link still names the same year end and the same snapshot after a switch of some other draft. The link is not cleared and not pointed at another period.

If a later FINAL snapshot appears on that previous year end, the page shows: "A later final snapshot exists for the previous period. These comparatives stay as confirmed until you confirm again." The column does not move by itself.

When both source 1 and source 4 exist, source 1 stays preferred. Source 4 remains selectable.

## Face dates

`face_dates.prior_start` and `face_dates.prior_end` are display-only, as they are today. The statement engine does not read them. Changing them does not move `V-GATE-001` and does not change a comparative amount.

On confirm of source 1 or source 4, if both prior face dates are empty, they are filled from that source's period start and period end. A first financial period leaves them empty. If either is already set and differs from the source, it is left as set and the page shows: "The printed prior dates differ from the comparative period. Clear them in Report setup if the face should follow the source."

## What the face, the notes, and Word print

The composer already sets `comparative = not first_financial_period` and prints one comparative column on the face and in the notes. Word uses that same composed document. PDF uses it too.

The figures in that column are `prior_from_mapped` of the stored prior-year lines. They are the snapshot from confirm. Print does not re-read the prior Product 1 file and does not re-read the previous FINAL snapshot.

A first financial period prints no comparative column. A later year with confirmed lines prints two columns. A FINAL draft keeps the column that was in its snapshot.

## Routes

| Method | Path | Who | Effect |
| --- | --- | --- | --- |
| GET | `/year-ends/{year_end_id}/prior-year` | viewer and above | The four sources, the preferred one, any refusal sentence, the stored lines, and the stale-source notice. |
| POST | `/year-ends/{year_end_id}/prior-year` | member and above | Manual lines. Existing route, plus the three checks. |
| POST | `/year-ends/{year_end_id}/prior-year/from-trial-balance` | member and above | `confirm: false` returns the translated lines and writes nothing. `confirm: true` snapshots them. |
| POST | `/year-ends/{year_end_id}/prior-year/from-final` | member and above | `confirm: false` names the previous FINAL draft and writes nothing. `confirm: true` copies its current column. |
| POST | `/year-ends/{year_end_id}/first-financial-period` | member and above | Existing mark. |
| POST | `/year-ends/{year_end_id}/first-financial-period/undo` | member and above | Clears the mark. |

A viewer POST is 403, "You don't have permission to access this resource." Another organisation is 404. Final, locked, and frozen are 409 and write nothing. `confirm: false` writes nothing, including no audit row.

## Migration

One revision, for the source record. The lines table already holds the amounts.

`p2q3r4s5t6`. `down_revision` is the Alembic head on main when the migration pull request opens. That head is `m9n0o1p2q3` until a later revision has been merged and applied. Do not stack this revision on `n0o1p2q3r4` or `o1p2q3r4s5` unless that revision is already the head.

All on `findraft_year_ends`, all nullable, no server default, no backfill:

- `comparative_source VARCHAR(32) NULL`, check in `product1_tb`, `first_period`, `manual`, `final_snapshot`
- `comparative_source_trial_balance_id UUID NULL`, foreign key to `trial_balances.id` `ON DELETE SET NULL`
- `comparative_source_year_end_id UUID NULL`, foreign key to `findraft_year_ends.id` `ON DELETE SET NULL`
- `comparative_source_draft_id UUID NULL`
- `comparative_source_sha256 VARCHAR(64) NULL`

Upgrade and downgrade reapply `backend/scripts/findraft_table_privileges.sql`. The executable contains no `GRANT ALL` and no `SELECT`. No new table, so no new policy. The year-end table already grants `SELECT, INSERT, UPDATE, DELETE` to `findraft`.

The migration pull request does not map the columns. The following pull request maps them, and it merges only after `/health` shows `revision_matches` true for `p2q3r4s5t6`.

## Roles and audit

Viewer and above can read. Member and above prepare and confirm. Confirmation is audited.

| Action | Audit action | Stored value |
| --- | --- | --- |
| Snapshot a prior trial balance | `prior_year_confirmed` | year end id, source `product1_tb`, trial balance id |
| Copy a FINAL snapshot | `prior_year_confirmed` | year end id, source `final_snapshot`, previous year end id, draft id |
| Manual confirm or replace | `prior_year_confirmed` or `prior_year_replaced` | year end id, source `manual` |
| Mark first period | `first_financial_period_marked` | year end id |
| Undo first period | `first_financial_period_cleared` | year end id |

No amounts, no account names, and no narration in the audit JSON. Inserts go through `append_audit_log`. Queries filter by `org_id`.

## Least privilege

No `GRANT ALL`. No new table. The migration reapplies the existing privileges script. Cross-organisation access stays 404.

## Tests

- Golden engine tests still report net assets 455812.00 and profit 157650.00. No test changes the golden current column.
- A confirmed prior trial balance makes the comparative column appear on the face, in the notes, and in the Word document, and the current column is unchanged.
- An unmapped account, a missing sub-line, and a non-contiguous period each refuse with the sentence above and leave `prior_year_validated` false.
- After confirm, editing the prior trial balance does not change the stored lines, and the stale notice appears.
- First period undo clears the flags and `V-GATE-001` blocks again. Undo of a final draft is 409.
- Manual entry that fails the balance, the retained-earnings roll-forward, or the fixed-asset roll-forward is 422 and stores nothing.
- A FINAL copy writes the snapshot's current figures and does not modify the FINAL row.
- Face dates that were empty take the source period. Face dates that were already set are not overwritten. The engine source does not read `report_setup`.
- Viewer POST is 403. Another organisation is 404.
- `V-GATE-001` Fix link is `/year-ends/{id}/draft?section=prior-year`.

## Build order

Each pull request is merged on its own, with the required checks green, including `npm run build` when the frontend changes. Golden figures stay unchanged. No LLM.

1. **Page and the gate link.** Section, GET of today's lines and the first-period flag, the new `V-GATE-001` sentence, Fix link to `?section=prior-year`. No migration. The four sources are listed; only the current manual lines and the first-period control work.
2. **Undo.** The undo route, the plain-English sentence, and the 409 for a final draft. No migration.
3. **Manual checks.** Balance, retained-earnings roll-forward, and fixed-asset roll-forward refuse confirm. No migration.
4. **Migration `p2q3r4s5t6` only.** The five columns. The model does not map them. After merge, the first line of the report is `MIGRATION REQUIRED: p2q3r4s5t6. Production is failing until you apply it.` Do not merge pull request 5 until `/health` matches.
5. **Prior trial balance.** Map the columns. Translate, preview, snapshot, stale notice.
6. **FINAL roll-forward.** Copy the previous snapshot. The link is the year end id and the draft id.

Pull requests 1 to 3 do not wait on a migration. Pull request 5 waits on `p2q3r4s5t6`. Pull request 6 waits on 5.
