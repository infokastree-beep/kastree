# Notes library, review dashboard, and disclosures

**Status: design only. Not built.**

This note does not add a migration, a column, or a reader. It does not read `companies.country_of_incorporation`. The JSONB column below is a later revision, after `l8m9n0o1p2` is confirmed on the production database. Golden net assets and profit stay `455812.00` and `157650.00`. No model call.

The Irish pack already decides which notes print. `select_notes` in `findraft/engine/notes.py` keeps a template when `includeWhen` is `always`, when the predicate is true, or when the predicate still needs an unanswered disclosure. An unanswered fact is never stored as No, and `V-DISC-001` still blocks FINAL. Policy paragraphs in `findraft/content/frs102-1a-ie/2024.09/policies.py` use the same idea through `appliesWhen`. The statement engine fills every amount. The composer prints the notes the engine returned. The Notes sidebar entry is the locked pack section `notes`.

## Library

The library lives on the existing Notes section (`?section=notes`). It is a list of the pack's own blocks. It is not a second note writer.

One row per pack note `N0`–`N9`, in the order the pack already prints. Under Accounting policies (`N1_POLICIES`), one row per policy id in `POLICIES`. Under Commitments (`N9_COMMITMENTS`), one row per entry in that note's `blocks` map (`capital_commitments`, `pension_commitments`, `guarantee_particulars`, `charge_particulars`, `subsequent_events`). Each of those block rows is tied to the checklist item whose `includeWhen` names the same fact (`pension_commitments` is checklist `1AD.32`, flag `PENSION_COMMITMENT`).

The preparer can do two things, and only these two:

1. Omit a narrative block the engine included because a disclosure answer was Yes, by marking it immaterial.
2. Force-include a narrative block the engine left out because that answer was No. Pensions is the example: `pension_commitments` when `PENSION_COMMITMENT` is No and the rest of `N9_COMMITMENTS` did not bring the note in.

Omitting or adding a block does not change a figure, a disclosure answer, a face line, or the pack wording.

### Reason on every row

Every row shows one plain-English sentence. The sentence names the trial-balance line or the disclosure question. It does not show a flag id, a code, or an amount.

| Reason | Sentence | Control |
| --- | --- | --- |
| Always | "This note is always included." | None. The row stays on. |
| Trial balance | "Included because Tangible fixed assets has a balance." The line name comes from the pack reason label for that derived fact. | None. The row stays on. The face figure and its note table stay together. |
| Disclosure yes | "Included because the answer to “Are there retirement-benefit commitments?” is Yes." The question is the pack `question` field. | Omit as immaterial, or put it back. |
| Unanswered | "Waiting for an answer to “Are there retirement-benefit commitments?”." | None. The row stays in, marked pending. `V-DISC-001` still blocks FINAL. |
| Disclosure no | "Left out because the answer to “Are there retirement-benefit commitments?” is No." | Add this block, or leave it out. |
| Omitted as immaterial | "Omitted as immaterial. The answer to “…” is still Yes." | Put it back. The dashboard lists it as omitted. |
| Added by preparer | "Added by the preparer. The answer to “…” is No." | Remove the addition. The dashboard lists it as "added by preparer". |

`N0_ENTITY` and the compliance and basis paragraphs in `N1_POLICIES` are Always. `TAXATION` and `RELATED_PARTIES` are Always. A fixed-asset movement table, or any other note table filled from the trial balance, is Trial balance while the derived balance is not zero. Hiding that table while the face still shows the amount is not an immateriality choice. A zero balance does not become a block the preparer can add.

While any flag in a note's `includeWhen` is unanswered, `select_notes` already includes that note and the commitments note prints the single pending line. Child rows on that note show Unanswered and have no add or omit control.

### Force-include and the blocking rule

Force-include applies only when the engine left the block out. `select_notes` already includes an unanswered note, so an unanswered block is not something the preparer can add. The POST returns 422 and writes nothing.

Force-include leaves the disclosure answer as it is.

