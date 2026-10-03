# Statutory translation rules — proposal for review

**Status: design only. Not accepted. Not implemented.** No change to
`engine_line_for_confirmed_mapping` until this is approved.

Recorded 3 October 2026. This is the Phase 1 rule set for the seven Product 1
lines that have no single statutory home: `property_plant_equipment`,
`operating_expenses`, `loans`, `tax`, `depreciation`, `amortisation`,
`intangible_assets`.

The standard is FRS 102 (September 2024), Section 1A, the edition pinned by
content pack `frs102-1a-ie/2024.09`. Irish small entities take their formats
from Part II of Schedule 3A to the Companies Act 2014 (FRS 102 1A.12 and
1A.14). Paragraph numbers below are that edition. Wording here is a
paraphrase, not a reproduction of the standard.

## What the statute actually requires

Section 1A does not publish a closed list of trial-balance sub-accounts.
It requires a format, and a movement note for each class the entity
actually shows.

**Face formats this product already builds**

- **1A.12 / Schedule 3A Part II balance sheet.** Tangible assets are one
  face line. Intangible assets are one face line. Creditors are split only
  by maturity: amounts falling due within one year, and amounts falling due
  after more than one year. The engine's face follows that abridged format
  (`findraft/content/frs102-1a-ie/2024.09/statements.py`).
- **1A.14 / Schedule 3A Part II profit and loss, Format 1 (function).**
  The face lines are turnover, cost of sales, distribution costs,
  administrative expenses, other operating income, interest, and tax on
  profit. Depreciation is not a Format 1 face line. The engine adds
  `DEPRECIATION_CHARGE` into administrative expenses
  (`findraft/engine/statements.py`). Format 2 (nature of expense) is the
  format that has its own "depreciation and other amounts written off"
  line. This product does not present Format 2.

**What is a note, not a face line**

- **1AD.13 and 1AD.14** (Schedule 3A, paragraphs 45(1) to 45(3)). For each
  fixed-asset item shown on the face or as its own class in the notes, the
  notes give acquisitions, disposals, transfers, and the opening, charge,
  disposal, and closing depreciation or amortisation. The FRC note under
  1AD.14 treats an "item" as a class the entity shows. Section 1A does not
  prescribe which classes those are. A Section 1A entity is not required to
  give the Section 8 to 35 disclosures (1A.17), so paragraph 17.31's
  class-movement disclosure is not an extra obligation here. The movement
  that is obligatory is Appendix D.
- **17.8.** Land and buildings are measured separately even when bought
  together. The engine has one combined line, `FA_LAND_BUILDINGS`. This
  proposal does not invent a split the engine cannot store.
- **1AD.26** (Schedule 3A, paragraph 50(1)). For each creditor item, the
  notes give the amount repayable after five years, and the amount
  repayable between one and five years. That is a maturity analysis of a
  creditor already classified. It is not a fifth trial-balance line.
  "After five years" still maps to the after-more-than-one-year line.
- **1AD.5 to 1AD.7** (Schedule 3A paragraphs 24(2) and 25(4), and Companies
  Act 2014 section 120(3) for the unrealised-loss case). Capitalised
  development costs and goodwill need a write-off period and the reasons.
  Those are disclosure facts. They are not extra engine lines.
- **1AA.3 and 1AA.4** apply only when the entity adapts the statutory
  formats. This product does not adapt them. Goodwill is not a separate
  face line here, and current versus deferred tax is not taken from the
  adapted-format list.

**Full Schedule 3 headings, used only as the note-class vocabulary**

Schedule 3A's abridged face collapses the Arabic-numeral lines. The longer
Schedule 3 Format 1 headings are the conventional classes an Irish company
may still show in the fixed-asset note. They are the source of the
sub-lines below. They are not extra face lines.

Tangible assets (Schedule 3 Format 1, item B.II):

1. Land and buildings
2. Plant and machinery
3. Fixtures, fittings, tools and equipment
4. Payments on account and assets in the course of construction

Intangible assets (Schedule 3 Format 1, item B.I):

1. Development costs
2. Concessions, patents, licences, trade marks and similar rights
3. Goodwill
4. Payments on account

**Motor vehicles are not one of those headings.** They are a class an
entity may choose. This engine already stores that class as
`FA_MOTOR_COST`. Office equipment and computer equipment are not headings
either. They can sit in fixtures or in plant. That choice is the
accountant's.

