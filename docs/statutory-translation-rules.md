# Statutory translation rules — proposal for review

**Status: design only. Not accepted. Not implemented.** A name pattern
suggests a sub-line. It does not lock one. An ambiguous name stays
unmapped, and the accountant chooses on the statutory draft.

Recorded 2 October 2026 for review before any change to
`engine_line_for_confirmed_mapping`. This covers the seven Product 1 lines
that have no single automatic statutory line: `property_plant_equipment`,
`operating_expenses`, `loans`, `tax`,
`depreciation`, `amortisation`, `intangible_assets`.

The standard is FRS 102 (September 2024), Section 1A, the edition pinned by
content pack `frs102-1a-ie/2024.09`. Irish small entities apply the formats
in Part II of Schedule 3A to the Companies Act 2014 (FRS 102 footnotes to
paragraphs 1A.12 and 1A.14). Paragraph numbers below are that edition.
Wording here is a paraphrase. It is not a reproduction of the standard.

## What the statute actually requires

The product presents the statutory small-company format, not the adapted
minimum lists in paragraphs 1AA.3 and 1AB.3.

- **1A.12.** The balance sheet follows Schedule 3A. On the face this product
  already builds, tangible fixed assets are one line, **Tangible assets**,
  and intangible assets are one line, **Intangible assets**.
- **1A.14.** The profit and loss account follows Schedule 3A. This product
  uses the function-of-expense format: turnover, cost of sales, distribution
  costs, administrative expenses (the engine includes the depreciation
  charge in that face line), other operating income, interest, and tax on
  profit. Depreciation and amortisation are not face lines of their own.
- **1AD.13 and 1AD.14** (Schedule 3A, paragraphs 45(1) to 45(3)). For each
  fixed-asset item shown on the face, or shown as its own class in the
  notes, the notes give opening and closing cost, acquisitions, disposals,
  transfers, and the opening, charge, disposal, and closing depreciation or
  amortisation. The FRC note under 1AD.14 says an "item" is a class shown
  separately on the face or in the notes. Section 1A does not prescribe the
  class list.
- **17.8.** Land and buildings are accounted for separately even when bought
  together. That is a measurement rule. The engine has one combined line
  for them.
- **17.31.** Full FRS 102 asks for a movement by class of property, plant
  and equipment. A Section 1A entity is not specifically required to give
  the Section 8 to 35 disclosures (1A.17), except the movement Appendix D
  already requires. Classes are whatever the entity shows.
- **1AA.4(a) and (b).** Only if the entity adapts the balance-sheet format:
  property, plant and equipment in classifications appropriate to that
  entity, and goodwill shown apart from other intangible assets. This
  product does not adapt the format, so those splits are not face lines.
- **1AD.26** (Schedule 3A, paragraph 50(1)). For each creditor item, the
  notes state the amount falling due after five years. That is a note
  analysis. There is no fifth-year trial-balance line.
- **1AA.3(o) and (p),** on an adapted balance sheet: current tax, and
  deferred tax shown as non-current. The product's statutory format
  already has a corporation-tax creditor inside amounts falling due within
  one year, and a deferred-tax sign home.

The full Companies Act format (the longer Schedule 3 headings, before the
small-company format collapses the Arabic-numeral lines) analyses tangible
assets as land and buildings; plant and machinery; fixtures, fittings,
tools and equipment; and payments on account and assets in the course of
construction. **Motor vehicles are not one of those headings.** They are a
class an entity may choose, and this engine already has a line for them.
Office equipment is not a heading either. It can sit in "fixtures,
fittings, tools and equipment" or in plant. That is why a generic
"Office equipment" name gets no suggestion below, and the accountant
chooses.

## Rules that apply to every line

1. The accountant has already confirmed the Product 1 line. The rule reads
   the account name only. Nominal-code ranges are not used. The Sage
   defaults in `mapping-defaults.py` are not adopted: they send bare
   "equipment" to plant and a bare "loan" to long-term.
2. The only lines a suggestion or a dropdown may offer are engine lines
   already in `statutory_lines()`. This proposal adds no lines.
3. Matching is case-insensitive and on word boundaries, more specific
   patterns first. A contra pattern wins over a cost pattern in the same
   name.
4. If two patterns point at different engine lines, there is no suggestion.
   One account is not split.
5. A pattern match is a suggestion. It is not written onto the draft until
   the accountant confirms it. See the next section.

