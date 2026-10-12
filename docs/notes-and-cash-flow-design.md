# Notes coverage and optional cash flow — design for approval

Status: design only. Nothing in this note is built. Wording drawn from a
public source stays "researched (public source)". That is not a reviewer
sign-off. The workspace label stays "source not confirmed". The banner stays
"Statutory wording not yet reviewed by a qualified reviewer".

The pack checklist `disclosure-checklist.json` is the project's list of
FRS 102 Section 1A appendix items, numbered 1AD.1 to 1AD.55. Its
`source_status` is unchanged.

## A. What the pack prints today

Ten notes. A note with `includeWhen: always` is in every pack. A trial-balance
condition includes the note when that balance is not zero. A disclosure
condition waits for a yes/no answer.

| Note | When it prints | Pack refs |
| --- | --- | --- |
| Company information | always | 1AD.52 |
| 1. Accounting policies | always | 1AD.3, 1AD.4, and the policy blocks below |
| 2. Fixed assets | fixed-asset net book value is not zero | 1AD.5 to 1AD.7, 1AD.13 to 1AD.16, 1AD.19 to 1AD.21 |
| 3. Debtors | debtors are not zero | 1AD.22 to 1AD.24 |
| 4. Creditors | creditors are not zero | 1AD.26, 1AD.27 |
| 5. Loans | loans or director loans are not zero | 1AD.40 to 1AD.46 |
| 6. Share capital and reserves | always | 1AD.17, 1AD.18, 1AD.47, 1AD.49, 1AD.50 |
| 7. Related party transactions | a related-party yes, or directors exist | 1AD.33, 1AD.38, 1AD.39, 1AD.48, 1AD.51 |
| 8. Employees | always | 1AD.37 |
| 9. Commitments and contingencies | any of commitments, guarantees, subsequent events, pension commitments, charges, or off-balance arrangements is yes | 1AD.28 to 1AD.32, 1AD.34, 1AD.54 |

Policy blocks inside note 1:

| Policy | When it applies |
| --- | --- |
| Revenue | revenue is not zero |
| Tangible fixed assets | fixed-asset net book value is not zero |
| Intangible assets | intangibles are not zero |
| Leases | a lease balance is not zero |
| Stocks | stocks are not zero |
| Debtors | debtors are not zero |
| Creditors | creditors are not zero |
| Borrowing costs | borrowings are not zero |
| Taxation | always |
| Foreign currencies | the foreign-currency question is yes |
| Employee benefits | the employees question is yes |
| Related parties | always |

Commitment blocks inside note 9, each with its own question: capital
commitments, retirement benefit commitments, guarantees and security,
charges on assets, subsequent events.