Profit and loss Format 1 has two function lines under gross profit:
distribution costs, and administrative expenses. There is no statutory
"operating expenses" line, and no statutory "other expenses" catch-all on
this format.

## How a name is matched

This uses the matcher already in `findraft/engine/mapping.py`
(`_keyword_score`) and `backend/app/services/mapper.py` (`_keyword_score`),
not the leading-only helper `_token` in `adopted_trial_balance.py`.

1. Case-fold the name and collapse internal whitespace.
2. A phrase matches only with a word boundary on both sides:
   `\b` + phrase + `\b`. "rent" does not match "current". "motor" does not
   match "motorway". "land" does not match "landlord". "plant" does not
   match "plantation". "sales" does not match inside "cost of sales".
3. Longer phrases are tested before shorter ones.
4. An exclusion is tested before the phrase may fire. Exclusions are the
   same idea as the three FinDraft exclusion sets already in the mapper:
   liability and director words never suggest cash, tax words never suggest
   cash, and profit-and-loss wording never suggests a balance-sheet line
   (`findraft_excluded_lines`). The tables below add the collisions that
   matter inside each of these seven lines.
5. A contra phrase (accumulated, provision for, brought forward) beats a
   cost phrase in the same name.
6. If two phrases that are not in that precedence still point at different
   engine lines, there is no suggestion. One account is not split.
7. Nominal codes are not used. The Sage ranges and the long-term loan
   default in `mapping-defaults.py` are not adopted. That file sends bare
   "equipment" and "computer equipment" to plant, bare "motor" to motor
   vehicles, bare "depreciation" to the charge, and bare "loan" and
   "hire purchase" to long-term. Those are the guesses this design refuses.

**Scores.** The integer scale is the engine scale. A heuristic is capped
at 79, one below the pre-select threshold of 80, which is what
`suggest_mapping` already does. The screen shows that integer divided by
100, so 40 is 0.40. A score of 100 is only a human confirmation of the
same company, code, and name. Nothing in these tables is an auto-confirm.

| Score | When |
| --- | --- |
| 100 | The accountant has already confirmed this engine line for this company, code, and name. |
| 40 | A multi-word phrase that names one engine line, and no exclusion fires. |
| 35 | One class word that names one engine line, and no exclusion fires. |
| 0 | No suggestion. The row stays empty. |

A suggestion pre-fills the dropdown. It does not post. The accountant can
change it. Statements do not use it until they confirm it.

## Suggest, ask, remember, then stop

Product 1 has already confirmed the canonical line. This step only chooses
the engine sub-line.

- **Suggest** where one phrase scores 35 or 40. Pre-fill the dropdown.
  Show the score. Leave it changeable.
- **Needs review** where the score is 0. The row is empty. There is no
  confidence. The continuation does not abort with "has no single statutory
  line". That message is today's dead end.
- **Dropdown** on the statutory draft, for every one of these rows,
  suggested or empty. The options are only the engine lines listed for
  that Product 1 line in this document. A fixed-asset account is not
  offered Revenue. The native statutory upload screen already lists every
  engine line, because that screen has no Product 1 line to narrow it.
  This review is the same control, narrowed.
- **Remember** a confirmed choice as an engine line for that company,
  code, and name, the same way Product 1 remembers a confirmed mapping and
  the same way `findraft_confirmed_mappings` returns a prior exact engine
  line at 100. It does not replace the Product 1 canonical line.
  `property_plant_equipment` stays `property_plant_equipment` on
  `account_mappings`. Next time the same code and name come back at 100,
  still visible and still changeable.
- **Block** when, after that review, a row still has no selection. The
  draft is not built. No default is substituted. An empty row is not
  dropped into administrative expenses, plant, long-term loans, or the
  depreciation charge. This is the same gate as Product 1's mapping
  review: every row is resolved, or export does not proceed.

The 23 Product 1 lines that already have one statutory home for every name
stay direct. There is nothing to ask.

One limit is not a dropdown problem. Where the engine has no honest line,
the dropdown must not offer a wrong one. The amortisation charge is that
case. The row stays unresolved and the draft stays blocked, with the
reason on the row. That is a fail-closed stop, not a guess.

## 1. `property_plant_equipment`

**What exists**

The face line is Tangible assets, the sum of the engine's tangible lines.
The note classes the engine can hold are:

