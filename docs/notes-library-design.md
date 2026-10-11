# Notes library and the review dashboard

**Status: design only. Not built.**

This note does not add a migration, a column, or a reader. It does not read `companies.country_of_incorporation`. Build it only after revision `l8m9n0o1p2` is confirmed on the production database, and as its own change.

The Irish pack already decides which notes print. `select_notes` in `findraft/engine/notes.py` keeps a template when `includeWhen` is `always`, when the predicate is true, or when the predicate still needs an unanswered disclosure. An unanswered fact is never stored as No, and `V-DISC-001` still blocks FINAL. Policy paragraphs in `findraft/content/frs102-1a-ie/2024.09/policies.py` use the same idea through `appliesWhen`. The statement engine fills every amount. The composer prints the notes the engine returned. The Notes sidebar entry is the locked pack section `notes`, with children expanded from those printed notes (`printed-notes`).

The review dashboard on `/year-ends/{id}/draft?section=review` already shows traffic, the failed checks, and finalise. It does not show why each note is in the set.

## What this design adds

A library on the existing Notes section, and a short summary of that library on the existing review dashboard. The library is a list of the pack's own blocks. It is not a second note writer.

The preparer can omit a narrative block the engine included because a disclosure answer was Yes, and only by marking it immaterial. Everything else stays under the engine's rule. Omitting a block does not change a figure, a disclosure answer, a face line, or the pack wording.

## What the library shows

One row per pack note `N0`–`N9`, in the order the pack already prints. Under Accounting policies (`N1_POLICIES`), one row per policy id in `POLICIES`. Each row shows the pack title, the source reference already on the template, and one reason:

| Reason | When | Control |
| --- | --- | --- |
| Always | `includeWhen` or `appliesWhen` is `always` | None. The row stays on. |
| Trial balance | A derived fact in `DERIVED` made the predicate true, including a non-zero balance | None. The row stays on. The face figure and its note table stay together. |
| Disclosure yes | A preparer flag in `ANSWER_FLAGS` is Yes and that is why the block is in | Omit as immaterial, or put it back. |
| Unanswered | The predicate needs a flag that is still unanswered | None. The row stays in, marked pending. `V-DISC-001` still blocks FINAL. |
| Disclosure no | The flag is No, so the engine left the block out | None. The library does not turn it on. |
| Omitted as immaterial | The preparer used the omit control on a Disclosure-yes row | Put it back. |

`N0_ENTITY` and the compliance and basis paragraphs in `N1_POLICIES` are Always. `TAXATION` and `RELATED_PARTIES` are Always. A fixed-asset movement table, or any other note table filled from the trial balance, is Trial balance while the derived balance is not zero. Hiding that table while the face still shows the amount is not an immateriality choice.

The omit control writes one fact: this block id was omitted as immaterial on this draft. It does not edit `bodyTemplate`, a policy `body`, a checklist question, or an amount. Putting the block back deletes that fact. Answering the disclosure No later also drops the block, because the engine no longer includes it. The stored omission is then unused and is not shown as a second reason.

Wording stays the pack sentence. There is no free-text note, no note override, and no model call. The comment in `policies.py` that an LLM may adapt a policy is not this design.

## Where it is stored

On the draft, not on the company and not in `report_setup`. Two drafts of one year end can omit different blocks. `report_setup` stays the presentation already saved there: rounding, face dates, column headers, statement type, and section toggles. The Notes section stays locked on. This library does not turn that section off.

The build needs one nullable JSONB column on `findraft_draft_versions`, no server default, existing rows NULL. NULL means the preparer has omitted nothing. The value is a list of pack block ids, each a note code or a policy id, that this draft has marked immaterial. The build's migration is its own revision, after `l8m9n0o1p2`. It reapplies `backend/scripts/findraft_table_privileges.sql` and does not `GRANT ALL`. This document does not add that revision.

A locked draft keeps the list. A new version copies it the same way disclosure answers are copied. A FINAL snapshot copies the list into the snapshot next to the composed HTML. A later change to the live draft does not rewrite the stored file. `final_adopted_snapshot` keeps serving that copy.

## What the print does

`select_notes` and the policy `appliesWhen` checks stay the authority for the default set. After that selection, the composer drops a block whose id is in this draft's omission list and whose reason is still Disclosure yes. A block the engine did not select is not printed, even if an old omission names it. Amounts inside a block that remains are the engine amounts, including display rounding already applied by the composer. The JSON statement payload keeps the engine notes in full and adds the omission list, so the workspace can show a dropped block as omitted rather than as never generated.

PDF, Word, and the section preview use the composed document. They do not grow a second renderer.

## Review dashboard

The review dashboard stays `?section=review` and `statutory-review-dashboard`. Traffic, the failed-check list, currency confirmation, and finalise stay as they are.

Under that list, one notes summary, fed by the same draft the dashboard already loads:

- How many blocks the engine included.
- How many of those are pending an unanswered disclosure.
- How many Disclosure-yes blocks this draft omitted as immaterial, by title, with no amount.

A new check `V-NOTE-001`, severity NOTICE, passed false, when the omission list is non-empty. The message names the titles. It does not block FINAL. `blocks_final` does not gain this code. `V-DISC-001` is unchanged.

The summary is empty of omissions when the JSON is NULL. Pending disclosures still appear, because those already come from the engine.

## API

On the year-end draft routes that already require Product 2 access:

- A reader GET returns the library rows and the omission list. It does not create a row.
- A member POST sets or clears one block id, with the draft `row_version`. The server rejects an id that is not a pack note code or policy id, an Always block, a Trial-balance block, an unanswered block, and a block the engine did not include. Viewer receives 403. A FINAL draft is refused with the existing immutability rule.
- The audit action is `note_block_omitted` or `note_block_restored`, with the block id and no amount in `old_value` or `new_value`.

No new route outside `/year-ends`. No change to company create or company update.

## Cuts

Free-text notes, wording edits, and LLM narrative. Turning on a block the engine excluded. Omitting an Always block or a Trial-balance block. A new dashboard page. iXBRL. The UK pack. Cash flow. A change to `includeWhen`, size thresholds, or any engine figure. A read or write of `companies.country_of_incorporation`. Note 1's incorporation sentence stays the pack sentence.

## Tests, when it is built

- NULL omissions leave the composed notes equal to today's engine set, and the golden net assets and profit stay `455812.00` and `157650.00`.
- Omitting a Disclosure-yes policy removes that paragraph from the composed HTML and leaves the engine amount on the face unchanged.
- POST of `N0_ENTITY`, of a non-zero fixed-asset note, of an unknown id, and of an unanswered block returns 422 and writes nothing.
- The dashboard shows `V-NOTE-001` for an omission and `can_finalise` is unchanged by that notice alone.
- An unanswered disclosure still blocks FINAL.
- A stored FINAL snapshot keeps the omission list from finalise time after the live draft restores the block.