In the seven sections below, "suggests" means a pre-filled dropdown and a
confidence score. "Needs review" means the row stays empty. Neither one
locks a classification, and neither one stops the draft with no way to
choose.

## Suggest, ask, remember

This follows the human-confirms pattern Product 1 already uses. A
suggestion is shown with its confidence. The accountant picks the line.
The choice is stored for that company and offered again next time. Nothing
in that chain is silent.

The scale is the one the mapping screen already shows. Product 1 stores
confidence as a fraction from 0 to 1. The statutory suggester uses an
integer score and divides by 100 before display, so 79 is shown as 0.79.
A heuristic stays below the pre-select threshold of 0.80. A score of 1.00
is only a human confirmation. That cap already applies to
`suggest_statutory_mapping`.

**A confident name is a suggestion.** "Motor Vehicles - Cost" on
`property_plant_equipment` suggests `FA_MOTOR_COST`, with a confidence
below 0.80 and the method recorded as the name pattern. The statutory
draft pre-fills that line in the dropdown, the same way Product 1
pre-fills a suggested canonical line. The accountant can change it before
confirming. The statements do not use it until then.

**An ambiguous name stays unmapped.** "Fixed Assets - Office Equipment"
and "Operating Expenses" get no suggestion and no confidence. The row is
needs-review, which is how Product 1 already treats a row whose suggestion
is `unmapped`. The continuation does not abort with "has no single
statutory line". That error is the current dead end: adoption runs
`engine_line_for_confirmed_mapping` and stops the whole draft on the first
miss, and the continuation screen only shows the error text.

**The draft offers a dropdown.** Each needs-review row, and each suggested
row, has a dropdown of the engine lines listed for that Product 1 line in
this document. Office equipment can be set to fixtures or to plant by the
accountant. Operating expenses can be set to distribution costs or to
administrative expenses. The dropdown is those homes, not the whole chart,
because the Product 1 line is already confirmed and a fixed-asset account
should not be offered Revenue. The native statutory upload screen already
has a dropdown and a confidence badge; that screen lists every engine
line because it has no Product 1 line to narrow it. This review is the
same control, narrowed to the homes for the line being resolved.

The draft is not built until every one of these rows has a selection. That
is the same gate as Product 1's mapping review: choose a line for every
row, then confirm.

**A confirmed choice is remembered for that company.** Product 1 stores a
confirmed mapping on `account_mappings`, unique on company, account code,
and account name. The next file for that company is pre-filled from that
row at confidence 1.00. The statutory upload path already does the
equivalent for an engine line: `findraft_confirmed_mappings` for that
company, and the next import suggests the same code and name at score 100.
A manual sub-line choice is stored the same way, as an engine line. It
does not replace the Product 1 canonical line. `property_plant_equipment`
stays `property_plant_equipment` on `account_mappings`. Next period the
same code and name come back pre-filled at 1.00, still visible, still
changeable, and still confirmed again with the rest of the draft. A
remembered choice is not a silent lock.

The 23 Product 1 lines that already have one statutory home for every name
stay direct. There is nothing to ask. This review is the seven lines in
this document.

One limit remains. The dropdown cannot offer a line the engine does not
have. An amortisation charge still has no profit-and-loss line of its own,
so the accountant cannot place that charge correctly until that line
exists. Accumulated amortisation can be chosen. Office equipment can be
chosen onto fixtures or plant. The missing charge line is a missing home,
not a hidden guess.

## 1. `property_plant_equipment`

**Face.** One line, Tangible assets, which is the sum of the engine's
tangible lines. The note classes below are the lines the engine can hold.
They are not a statutory closed list.

| Engine line | What it is |
| --- | --- |
| `FA_LAND_BUILDINGS` | Land and buildings, one combined line. Paragraph 17.8 wants land and buildings separable; this engine cannot do that. |
| `FA_PLANT_COST` | Plant and machinery. |
| `FA_FIXTURES_COST` | Fixtures and fittings. |
| `FA_MOTOR_COST` | Motor vehicles, an entity class this engine already stores. Not a Schedule 3 heading. |
| `FA_ACCUM_DEP` | The only accumulated-depreciation line. It is pooled across those classes. |
| `ROU_ASSETS` | A right-of-use asset (Section 20). Only when the name says so. |

**Suggested cost names**

- Land and buildings, freehold land, freehold buildings, freehold property,
  premises → `FA_LAND_BUILDINGS`.