| Engine line | Statutory class it can represent |
| --- | --- |
| `FA_LAND_BUILDINGS` | Schedule 3 Format 1 "land and buildings", combined. Paragraph 17.8 wants them separable. This engine cannot split them. |
| `FA_PLANT_COST` | Schedule 3 Format 1 "plant and machinery". |
| `FA_FIXTURES_COST` | Schedule 3 Format 1 "fixtures, fittings, tools and equipment". |
| `FA_MOTOR_COST` | Motor vehicles, an entity class. Not a Schedule 3 Arabic heading. |
| `FA_ACCUM_DEP` | The only accumulated-depreciation line. Pooled across those classes. The note cannot split it by class from this mapping. |
| `ROU_ASSETS` | Right-of-use asset (Section 20), only when the name says so. |

Payments on account and assets in the course of construction have no
engine line. Leasehold is not treated as land, and it is not treated as a
right-of-use asset, unless the name says right-of-use.

**Suggestions**

| Phrase (both-side word boundary) | Line | Score | Does not fire when |
| --- | --- | --- | --- |
| accumulated depreciation; provision for depreciation; depreciation brought forward | `FA_ACCUM_DEP` | 40 | the name also matches an amortisation word (that row is not this Product 1 line) |
| land and buildings; freehold land; freehold property; freehold buildings | `FA_LAND_BUILDINGS` | 40 | the name contains leasehold, investment property, or right-of-use |
| land; buildings; premises | `FA_LAND_BUILDINGS` | 35 | leasehold, investment property, right-of-use, or landlord |
| plant and machinery | `FA_PLANT_COST` | 40 | — |
| plant; machinery | `FA_PLANT_COST` | 35 | the name is office equipment, computer equipment, or equipment on its own |
| fixtures and fittings; fixtures, fittings | `FA_FIXTURES_COST` | 40 | — |
| fixtures; fittings; furniture | `FA_FIXTURES_COST` | 35 | — |
| motor vehicles; motor vans | `FA_MOTOR_COST` | 40 | the name also contains expense, expenses, running, repairs, fuel, or insurance |
| vans; lorries; trucks | `FA_MOTOR_COST` | 35 | the same expense words |
| right-of-use asset; right of use asset | `ROU_ASSETS` | 40 | — |

"Motor" on its own does not match. "Equipment" does not match. "Property"
on its own does not match.

**Needs review — dropdown is the six lines in the table**

Fixed assets. Tangible assets. Office equipment. Computer equipment.
Equipment. Assets under construction. Payments on account. Leasehold.
Leasehold improvements. Investment property (that name is not a tangible
class; the Product 1 line itself may be wrong, and this dropdown must not
silently send it to land). Any name where two of the phrases above point
at different lines.

