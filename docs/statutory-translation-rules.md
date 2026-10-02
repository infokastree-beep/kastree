# Statutory translation rules — proposal for review

**Status: design only. Not accepted. Not implemented.**

Recorded 2 October 2026 for review before any change to
`engine_line_for_confirmed_mapping`. This covers the seven Product 1 lines
that already refuse when the account name does not resolve to one engine
line: `property_plant_equipment`, `operating_expenses`, `loans`, `tax`,
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
"Office equipment" name is a refusal below, not a default.

## Rules that apply to every line

1. The accountant has already confirmed the Product 1 line. The rule reads
   the account name only. Mapping suggestions and nominal-code ranges are
   not used. The Sage defaults in `mapping-defaults.py` are not adopted:
   they send bare "equipment" to plant and a bare "loan" to long-term.
2. The only allowed target is an engine line already in `statutory_lines()`.
   This proposal adds no lines. A name whose honest class has no line is
   refused.
3. Matching is case-insensitive and on word boundaries, more specific
   patterns first. A contra pattern wins over a cost pattern in the same
   name.
4. If two patterns point at different engine lines, the name is refused.
   One account is not split.
5. If no pattern matches, the name is refused with the existing outcome:
   that account has no single statutory line. There is no default class.

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

**Confident cost names**

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
accumulated-depreciation name is refused: there is no right-of-use contra
line.

**Refused**

- Fixed assets, tangible assets, PPE, property, sundry assets, additions,
  disposals, capital expenditure.
- Office equipment, equipment, computer equipment, IT equipment. Computer
  equipment has its own life in the product's tangible-asset policy and no
  engine line. Folding it into plant would be a guess. Office equipment is
  the worked example: fixtures and plant are both defensible, so it is
  refused.
- Assets under construction, assets in course of construction, payments on
  account. Those are a full-format heading with no engine line.
- Leasehold, leasehold property, leasehold improvements. Leasehold can be
  a right-of-use asset or, for improvements, fixtures or buildings.
- Investment property. That is a different engine line, and the confirmed
  Product 1 line says tangible assets. The clash is a refusal, not a
  silent reclass.

## 2. `operating_expenses`

**Face.** Two function lines, and no further statutory analysis:

| Engine line | Face label |
| --- | --- |
| `DISTRIBUTION_COSTS` | Distribution costs |
| `ADMIN_EXPENSES` | Administrative expenses (the depreciation charge is added on the face by the engine; it is not chosen here) |

Rent, rates, wages, insurance and the rest are not statutory lines. They
are components of one of those two functions. The standard does not assign
them. A name maps only when it states the function, or when it is an
establishment or administration cost with no credible distribution reading.
Cost of sales, interest, tax, and depreciation stay on their own Product 1
lines and are not reclassified here.

**Confident administrative expenses**

Rent, rates, service charges, insurance, light and heat, electricity, gas,
heating, telephone, broadband, postage, stationery, printing, accountancy,
audit, legal fees, professional fees, bank charges, bank fees,
subscriptions. Also a name that itself says administrative,
administration, office salaries, or admin wages.

**Confident distribution costs**

Distribution, selling, sales commission, carriage outwards, freight
outwards, delivery costs, sales wages, selling wages, delivery wages.

**Please confirm — advertising and marketing**

Proposed home: `DISTRIBUTION_COSTS`, as the selling function on a Format 1
profit and loss account. Some charts book advertising in administrative
expenses. If that split is not acceptable, these names are refusals too.

**Refused**

- Operating expenses, overheads, general expenses, sundry expenses,
  miscellaneous, other expenses. "Overheads" is refused on purpose. The
  current code treats it as administrative expenses.
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

A name that says repayable after five years still maps to `LOANS_GT1Y`.
The five-year amount is the 1AD.26 note, not a translation target.

**Confident**

- Overdraft → `BANK_OVERDRAFT`.
- Director's loan, directors' loan, director loan, director current
  account → `DIRECTOR_LOAN`.
- A loan or borrowing whose name states "within one year", "less than one
  year", or "short-term" → `LOANS_LT1Y`.
- A loan or borrowing whose name states "after more than one year", "more
  than one year", "non-current", or "long-term" → `LOANS_GT1Y`.
- Finance lease, lease liability, or hire purchase, and the name also
  states one of those maturity phrases → the matching lease-liability line.

**Refused**

Loan, bank loan, mortgage, borrowings, hire purchase, finance lease, lease
liability, invoice finance, intercompany loan, and loan account, whenever
the name does not state the maturity. "Current" on its own is not a
maturity: it can mean a current account. There is no default to long-term.