- Plant, machinery, plant and machinery → `FA_PLANT_COST`.
- Fixtures, fittings, furniture, office furniture → `FA_FIXTURES_COST`.
- Motor vehicles, motor vans, vans, lorries, trucks → `FA_MOTOR_COST`.
  The word "motor" on its own does not match.
- Right-of-use asset, right of use asset → `ROU_ASSETS`.

**Accumulated depreciation**

Any name that says accumulated depreciation, provision for depreciation,
or depreciation brought forward → `FA_ACCUM_DEP`, including when the name
also names a class ("Accumulated depreciation - motor vehicles"). The face
has one contra line, so the class is not stored. The fixed-asset note
cannot then show that class's own depreciation movement (1AD.14) from this
mapping alone. Confirm this pooling before it is built. A right-of-use
accumulated-depreciation name gets no suggestion: there is no right-of-use
contra line. The accountant can still pick one of the tangible lines below.

**Needs review**

These names get an empty row. The dropdown is the six lines in the table
above.

- Fixed assets, tangible assets, PPE, property, sundry assets, additions,
  disposals, capital expenditure.
- Office equipment, equipment, computer equipment, IT equipment. Computer
  equipment has its own life in the product's tangible-asset policy and no
  engine line. Folding it into plant would be a guess. Office equipment is
  the worked example: fixtures and plant are both defensible, so the
  accountant chooses.
- Assets under construction, assets in course of construction, payments on
  account. Those are a full-format heading with no engine line.
- Leasehold, leasehold property, leasehold improvements. Leasehold can be
  a right-of-use asset or, for improvements, fixtures or buildings.
- Investment property. That is a different engine line, and the confirmed
  Product 1 line says tangible assets. It is not offered in this dropdown.
  The accountant changes the Product 1 mapping, which is already remembered
  for that company.

## 2. `operating_expenses`

**Face.** Two function lines, and no further statutory analysis:

| Engine line | Face label |
| --- | --- |
| `DISTRIBUTION_COSTS` | Distribution costs |
| `ADMIN_EXPENSES` | Administrative expenses (the depreciation charge is added on the face by the engine; it is not chosen here) |

Rent, rates, wages, insurance and the rest are not statutory lines. They
are components of one of those two functions. The standard does not assign
them. A name is suggested only when it states the function, or when it is
an establishment or administration cost with no credible distribution
reading. The accountant confirms or changes it.
Cost of sales, interest, tax, and depreciation stay on their own Product 1
lines and are not reclassified here.

**Suggested administrative expenses**

Rent, rates, service charges, insurance, light and heat, electricity, gas,
heating, telephone, broadband, postage, stationery, printing, accountancy,
audit, legal fees, professional fees, bank charges, bank fees,
subscriptions. Also a name that itself says administrative,
administration, office salaries, or admin wages.

**Suggested distribution costs**

Distribution, selling, sales commission, carriage outwards, freight
outwards, delivery costs, sales wages, selling wages, delivery wages.

**Please confirm — advertising and marketing**

Proposed home: `DISTRIBUTION_COSTS`, as the selling function on a Format 1
profit and loss account. Some charts book advertising in administrative
expenses. Until that is confirmed, these names are needs-review, not a
suggestion.

**Needs review**

The dropdown is the two lines in the table above.

- Operating expenses, overheads, general expenses, sundry expenses,
  miscellaneous, other expenses. "Overheads" gets no suggestion on purpose.
  The current code treats it as administrative expenses.
- Wages, salaries, payroll, staff costs, employers' PRSI, pension
  contributions, unless the name itself says administrative or selling.
- Motor expenses, motor running, travel, repairs, repairs and maintenance.
- Office expenses.

## 3. `loans`

**Face.** Maturity, not lender:

| Engine line | Where it sits |
| --- | --- |
| `LOANS_LT1Y` | Creditors falling due within one year |
| `LOANS_GT1Y` | Creditors falling due after more than one year |
| `BANK_OVERDRAFT` | Its own line inside creditors falling due within one year |
| `DIRECTOR_LOAN` | Not borrowings. Sign sends it to other debtors or other creditors. Directors' advances are the 1AD.41 to 1AD.45 disclosure. |
| `LEASE_LIABILITY_LT1Y` / `LEASE_LIABILITY_GT1Y` | Section 20 lease liabilities, including hire purchase under the September 2024 lease section |