- The stored answer stays No. The POST does not write Yes. `V-DISC-001` does not reopen for that flag, because the flag is answered. The row reads "Added by the preparer" and the sentence says the answer is No.
- Answering Yes later makes the engine include the block. The stored addition is then unused and is not shown as a second reason. The same rule already applies to an omission when the answer later becomes No.
- Clearing the answer back to unanswered removes the row from the database, as the existing single-answer route does. The note returns to pending. `V-DISC-001` blocks FINAL again. The stored addition is unused while the engine includes the note. It takes effect again only if the answer is later No and the addition is still stored.
- "Mark all remaining as No" writes No for unanswered flags only. It does not create an addition. A note that was pending then drops out. The preparer can force-include a block after that, as a separate action. That later addition still leaves the answer as No.

Adding `pension_commitments` prints parent `N9_COMMITMENTS` with that block's pack sentence only. A sibling whose own flag is No stays out unless that sibling is also added. A sibling the engine included stays in. The printed sentence is the pack block (`1AD.32 — retirement benefit commitments incl. assumptions`, with the existing placeholder while particulars are blank). There is no free-text note.

The omit control writes one fact: this block id was omitted as immaterial on this draft. The add control writes one fact: this block id was added by the preparer. Neither edits `bodyTemplate`, a policy `body`, a checklist question, or an amount. Putting the block back, or removing the addition, deletes that fact.

Wording stays the pack sentence. The comment in `policies.py` that an LLM may adapt a policy is not this design.

## Where it is stored

On the draft, not on the company and not in `report_setup`. Two drafts of one year end can omit or add different blocks. `report_setup` stays the presentation already saved there. The Notes section stays locked on.

One nullable JSONB column on `findraft_draft_versions`, name `note_library`, no server default. Existing rows stay NULL. NULL means the preparer has neither omitted nor added a block. A non-NULL value is an object with two lists of pack block ids:

```json
{"omitted": ["REVENUE"], "added": ["pension_commitments"]}
```

A block id is a note code, a policy id, or a commitments block id. The same id is never in both lists. The service rejects any other shape.

The migration is revision `m9n0o1p2q3`, `down_revision` `l8m9n0o1p2`. It is not part of this change. Upgrade adds the column and then runs `backend/scripts/findraft_table_privileges.sql`. Downgrade drops the column and runs that script again. The migration does not contain `GRANT ALL`. It does not alter `companies`.

A locked draft keeps the object. A new version copies it the same way disclosure answers are copied. A FINAL snapshot copies it next to the composed HTML. A later change to the live draft does not rewrite the stored file. `final_adopted_snapshot` keeps serving that copy.

## What the print does

`select_notes` and the policy `appliesWhen` checks stay the authority for the default set. Block rows inside `N9_COMMITMENTS` then follow that block's own checklist predicate, which replaces filling every particular whenever the parent note is in.

After that selection, the composer:

- drops a block whose id is in `omitted` and whose reason is still Disclosure yes;
- prints a block whose id is in `added` and whose reason is still Disclosure no.

A block the engine did not select is not printed merely because an old omission names it. An added block the engine now includes is not printed twice. Amounts inside a block that remains are the engine amounts, including display rounding already applied by the composer. The JSON statement payload keeps the engine notes in full and adds both lists, so the workspace can show a dropped block as omitted and an added block as added by the preparer.

PDF, Word, and the section preview use the composed document. They do not grow a second renderer.

`V-NOTE-001`, severity NOTICE, passed false, when `omitted` is non-empty. The message names the titles. `V-NOTE-002`, severity NOTICE, passed false, when `added` is non-empty. The message names the titles and says they were added by the preparer. Neither code blocks FINAL. `blocks_final` does not gain either code. `V-DISC-001` is unchanged: the engine message stays `Unanswered disclosure questions: ` plus the sorted flag list, because `_unanswered` reads that prefix. The review screen does not print that message.

## Review dashboard

The review dashboard stays `?section=review` and `statutory-review-dashboard`. Failed checks are grouped. A group with no failed check is omitted. Passed checks stay off the list. Each failed row has a Fix link to the page that can clear it.