## 4. `tax`

**Homes**

| Engine line | What it is |
| --- | --- |
| `TAX_CHARGE` | Tax expense on the profit and loss account, including a deferred-tax charge |
| `CORP_TAX` | Corporation-tax creditor, inside creditors falling due within one year |
| `DEFERRED_TAX` | Deferred tax. Sign splits the asset and the non-current liability |
| `VAT_CONTROL` | VAT. Sign splits the asset and the creditor. Not corporation tax |
| `PAYE_PRSI` | PAYE, PRSI, USC. Not corporation tax |

**Confident, in this order**

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

**Refused**

Tax, taxation, corporation tax, and corp tax, when the name does not say
whether it is the charge or the creditor. Income tax is refused: it may be
a misnamed corporation-tax account or a different withholding.

## 5. `depreciation`

**Presentation.** The charge is `DEPRECIATION_CHARGE`. The income statement
adds it into administrative expenses and does not show it as its own face
line. The contra is `FA_ACCUM_DEP`, inside Tangible assets. The note's
period charge (1AD.14) is the charge line; the cumulative amount is the
contra. A name has to say which of the two it is.

**Confident**

- Accumulated depreciation, provision for depreciation, depreciation
  brought forward → `FA_ACCUM_DEP`.
- Depreciation charge, depreciation expense, charge for depreciation,
  depreciation for the year → `DEPRECIATION_CHARGE`. A right-of-use
  depreciation charge uses the same profit-and-loss line. Right-of-use
  accumulated depreciation is refused, as under tangible assets.

**Refused**

Depreciation, depn, and "Depreciation - motor vehicles" or any other
class-named depreciation that does not say accumulated, provision, charge,
or expense. A name that says amortisation is refused on this Product 1
line.

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

**Confident**

Accumulated amortisation, provision for amortisation, amortisation brought
forward → `FA_INTANGIBLE_AMORT`, including when the name also says
goodwill or software.

**Refused**

Amortisation, amortisation charge, amortisation expense, amortisation of
goodwill, amortisation of software. The profit-and-loss charge stays
refused until there is a line that hits administrative expenses and stays
identifiable as intangible amortisation. This proposal does not borrow
`DEPRECIATION_CHARGE`.

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

**Confident cost → `FA_INTANGIBLE_COST`**

Goodwill. Patents, trade marks, trademarks, licences, licenses,
concessions. Development costs or development expenditure. Computer
software or software, unless the name says subscription. A name that says
cost together with intangible, goodwill, software, or patent.

**Confident contra → `FA_INTANGIBLE_AMORT`**

The accumulated-amortisation names in section 6.

**Refused**

Intangible assets, intangibles, website, software subscription, payments on
account, and any amortisation name that does not say accumulated or
provision. "Intangible assets" can be a net-book-value account. Website
costs are often an expense, so the name is not taken as an intangible cost.

## What this changes from today's refuser

Today's functions already refuse the generic names that started this work
("Fixed Assets - Office Equipment", "Rent", a bare loan, a bare tax
account). The deliberate changes, if this proposal is accepted, are:

- Named administration costs (rent, rates, insurance, light and heat,
  professional fees, bank charges) become administrative expenses. Bare
  operating expenses, overheads, and wages stay refused.
- Bare "depreciation" and bare "corporation tax" stay refused, tighter
  than today's code, which currently picks a line for both.
- VAT and PAYE on the Product 1 tax line go to their own homes, and never
  to corporation tax.
- A director's loan on the Product 1 loans line goes to `DIRECTOR_LOAN`.
- Hire purchase and finance leases go to lease liabilities only when the
  name states the maturity.
- "Intangible assets" with no cost or accumulated-amortisation word is
  refused. Goodwill, patents, and software at cost still map.

## Confirmation needed before any build

1. Pooled accumulated depreciation: a class-named contra still maps to
   `FA_ACCUM_DEP`.
2. Land and buildings stay one engine line.
3. Office equipment, computer equipment, and assets under construction
   stay refusals.
4. The administrative-expense name list above, with wages, motor expenses,
   repairs, and overheads still refused.
5. Advertising and marketing as distribution costs, or as a refusal.
6. Director's loans leave the borrowings lines.
7. No long-term default for a loan, mortgage, or hire purchase whose name
   does not state the maturity.
8. Bare "Corporation tax" refused; VAT and PAYE never mapped to it.
9. Bare "Depreciation" refused.
10. The amortisation charge refused until it has its own profit-and-loss
    line.
11. Goodwill, patents, licences, development costs, and software share
    `FA_INTANGIBLE_COST`. Bare "Intangible assets" refused.