A name that says repayable after five years suggests `LOANS_GT1Y`.
The five-year amount is the 1AD.26 note, not a translation target.

**Suggested**

- Overdraft → `BANK_OVERDRAFT`.
- Director's loan, directors' loan, director loan, director current
  account → `DIRECTOR_LOAN`.
- A loan or borrowing whose name states "within one year", "less than one
  year", or "short-term" → `LOANS_LT1Y`.
- A loan or borrowing whose name states "after more than one year", "more
  than one year", "non-current", or "long-term" → `LOANS_GT1Y`.
- Finance lease, lease liability, or hire purchase, and the name also
  states one of those maturity phrases → the matching lease-liability line.

**Needs review**

The dropdown is the lines in the table above. Loan, bank loan, mortgage,
borrowings, hire purchase, finance lease, lease liability, invoice
finance, intercompany loan, and loan account get no suggestion whenever
the name does not state the maturity. "Current" on its own is not a
maturity: it can mean a current account. There is no default to long-term.
The accountant picks the maturity, the overdraft line, the director-loan
line, or a lease liability.

## 4. `tax`

**Homes**

| Engine line | What it is |
| --- | --- |
| `TAX_CHARGE` | Tax expense on the profit and loss account, including a deferred-tax charge |
| `CORP_TAX` | Corporation-tax creditor, inside creditors falling due within one year |
| `DEFERRED_TAX` | Deferred tax. Sign splits the asset and the non-current liability |
| `VAT_CONTROL` | VAT. Sign splits the asset and the creditor. Not corporation tax |
| `PAYE_PRSI` | PAYE, PRSI, USC. Not corporation tax |

**Suggested, in this order**

1. VAT or value added tax → `VAT_CONTROL`, even if the name also says
   payable.
2. PAYE, PRSI, or USC → `PAYE_PRSI`, even if the name also says payable.
3. Deferred tax charge, or deferred tax expense → `TAX_CHARGE`.
4. Deferred tax, deferred tax asset, deferred tax liability, or deferred
   tax provision, with no charge or expense word → `DEFERRED_TAX`.
5. Corporation tax charge, corporation tax expense, corp tax charge, tax
   charge, tax expense → `TAX_CHARGE`.
6. Corporation tax payable, corporation tax creditor, corporation tax
   liability, or corporation tax provision → `CORP_TAX`.

**Needs review**

The dropdown is the five lines in the table above. Tax, taxation,
corporation tax, and corp tax get no suggestion when the name does not say
whether it is the charge or the creditor. Income tax gets no suggestion: it
may be a misnamed corporation-tax account or a different withholding. The
accountant chooses.

## 5. `depreciation`

**Presentation.** The charge is `DEPRECIATION_CHARGE`. The income statement
adds it into administrative expenses and does not show it as its own face
line. The contra is `FA_ACCUM_DEP`, inside Tangible assets. The note's
period charge (1AD.14) is the charge line; the cumulative amount is the
contra. A name has to say which of the two it is.

**Suggested**

- Accumulated depreciation, provision for depreciation, depreciation
  brought forward → `FA_ACCUM_DEP`.
- Depreciation charge, depreciation expense, charge for depreciation,
  depreciation for the year → `DEPRECIATION_CHARGE`. A right-of-use
  depreciation charge suggests the same profit-and-loss line. Right-of-use
  accumulated depreciation gets no suggestion, as under tangible assets.

**Needs review**

The dropdown is `DEPRECIATION_CHARGE` and `FA_ACCUM_DEP`. Depreciation,
depn, and "Depreciation - motor vehicles" or any other class-named
depreciation that does not say accumulated, provision, charge, or expense
stay empty until the accountant picks one. A name that says amortisation
is not offered a tangible line here; it belongs on the amortisation
review.

The current code treats the bare word "depreciation" as the charge. This
proposal stops that.

## 6. `amortisation`

**Presentation.** Format 1 has no amortisation line. The charge belongs in
administrative expenses, and the cumulative amount belongs in the
intangible movement (1AD.13 and 1AD.14, the same movement Appendix D
points at for goodwill and other intangibles).

The engine has `FA_INTANGIBLE_AMORT` for the contra. It has no
amortisation-charge line. `DEPRECIATION_CHARGE` is the tangible charge. Using
it for amortisation would put the amount inside administrative expenses and
would also make the tangible depreciation figure wrong for the note.

**Suggested**