| Group | Checks | Fix |
| --- | --- | --- |
| Company details | `V-CO-001` directors, `V-CO-002` office and number, `V-CO-003` secretary, `V-CO-004` principal activity, `V-CO-005` approval date, `V-CO-006` signing director, `V-CO-007` currency, `V-CO-008` country missing, `V-CO-009` country other than Ireland | `/year-ends/{id}/draft?section=company-details`. The `V-CO-007` row keeps the existing Confirm currency button. |
| Disclosures | `V-DISC-001` | `/year-ends/{id}/draft?section=disclosures`. The row reads "40 disclosure questions are unanswered." using `unanswered_count`. It does not print the flag list. |
| Disclosures | `V-NOTE-001`, `V-NOTE-002` | `/year-ends/{id}/draft?section=notes&note={code}` when one note is named. `/year-ends/{id}/draft?section=notes` when several are named. |
| Comparatives | `V-GATE-001` | `/year-ends/{id}/draft?section=review#statutory-first-period-gate`. That control already exists on the draft page. There is no comparatives section. |
| Comparatives | `V-CMP-001`, `V-CMP-002` | `/year-ends/{id}/draft?section=sofp`. Comparatives are on the face. |
| Sections | `V-SEC-005`, `V-SEC-006` | `/year-ends/{id}/draft?section=sections-setup`. |
| Setup | `V-SEC-007` | `/year-ends/{id}/draft?section=report-setup`. |
| Figures | `V-MAP-001` | `/year-ends/{id}/draft?section=sub-lines`. |
| Figures | `V-TB-001`, `V-BS-001`, `V-BANK-001` | `/year-ends/{id}/draft?section=sofp`. |
| Figures | `V-RE-001` | `/year-ends/{id}/draft?section=income`. |
| Figures | `V-FA-001` | `/year-ends/{id}/draft?section=notes&note=N2_FA`. |

Figures is a sixth group so a red engine failure still has a Fix link. Those rows keep the engine message they already have. They do not gain a new amount.

The standing wording notice is shown once on this view, from `StandingWordingNotice` `place="workspace-header"`. The copy inside the review card (`place="review-dashboard"`) comes out. The copy on the outputs block (`place="downloads"`) stays; it sits with the downloads, not in the review card. The dev preview at `frontend/app/dev/statutory-workspace/page.tsx` drops the same card copy.

Finalise stays a control for owner and admin. When the button is disabled, the sentence beside it is "3 checks must be fixed" (or "1 check must be fixed"). The count is the number of failed checks that stop finalise: severity `CRITICAL` or `BLOCKED`, plus any failed code in `blocks_final` (`V-CO-001`, `V-CO-002`, `V-CO-005`, `V-CO-006`, `V-CO-008`, `V-CO-009`). Notices that do not stop finalise are outside the count: `V-CO-003`, `V-CO-004`, `V-CO-007`, `V-SEC-005`, `V-SEC-006`, `V-SEC-007`, `V-NOTE-001`, `V-NOTE-002`. When the button is disabled and that count is zero, the existing "Not ready to finalise." line remains. When finalise is allowed, the button stays enabled and the count sentence is absent.

## Disclosure questions

The disclosures section stays `?section=disclosures`. Questions are the preparer flags in `ANSWER_FLAGS`. Derived facts are not questions.

Questions are grouped by the checklist `note` field (`N9_COMMITMENTS`, `N1_POLICIES`, and the other note codes). Flags with no single checklist row sit in Other. Group labels and the question sentences are the ones already written in `docs/statutory-set-of-accounts.md` (the disclosures checklist table). Where that table has no row, the sentence is the checklist `topic`.

Each group header shows how many questions in the group are answered and how many are unanswered, and a link to the note when the group has a note code: `/year-ends/{id}/draft?section=notes&note={code}`. Answered rows show Yes or No and still use the existing single-answer buttons. Unanswered rows show the question and Yes / No. The screen does not title-case the flag id.

**Mark all remaining as No.** One button on this panel. The dialog names the unanswered questions in the pack wording and asks for confirmation. Until the POST succeeds, those questions stay unanswered and still block FINAL. The server writes No for the flags that are unanswered at the start of the transaction, and for no others. Derived flags are rejected. A flag that is already Yes or No is left as it is. An empty unanswered set returns 422 and writes nothing. One audit row. Viewer receives 403.

## Routes

All of these sit on the year-end routes that already require Product 2 access. No new route outside `/year-ends`. No change to company create or company update.