Checklist rows that are not a printed note or block: 1AD.1 (the "when
relevant" rule itself), 1AD.2 (order, done by the engine), 1AD.12, 1AD.25,
1AD.35, 1AD.36, 1AD.53, and 1AD.55. Those last six are marked `_line_level`
or have no note.

### Add and Omit today

The Notes library stores `omitted` and `added` on the draft. Add prints a
block the engine left out. Omit drops a block the engine included. Restore
and Remove undo those choices.

The controls work today for:

- the related party note
- the five commitment blocks
- the foreign-currencies policy
- the employee-benefits policy

They are refused for every always-on note, for the taxation and related-party
policies, and for every note or policy that follows a trial-balance balance.
The refusal sentences are "this note is always included" and "this note
follows the trial balance".

### Add and Omit for this list

Every row below is a library row once it is built.

Omit stays refused for two rows only: company information (1AD.52) and the
basis-of-preparation statement inside accounting policies (1AD.3). Those
two are part of the notes whenever the notes section is on.

Every other existing note, existing policy, existing commitment block, and
every proposed row gets Add and Omit. A trial-balance note can be omitted.
A disclosure block the engine left out can be added. An added block with an
empty particulars slot still blocks FINAL, the same rule as a Yes with an
empty slot. Omitting a block the checklist would have included is a notice,
not a silent drop. The notice names the row in plain English and does not
show a flag name.

This widens today's catalogue. It is not built in this design.

## A. Notes a small company commonly needs that the pack does not print

Ranked by how often a small Irish company needs the row. "Often" means a
typical trading company in a year's accounts. "Sometimes" means only when
that fact exists. "Rare" means the checklist already names it and most
small companies answer no.

The provision column is researched (public source) from the pack's 1AD list
or from FRS 102 Section 1A where the appendix does not require the row.
Practice rows are not presented as a legal mandate.

| Rank | Row | Provision | Data | Needs |
| --- | --- | --- | --- | --- |
| 1. Often, including a nil | Dividends | 1AD.35. The directors' report amount is Companies Act 2014, section 326(1)(d), which is queue item 5 and is not mapped yet | Interim and recommended amounts, or a recorded nil. The trial-balance dividends line is not the same split | Wording for a nil and for an amount. No new engine total. Test that a nil prints and that an amount ties to the recorded figure. Sign-off of the sentence |
| 2. Often when there is a tax charge or a tax creditor | Taxation note | Not an 1AD numbered note. The face already shows tax on profit. FRS 102 Section 29 is not required of a small entity | Tax charge and the corporation-tax balance the engine already has | A short note that repeats those two figures. Test that both tie to the face. Sign-off. Do not add a tax reconciliation unless a later approval asks for one |
| 3. Often when stocks are not zero | Stocks note | 1AD.4 is the policy, which already prints. A carrying-amount note is not a separate 1AD line | The stocks balance | One line that repeats the face amount under the existing policy. Test that it ties. Sign-off |
| 4. Often | Defined-contribution pension sentence | 1AD.32 is the commitment note, and it stays for the yes case. A defined-contribution sentence is practice. Section 28 is not required of a small entity | A yes/no, and the contribution charged only when yes. No new calculated total | Wording, a question, an input for the amount the preparer records, a test, sign-off |
| 5. Often, usually a nil | Controlling party | 1AD.51 sits on the related-party note and does not have its own sentence | A name, or "the directors" | One sentence on note 7. Test the nil and the named case. Sign-off |
| 6. Sometimes | Government grants | Not an 1AD line. Section 24 is not required of a small entity | A yes/no and a short particular when yes | Wording, question, input, test, sign-off |
| 7. Sometimes | Provisions other than tax | Not an 1AD line. Section 21 is not required of a small entity | A yes/no, the face amount if a provision line exists, and a particular | Wording, question, input, test that the amount ties when a face line exists. Sign-off |
| 8. Rare for this pack | Deferred tax | Section 29 is not required of a small entity | A yes/no and the amount the preparer records | Same shape as grants. Do not invent a deferred-tax calculation |
| 9. Rare | Fair-value designation particulars | 1AD.25, checklist only, no note | The existing yes, plus a particular | A block on the debtors note. Empty particular with a yes blocks FINAL |
| 10. Rare | More than one statement line for one balance | 1AD.12, checklist only | The existing yes and the breakdown amounts | A line-level particular. Amounts are Decimal and must tie |
| 11. Rare | Combined format lines | 1AD.53, checklist only | The existing yes and the particular | Wording and a particular |
| 12. Rare | Set-off | 1AD.55, checklist only | The existing yes and the particular | Wording and a particular |

These stay where they already are, and this design does not rebuild them:

- Share-class particulars, related-party amounts, directors' remuneration
  amounts, loan terms, guarantees, and post-balance-sheet particulars are
  queue item 8.
- Directors' remuneration must cite Companies Act 2014, sections 305 and 306,
  and 1AD.38. That citation fix is queue item 6. This design does not change
  the Schedule 3A sentence.
- Fixed-asset movements already have note 2. A movement grid without a
  register is the deferred fixed-assets input. This design does not add one.
- An auditor's remuneration note stays out. A company that needs an audit is
  already out of scope.
- Strategic report and ESG stay out.

Each proposed row needs four things before it can print: pack wording with
status "researched (public source)", a typed input or an engine figure that
already exists, a test that the printed amount ties or that the nil is the
nil, and reviewer sign-off before the status changes. Until sign-off, the
banner stays as it is.

## B. Optional cash flow statement

FRS 102 (September 2024) paragraph 1A.7A: a small entity is not required to
present a statement of cash flows. The statement stays optional. It is not
yet built. It is demand-gated: it is not built unless this design is
approved and a later request asks for the build.

The method, if built, is indirect only. The direct method stays out.

### Engine function

One function. It does not change the income statement, the balance sheet, or
the golden figures. It consumes balances the engine already produced.

Inputs:

- current canonical balances
- prior canonical balances, which are the opening balances
- profit before tax, the tax charge, and depreciation and amortisation, from
  those balances
- the fixed-asset cost movement when a register exists, so additions are not
  inferred from a net book value change

Classification, stored beside the canonical lines, not in a prompt:

- cash: the cash line
- operating, non-cash: depreciation, amortisation, profit or loss on disposal
- operating, working capital: stocks, debtors, creditors, accruals
- investing: fixed-asset additions and disposals
- financing: loans drawn and repaid, share issues, dividends paid

Opening cash is the prior cash balance. Closing cash is the current cash
balance. The statement reconciles: opening cash, plus the net increase or
decrease, equals closing cash, within €0.01. If it does not, the statement
is withheld. A missing prior balance is withheld too, except a recorded
first financial period, where opening cash is zero and the statement says
so. The function does not invent an opening balance.

### Tests

- The golden net assets, profit, and retained earnings are unchanged.
- A fixture with depreciation and a working-capital movement ties to the
  movement in cash.
- A missing prior year, and not a first period, produces no statement.
- A movement that does not equal the cash movement is withheld.
- Money is Decimal. No float.

### Toggle

The pack section `cash-flow` stays off by default. Today, switching it on
shows the not-built panel and the one-time notice. After a build, the same
toggle includes the statement in the PDF, the Word file, and the preview,
and switching it off drops it from that copy without deleting the figures.
The engine still does not read the toggle.

### What the build touches

The pack classification list. One engine function and the tests above. The
composer, so the section joins the PDF, Word file, and preview. It depends
on prior-year balances from queue item 11. It does not depend on a new
column. It does not use an LLM.

## C. Docs

The docs now say the cash flow statement is an optional statement for a
small entity (FRS 102 (September 2024) paragraph 1A.7A), not yet built,
demand-gated. Strategic report and ESG stay out. The direct method stays
out. Those edits are in `docs/statutory-set-of-accounts.md`,
`docs/tracked-gaps.md`, and `docs/product-roadmap.md`. They are part of
this design and wait for approval with it.