Accumulated amortisation, provision for amortisation, amortisation brought
forward → `FA_INTANGIBLE_AMORT`, including when the name also says
goodwill or software.

**Needs review**

Amortisation, amortisation charge, amortisation expense, amortisation of
goodwill, amortisation of software. The only line the dropdown can offer
today is `FA_INTANGIBLE_AMORT`, which is the contra, not the charge. The
profit-and-loss charge still has no line that hits administrative expenses
and stays identifiable as intangible amortisation. This proposal does not
borrow `DEPRECIATION_CHARGE`. That charge remains the one case with no
honest choice until a line exists.

## 7. `intangible_assets`

**Face.** One line, Intangible assets: cost less accumulated amortisation.
The engine has `FA_INTANGIBLE_COST` and `FA_INTANGIBLE_AMORT` only. It does
not split goodwill (Section 19) from other intangibles (Section 18). Extra
wording for capitalised development costs and for goodwill (1AD.5 to
1AD.7) is a disclosure fact, not a second trial-balance line.

The full-format intangible headings are development costs; concessions,
patents, licences, trade marks and similar rights; goodwill; and payments
on account. On this engine they share one cost line, because the face line
is the same and there is no second cost line to choose.

**Suggested cost → `FA_INTANGIBLE_COST`**

Goodwill. Patents, trade marks, trademarks, licences, licenses,
concessions. Development costs or development expenditure. Computer
software or software, unless the name says subscription. A name that says
cost together with intangible, goodwill, software, or patent.

**Suggested contra → `FA_INTANGIBLE_AMORT`**

The accumulated-amortisation names in section 6.

**Needs review**

The dropdown is `FA_INTANGIBLE_COST` and `FA_INTANGIBLE_AMORT`. Intangible
assets, intangibles, website, software subscription, payments on account,
and any amortisation name that does not say accumulated or provision stay
empty. "Intangible assets" can be a net-book-value account. Website costs
are often an expense, so the name is not suggested as an intangible cost.
The accountant picks cost or accumulated amortisation.

## What this changes from today's refuser

Today a miss aborts the whole continuation with "has no single statutory
line". Under this proposal that miss opens a review row. A confident name
is pre-filled below 0.80. An ambiguous name is empty. The accountant
picks, confirms, and the choice is remembered for that company.

The name lists, if accepted, change only what is suggested:

- Named administration costs (rent, rates, insurance, light and heat,
  professional fees, bank charges) suggest administrative expenses.
  Operating expenses, overheads, and wages stay empty.
- Bare "depreciation" and bare "corporation tax" stay empty. Today's code
  picks a line for both.
- VAT and PAYE on the Product 1 tax line suggest their own homes, and are
  not suggested as corporation tax.
- A director's loan on the Product 1 loans line suggests `DIRECTOR_LOAN`.
- Hire purchase and finance leases suggest a lease liability only when the
  name states the maturity. Otherwise the row is empty.
- Goodwill, patents, and software at cost suggest `FA_INTANGIBLE_COST`.
  Bare "Intangible assets" stays empty.

## Confirmation needed before any build

1. A name-pattern hit is a suggestion below 0.80, shown and changeable.
   Nothing is posted until the accountant confirms.
2. An empty row gets a dropdown of the homes listed for that Product 1
   line, and the draft waits until every row has a selection.
3. A confirmed choice is stored as an engine line for that company, code,
   and name, and comes back next time at 1.00. The Product 1 canonical
   line is left as it is.
4. Pooled accumulated depreciation: a class-named contra suggests
   `FA_ACCUM_DEP`.
5. Land and buildings stay one engine line.
6. Office equipment, computer equipment, and assets under construction get
   no suggestion. The accountant chooses an existing tangible line.
7. The administrative-expense suggestion list above, with wages, motor
   expenses, repairs, and overheads left empty.
8. Advertising and marketing as a distribution-cost suggestion, or left
   empty.
9. Director's loans suggest `DIRECTOR_LOAN`, not a borrowings line.
10. No long-term suggestion for a loan, mortgage, or hire purchase whose
    name does not state the maturity.
11. Bare "Corporation tax" left empty. VAT and PAYE suggested to their own
    lines.
12. Bare "Depreciation" left empty.
13. The amortisation charge still has no honest line to offer.
14. Goodwill, patents, licences, development costs, and software suggest
    `FA_INTANGIBLE_COST`. Bare "Intangible assets" left empty.