| Method and path | Who | Body | Result |
| --- | --- | --- | --- |
| `GET /year-ends/{id}/drafts/{draft_id}/dashboard` | Viewer and above. Existing route. | — | Existing checks, plus `unanswered_count` and, on each check, `area` and `fix` (`section`, optional `note`, optional `anchor`). `can_finalise` uses the same rule as today. `V-NOTE-001` and `V-NOTE-002` do not flip it. |
| `GET /year-ends/{id}/drafts/{draft_id}/notes` | Viewer and above. | — | Library rows: block id, title, reason, sentence, and whether omit, restore, add, or remove is allowed. Does not create a row. |
| `POST /year-ends/{id}/drafts/{draft_id}/notes/library` | Member, admin, owner. | `row_version`, `block_id`, `action` of `omit`, `restore`, `add`, or `remove`. | Updates `note_library` and bumps `row_version`. |
| `POST /year-ends/{id}/drafts/{draft_id}/disclosures` | Member, admin, owner. Existing route. | Existing single answer. | Unchanged. Still the only way to set one flag to Yes, No, or unanswered. |
| `POST /year-ends/{id}/drafts/{draft_id}/disclosures/mark-remaining-no` | Member, admin, owner. | `row_version`, `confirm: true`. | Writes No for currently unanswered `ANSWER_FLAGS` only. |
| `POST /year-ends/{id}/drafts/{draft_id}/finalise` | Owner, admin. Existing route. | Unchanged. | Unchanged. |

The library POST returns 422, and writes nothing, when the id is unknown, the block is Always, the block is Trial balance, the block is unanswered, the action is `omit` on a block the engine did not include, or the action is `add` on a block the engine already included. Viewer receives 403. A FINAL draft is refused with the existing immutability rule (409). A locked draft is refused the same way other draft writes are refused.

Cross-org access stays 404.

## Pack

Pack `frs102-1a-ie` `2024.09` only.

- `disclosure-checklist.json`: each item gains `question` (the plain-English sentence) and `flag` (the `ANSWER_FLAGS` name). `includeWhen`, `topic`, statute refs, and evidence stay as they are.
- New `reason-labels.json`: one label per derived fact, with no amount. `FIXED_ASSETS_NBV` is "Tangible fixed assets", `DEBTORS` is "Debtors", `CREDITORS` is "Creditors", `STOCKS` is "Stocks", `LOANS` and `HAS_BORROWINGS` are "Borrowings", `HAS_LEASES` is "Leases", `INTANGIBLE_ASSETS` is "Intangible assets", `REVENUE` is "Revenue", `DIRECTOR_LOANS` is "Director loans", `DIVIDENDS_PAID` is "Dividends".

Note bodies, `includeWhen`, size thresholds, and Note 1's incorporation sentence stay as they are.

## Frontend files

- `frontend/components/statutory/StatutoryDraftWorkspace.tsx` — render the grouped checks; remove the review-card wording notice; pass the blocking count into Finalise.
- `frontend/components/statutory/FinaliseDraft.tsx` — `blockingCount`. The sentence sits beside the disabled button.
- `frontend/components/statutory/DisclosureGroups.tsx` — groups, counts, note link, mark-all-no dialog.
- `frontend/components/statutory/NotesLibrary.tsx` — rows, sentences, omit, restore, add, remove.
- `frontend/lib/dashboard-groups.ts` and `frontend/lib/dashboard-groups.test.ts` — area, Fix target, blocking count, and the disclosure count sentence.
- `frontend/lib/disclosure-groups.ts` and `frontend/lib/disclosure-groups.test.ts` — group by note, pack question, answered and unanswered counts.
- `frontend/lib/note-library.ts` and `frontend/lib/note-library.test.ts` — reason sentence from a line label or a question. No amount in the sentence.
- `frontend/app/dev/statutory-workspace/page.tsx` — same card-notice removal and the same finalise sentence.

The workspace Dashboard type gains `unanswered_count` and the check `area` / `fix` fields.

## Roles

Inside the existing Product 2 gate:

| Action | Role |
| --- | --- |
| Read the dashboard, the library, and the disclosure groups | Viewer, member, admin, owner |
| Omit, restore, add, remove, answer one disclosure, mark remaining as No | Member, admin, owner (`require_member_work`) |
| Finalise | Owner, admin (`require_client_admin`) |

A viewer POST returns 403. The finalise reason is part of the button owner and admin already see.

## Audit

No monetary amount in `old_value` or `new_value`.

| Action | When | Payload |
| --- | --- | --- |
| `note_block_omitted` | Omit | Block id |
| `note_block_restored` | Restore | Block id |
| `note_block_added` | Force-include | Block id |
| `note_block_add_removed` | Remove an addition | Block id |
| `disclosures_marked_remaining_no` | Mark all remaining as No | The flag names written in that transaction, and no others |
| `disclosure_answered` | The existing single-answer POST | Flag name and `yes`, `no`, or `unanswered` |