A class-named accumulated depreciation ("Accumulated depreciation - motor
vehicles") still suggests `FA_ACCUM_DEP` at 40. The class is not stored.
The confirmation screen should say that the note cannot analyse that pool
by class.

## 2. `operating_expenses`

**What exists**

Format 1 has two homes, and the engine has both:

| Engine line | Face line |
| --- | --- |
| `DISTRIBUTION_COSTS` | Distribution costs |
| `ADMIN_EXPENSES` | Administrative expenses |

There is no third statutory bucket. "Operating expenses", "overheads", and
"other expenses" are not Format 1 lines.

**Suggestions**

| Phrase | Line | Score | Does not fire when |
| --- | --- | --- | --- |
| distribution costs; carriage outwards; sales commission; sales wages | `DISTRIBUTION_COSTS` | 40 | the name contains inwards or inward (carriage inwards is cost of sales, not this line) |
| distribution; selling; delivery | `DISTRIBUTION_COSTS` | 35 | inwards, or the name is "selling" only as part of a fixed-asset phrase |
| administrative expenses; administration expenses | `ADMIN_EXPENSES` | 40 | — |
| rent and rates; light and heat; professional fees; accountancy fees; audit fees; bank charges | `ADMIN_EXPENSES` | 40 | the name contains income, receivable, or received (rental income is not this expense) |
| rent; rates; insurance; telephone; stationery; accountancy; audit; legal; subscriptions | `ADMIN_EXPENSES` | 35 | income, receivable, received, or the word administrator (an insolvency office, not this expense) |
| advertising; marketing | `DISTRIBUTION_COSTS` | 35 | the name contains wages or salaries (a marketing wage is still a wage; leave it empty) |

"Admin" matches only as the whole word, or as administrative /
administration. It does not match administrator.

**Needs review — dropdown is the two lines above**

Operating expenses. Overheads. General expenses. Sundry expenses. Wages,
salaries, payroll, staff costs, employers' PRSI, and pension contributions,
unless the name itself contains administrative or selling or distribution.
Motor expenses. Motor running. Travel. Repairs. Repairs and maintenance.
Office expenses. Hire, when the name does not say hire purchase (hire
purchase is not an operating expense; if it has been confirmed on this
Product 1 line, the row stays empty rather than being called
administrative). Any name that matches both a distribution phrase and an
administrative phrase.

Today's code treats "overhead" as administrative expenses. This proposal
stops that.

Advertising is the judgment in this table. It is proposed as distribution
because Format 1 puts selling costs there. If that is not accepted, the
phrase is removed and advertising stays empty. It is not proposed as a
silent default.

## 3. `loans`

**What exists**

Schedule 3A classifies creditors by maturity, not by lender. 1AD.26 then
analyses the longer portion. The engine lines are:

| Engine line | Where it sits |
| --- | --- |
| `LOANS_LT1Y` | Creditors falling due within one year |
| `LOANS_GT1Y` | Creditors falling due after more than one year |
| `BANK_OVERDRAFT` | Its own line inside creditors falling due within one year |
| `DIRECTOR_LOAN` | Not borrowings. Sign sends a debit to other debtors and a credit to other creditors. Directors' advances are the 1AD.41 to 1AD.45 disclosure. |
| `LEASE_LIABILITY_LT1Y` / `LEASE_LIABILITY_GT1Y` | Section 20 lease liabilities. Hire purchase is in that lease section from the September 2024 amendments. |

A name that says repayable after five years suggests `LOANS_GT1Y` only.
The five-year split stays in the note.

**Suggestions**

| Phrase | Line | Score | Does not fire when |
| --- | --- | --- | --- |
| bank overdraft; overdraft | `BANK_OVERDRAFT` | 40 | — |
| director's loan; directors' loan; director loan; directors loan; director current account; directors current account | `DIRECTOR_LOAN` | 40 | — |
| within one year; less than one year; less than 1 year; short-term; short term | `LOANS_LT1Y` | 40 | the name is a director loan (already matched), or the name says lease, hire purchase, or finance lease (those use the lease lines below) |
| after more than one year; more than one year; more than 1 year; non-current; non current; long-term; long term; after five years; after 5 years | `LOANS_GT1Y` | 40 | the same director-loan and lease exceptions |
| finance lease / hire purchase / lease liability, together with a within-one-year phrase | `LEASE_LIABILITY_LT1Y` | 40 | the name says leasehold, right-of-use, or ROU asset (those are assets, not the liability) |
| finance lease / hire purchase / lease liability, together with an after-more-than-one-year phrase | `LEASE_LIABILITY_GT1Y` | 40 | the same asset words |

The maturity phrase is required for a loan that is not an overdraft and
not a director loan. "Current" on its own is not a maturity phrase. It can
mean a current account.

**Needs review — dropdown is the six lines in the table**

Loan. Bank loan. Mortgage. Borrowings. Loan account. Intercompany loan.
Invoice finance. Hire purchase. Finance lease. Lease liability. Any of
those without a maturity phrase. There is no long-term default. The pack
file's bare "loan" → `LOANS_GT1Y` and bare "hire purchase" → `LOANS_GT1Y`
are not used.

## 4. `tax`

**What exists**

Format 1 has one profit-and-loss line, tax on profit. The balance sheet
then has to separate what is actually a creditor or a debtor. The engine
lines are:

| Engine line | What it is |
| --- | --- |
| `TAX_CHARGE` | The profit-and-loss tax line, including a deferred-tax charge |
| `CORP_TAX` | Corporation-tax creditor, inside creditors falling due within one year |
| `DEFERRED_TAX` | Deferred tax. Sign splits the asset and the non-current liability |
| `VAT_CONTROL` | VAT. Sign splits the asset and the creditor. Not tax on profit |
| `PAYE_PRSI` | PAYE, PRSI, USC. Not tax on profit |

**Suggestions, first match wins**

| Order | Phrase | Line | Score | Does not fire when |
| --- | --- | --- | --- | --- |
| 1 | vat; value added tax | `VAT_CONTROL` | 40 | — including when the name also says payable, recoverable, or receivable |
| 2 | paye; prsi; usc | `PAYE_PRSI` | 40 | — including when the name also says payable |
| 3 | deferred tax charge; deferred tax expense | `TAX_CHARGE` | 40 | — |
| 4 | deferred tax | `DEFERRED_TAX` | 35 | the name says charge or expense (order 3 already took those) |
| 5 | corporation tax charge; corporation tax expense; corp tax charge; tax charge; tax expense | `TAX_CHARGE` | 40 | the name says vat, paye, prsi, or usc |
| 6 | corporation tax payable; corporation tax creditor; corporation tax liability; corporation tax provision; corp tax payable | `CORP_TAX` | 40 | the name says vat, paye, prsi, or usc |

"Payable" does not by itself select corporation tax. That is the collision
in today's `_tax`: a VAT account named "VAT payable" can be sent to
`CORP_TAX`. Order 1 stops that.

**Needs review — dropdown is the five lines above**

Tax. Taxation. Corporation tax. Corp tax. Income tax. Any of those without
a charge word or a creditor word. Income tax is left empty because it may
be a misnamed corporation-tax account or a withholding, and those are
different lines.

## 5. `depreciation`

**What exists**

The charge is `DEPRECIATION_CHARGE`. The income statement adds it into
administrative expenses and does not show it on its own. The contra is
`FA_ACCUM_DEP`, inside Tangible assets. 1AD.14's period charge is the
charge line. The cumulative amount is the contra. The name has to say
which of the two it is.

**Suggestions**

| Phrase | Line | Score | Does not fire when |
| --- | --- | --- | --- |
| accumulated depreciation; provision for depreciation; depreciation brought forward; depreciation b/fwd | `FA_ACCUM_DEP` | 40 | the name matches amortisation (that is the next section) |
| depreciation charge; depreciation expense; charge for depreciation; depreciation for the year | `DEPRECIATION_CHARGE` | 40 | the name matches amortisation |

A right-of-use depreciation charge suggests `DEPRECIATION_CHARGE` at 40,
because that is the only depreciation charge line. Right-of-use
accumulated depreciation gets no suggestion: `FA_ACCUM_DEP` is the tangible
pool, and there is no right-of-use accumulated-depreciation line.

**Needs review — dropdown is `DEPRECIATION_CHARGE` and `FA_ACCUM_DEP`**

Depreciation. Depn. "Depreciation - motor vehicles", and any other
class-named depreciation that does not say accumulated, provision, charge,
expense, or for the year.

The abbreviation "acc" on its own does not match. It collides with
account and accrued. "a/dep" matches the contra only when the name also
contains depreciation or depn.

Today's code treats the bare word "depreciation" as the charge, because
`_token(name, "depreciation")` is true for every depreciation account.
This proposal stops that.

## 6. `amortisation`

**What exists**

Format 1 has no amortisation line. The charge belongs in administrative
expenses, and the cumulative amount belongs in the intangible movement
(1AD.13 and 1AD.14, the same movement used for goodwill and other
intangibles, 1AD.5 to 1AD.7).

The engine has `FA_INTANGIBLE_AMORT` for the contra. It has no
amortisation-charge line. `DEPRECIATION_CHARGE` is the tangible charge.
Using it here would put the amount inside administrative expenses and
would also make the tangible depreciation figure wrong for the note.

**Suggestions**

| Phrase | Line | Score | Does not fire when |
| --- | --- | --- | --- |
| accumulated amortisation; accumulated amortization; provision for amortisation; provision for amortization; amortisation brought forward | `FA_INTANGIBLE_AMORT` | 40 | — including when the name also says goodwill or software |

Match amortisation, amortization, amortised, amortized, and unamortised as
whole words. Do not use a bare "amort" prefix. The leading-only form is
how unrelated words get pulled in.

**Needs review — and the dropdown must not invent a charge line**

Amortisation. Amortisation charge. Amortisation expense. Amortisation of
goodwill. Amortisation of software. The only engine line available is the
contra, which is the wrong home for a charge. The dropdown does not offer
`DEPRECIATION_CHARGE` and does not offer `FA_INTANGIBLE_AMORT` as a
pretend charge. The row cannot be confirmed. The draft stays blocked, and
the row says the engine has no amortisation charge line.

That is the fail-closed case. A path forward exists for every other
ambiguous name in this document, because an honest line exists. It does
not exist here until a charge line exists.

## 7. `intangible_assets`

**What exists**

The face line is Intangible assets: cost less accumulated amortisation.
The engine has `FA_INTANGIBLE_COST` and `FA_INTANGIBLE_AMORT` only. It does
not split goodwill (Section 19) from other intangibles (Section 18). The
Schedule 3 Format 1 headings (development costs, concessions and similar
rights, goodwill, payments on account) share one cost line, because there
is no second cost line to choose. 1AD.5 to 1AD.7 remain disclosure facts,
not extra lines.

**Suggestions**

| Phrase | Line | Score | Does not fire when |
| --- | --- | --- | --- |
| the accumulated-amortisation phrases in section 6 | `FA_INTANGIBLE_AMORT` | 40 | — |
| development costs; development expenditure | `FA_INTANGIBLE_COST` | 40 | business development, staff development, or training |
| goodwill; patents; trade marks; trademarks; concessions | `FA_INTANGIBLE_COST` | 40 | the name says accumulated or provision for amortisation |
| licences; licenses | `FA_INTANGIBLE_COST` | 35 | fee, fees, subscription, or annual (a licence fee is not this asset) |
| computer software; software | `FA_INTANGIBLE_COST` | 35 | subscription |

**Needs review — dropdown is `FA_INTANGIBLE_COST` and `FA_INTANGIBLE_AMORT`**

Intangible assets. Intangibles. Website. Software subscription. Payments
on account. A licence fee. Any amortisation name that does not say
accumulated or provision. "Intangible assets" can be a net-book-value
account, so it is not suggested as cost. Website costs are often an
expense, so the name is not suggested as an asset. The accountant picks
cost or accumulated amortisation. If neither is honest, they leave the row
empty and the draft stays blocked.

## What stays blocked

The draft is not generated while any of these is true:

- A row on one of these seven lines has no selected engine line.
- Two phrases disagreed, and the accountant has not picked one.
- An amortisation charge is still present, because no honest line exists.
- The selected line is not one of the lines listed for that Product 1 line.

The draft is never completed by substituting plant, administrative
expenses, long-term loans, corporation tax, or the depreciation charge.
An ignored Product 1 row stays out, as it does today. An unconfirmed
Product 1 row still blocks, as it does today.

## What this changes from today's refuser

Today a miss aborts the whole continuation with "has no single statutory
line". Under this proposal that miss opens a review row, except the
amortisation charge, which stays blocked because the missing line is real.

The name lists, if accepted, also change what is suggested:

- Named administration costs suggest administrative expenses. Operating
  expenses, overheads, and wages stay empty.
- Bare "depreciation" and bare "corporation tax" stay empty. Today's code
  picks a line for both.
- VAT and PAYE on the Product 1 tax line suggest their own homes. "Payable"
  does not pull them onto corporation tax.
- A director's loan suggests `DIRECTOR_LOAN`.
- Hire purchase and finance leases suggest a lease liability only when the
  name states the maturity. Otherwise the row is empty.
- Goodwill, patents, and software at cost suggest `FA_INTANGIBLE_COST`.
  Bare "Intangible assets" stays empty.
- Matching is both-side word boundary, longest phrase first, with the
  exclusions in the tables. The leading-only `_token` helper is not the
  rule.

## Confirmation needed before any build

1. A phrase hit is a suggestion at 35 or 40, capped below 80, shown and
   changeable. Nothing is posted until the accountant confirms.
2. An empty row gets the dropdown listed for that Product 1 line.
3. A row that is still empty after review blocks the draft. No default
   line is written.
4. A confirmed choice is stored as an engine line for that company, code,
   and name, and comes back next time at 100. The Product 1 canonical line
   is left as it is.
5. Pooled accumulated depreciation: a class-named contra suggests
   `FA_ACCUM_DEP`, and the screen says the note cannot split that pool.
6. Land and buildings stay one engine line.
7. Office equipment, computer equipment, equipment, and assets under
   construction get no suggestion.
8. The administrative-expense list above, with wages, motor expenses,
   repairs, and overheads left empty.
9. Advertising and marketing suggested as distribution costs at 35, or
   left empty if that suggestion is rejected.
10. Director's loans suggest `DIRECTOR_LOAN`, not a borrowings line.
11. No long-term suggestion for a loan, mortgage, or hire purchase whose
    name does not state the maturity.
12. Bare "Corporation tax" left empty. VAT and PAYE suggested to their own
    lines even when the name says payable.
13. Bare "Depreciation" left empty.
14. The amortisation charge has no honest line. The row blocks the draft
    and is not offered `DEPRECIATION_CHARGE`.
15. Goodwill, patents, licences, development costs, and software suggest
    `FA_INTANGIBLE_COST`, subject to the fee and subscription exclusions.
    Bare "Intangible assets" stays empty.