`disclosure_answered` is new. The single-answer route writes no audit row today. This design adds that one row on the same route. It does not change the stored answer.

## Least privilege

No new table. `findraft_draft_versions` already has `SELECT`, `INSERT`, `UPDATE`, and `DELETE` for the login `findraft`. The new column is covered by that table grant. `findraft_disclosure_answers` already has the same four privileges and is where mark-remaining-no writes. No new sequence.

Revision `m9n0o1p2q3` reapplies `backend/scripts/findraft_table_privileges.sql` on upgrade and downgrade. That script revokes every table privilege from `findraft` and grants back `SELECT`, `INSERT`, `UPDATE`, and `DELETE` on this table, then revokes `TRUNCATE`, `REFERENCES`, and `TRIGGER`. The migration file itself does not grant `ALL`.

## Tests, when it is built

- NULL `note_library` leaves the composed notes equal to today's engine set, and the golden net assets and profit stay `455812.00` and `157650.00`.
- Omitting a Disclosure-yes policy removes that paragraph from the composed HTML and leaves the engine amount on the face unchanged.
- Force-including `pension_commitments` while the answer is No prints the pack block, leaves the answer No, and the dashboard row says "Added by the preparer".
- Force-include while the controlling flag is unanswered returns 422, writes nothing, and `V-DISC-001` still blocks FINAL.
- Force-include when the answer is No does not reopen `V-DISC-001` for that flag.
- Answering Yes after an addition leaves one copy of the block, and the stored addition is unused.
- POST of `N0_ENTITY`, of a non-zero fixed-asset note, of an unknown id, of an unanswered omit, and of an add on a block the engine already included returns 422 and writes nothing.
- `V-NOTE-001` and `V-NOTE-002` do not change `can_finalise` on their own.
- Mark-remaining-no writes No only for flags that were unanswered, writes one `disclosures_marked_remaining_no` row, leaves derived flags untouched, and leaves an already answered flag untouched. Before the POST returns, the client still treats those flags as unanswered.
- The review dashboard does not render the raw `V-DISC-001` flag list. The disclosures group shows the count and a Fix link to `?section=disclosures`.
- The review card does not render `place="review-dashboard"`. The page header notice remains.
- A disabled Finalise shows the blocking-check count. Notices that do not stop finalise are outside that count.
- Fix links match the table above, including `statutory-first-period-gate` for `V-GATE-001` and `?section=sub-lines` for `V-MAP-001`.
- A stored FINAL snapshot keeps `omitted` and `added` from finalise time after the live draft changes them.
- Viewer POST on the library route and on mark-remaining-no returns 403.

## Build order

Five small PRs, in this order. This document does not open them.

1. Pack only. Add `question` and `flag` on the checklist, and add `reason-labels.json`. No behaviour change. Golden figures unchanged.
2. Dashboard presentation. Group the checks, add Fix links, show the wording notice once on the review view, and show the blocking count beside a disabled Finalise. No migration.
3. Disclosure panel. Groups, pack questions, answered and unanswered counts, the note link, mark-remaining-no, and the two disclosure audit actions. Uses `findraft_disclosure_answers`. No new column.
4. Migration `m9n0o1p2q3` only, after `l8m9n0o1p2` is confirmed applied. Nullable `note_library`, privilege script, no `GRANT ALL`, no read of `companies.country_of_incorporation`. The running application does not select the column in this PR.
5. Library behaviour. Omit, force-include, the plain-English sentences, "added by preparer", `V-NOTE-001`, `V-NOTE-002`, the composer, and the snapshot copy. This is the PR that reads `note_library`.

## Cuts

Free-text notes, wording edits, and LLM narrative. Omitting an Always block or a Trial-balance block. Adding a Trial-balance block, including one whose balance is zero. Adding or omitting an unanswered block. Treating unanswered as No before mark-remaining-no succeeds. A new dashboard page, a comparatives page, or a second note renderer. iXBRL. The UK pack. Cash flow. A change to `includeWhen`, size thresholds, or any engine figure. A read or write of `companies.country_of_incorporation`. Note 1's incorporation sentence stays the pack sentence.
