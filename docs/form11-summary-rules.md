# Form 11 Summary — mapping rules for review

**Status: design only. Not accepted. Not implemented.**

Recorded 2 October 2026. This is the rule set for a second choice on the
Reporting framework dropdown, beside "FRS 102 Section 1A (Ireland)":
**Sole Trader / Form 11 Summary**. No code until these rules are confirmed.

The source is Revenue's *Guide to Completing 2025 Pay and File Tax Returns*,
Extracts From Accounts, lines 124–168, for Form 11 2025 (tax year 2025).
Headings below are Revenue's. A later year's form is a new line map. Line
numbers are not reused silently.

## What the summary is

The Statutory tab already has one framework, FRS 102 Section 1A (Ireland),
pack `frs102-1a-ie` / `2024.09`. Choosing Form 11 does not call that pack
and does not generate a statutory draft. It reads the trial balance and the
confirmed Product 1 mappings already on the page. There is no new upload
and no new mapping pass.

Python sums the confirmed accounts into the boxes below. The language model
does not classify, add, or adjust. Each box shows its amount and the
accounts behind it, so the accountant can key the figures into ROS.

The summary is shown before it is treated as final. A row that the rules
place in a named box can be moved. A move, if the accountant makes one, is
remembered for that company, account code, and account name, the same way
a confirmed Product 1 mapping is remembered. The Product 1 canonical line
is not changed. Seeing the summary does not require that extra step.

Partnerships are out of scope. Revenue says an individual partner does not
complete these pages; the partnership files them on Form 1. A trial balance
with share capital is a company chart. The summary says so and does not
force company equity into the sole-trader capital boxes.

## What it deliberately does not do

Lines 159–168 are the adjusted net-profit computation. Revenue says the
extracts are not a tax-adjustment computation. This summary leaves 159–168
blank. It does not calculate a private-use add-back, entertainment, stock
relief, carbon-tax relief, or any other adjustment. Line 160 ("Motor
Expenses — add back private element") is not the accounts total for motor
costs. That total is line 138.

Kastree does not prepare or file Form 11. The practice keys ROS and remains
the filer.

## The boxes

| Lines | Box | Kind |
| --- | --- | --- |
| 124–125 | Accounts period, from and to | The trial balance `period_start` and `period_end` |
| 128 | Sales / Receipts / Turnover | Trade income, excluding line 129 |
| 129 | Receipts from Government Agencies | GMS, free legal aid, Department of Agriculture payments, and the like |
| 130 | Other trading income, including tax-exempt trading income | Other income that belongs with the trade. Not rent, dividends, or interest |
| 131 | Purchases | Materials, or goods for resale |
| 132 | Gross trading profit | Shown from the identified income, purchases, and stock movement. Omitted if those pieces are not identified |
| 133 | Salaries / Wages | Staff pay, staff PRSI, staff pensions, redundancy. Not the owner's wages |
| 134 | Additional staff costs | Staff costs that are not wages and not motor or travel |
| 135 | RCT subcontractors | Building, meat processing, and forestry only |
| 136 | Other subcontractors | Subcontractors who are not in 135, such as locums |
| 137 | Consultancy, professional fees | Audit, accountancy, legal, architect, auctioneer, surveyor |
| 138 | Motor, travel and subsistence | One box. Motor and travelling in the accounts are added together |
| 139 | Repairs / Renewals | Maintenance of property, equipment, and machinery. Not improvements |
| 140 | Rental expenses | Property rent and rates |
| 141 | Depreciation, goodwill / capital write-off | The profit-and-loss charge for the period |
| 142 | Provisions, including bad debts | The profit-and-loss provision. A reduction goes in 142(b) |
| 143 | Other expenses | Every other profit-and-loss expense |
| 144 | Other expenses — credit entries | Credits that reduce expenses |
| 145 | Cash / capital introduced | |
| 146 | Drawings, net of tax and pension | Includes the owner's wages and private costs paid by the business |
| 147 | Closing capital | Only if the accounts already state it. Not computed from company equity |
| 148 | Stock, work in progress, finished goods | Closing stock |
| 149 | Debtors and prepayments | |
| 150 | Cash / bank (debit) | |
| 151 | Bank / loans / overdraft (credit) | |
| 152–153 | Client account balances | Only when the name says client account |
| 154 | Creditors and accruals | |
| 155 | Tax creditors | VAT, PAYE, income tax, RCT, CGT owing |
| 156 | Net assets, or net liabilities | The trial-balance identity, if it balances |
| 157 / 158 | Net trade profit, or loss, per the accounts | The trade result after the exclusions below. Profit in 157, loss in 158 |

## How an account gets a box

1. A remembered Form 11 choice for that company, code, and name is
   pre-filled at confidence 1.00. The accountant can still move it.
2. Otherwise the confirmed Product 1 line and the account name are read.
   A named box is used only when the line, or the name, is that box.
3. A profit-and-loss expense that matches no named box goes to **143**.
   That is Revenue's residual category ("the total of all other expenses
   included in your Profit and Loss Account and not listed above"). It is
   listed account by account, so nothing is hidden inside the total.
4. Income, balance-sheet amounts, drawings, and capital do not fall into
   143. If they match no box, the row is listed under "not an extracts
   line" with the reason. They are not dropped and they are not forced
   into turnover or wages.
5. Two boxes never share one account. The summary does not split a row.

Name matching is case-insensitive and on word boundaries. More specific
names win over the Product 1 line. "Owner's wages" is drawings even if the
confirmed line is operating expenses.

## Income

| Confirmed line or name | Box |
| --- | --- |
| `revenue`, and the name is not a Government payment | 128 |
| Name says GMS, Government, Department of Agriculture, DAFM, BPS, BISS, or scheme payment | 129, even if the confirmed line is `revenue` |
| `other_revenue`, and the name is trading income rather than rent, dividends, or interest | 130 |
| `interest_income`, rent, or dividends | Not an extracts income line. Revenue says those go to their own panels. Listed, not put in 128 or 130 |

## Purchases and gross profit

`cost_of_sales` is not line 131. Purchases are only the accounts whose
names say purchases, materials, or goods for resale.

A `cost_of_sales` account whose name says wages, subcontractors, motor, or
professional fees uses that expense box. Revenue's own note is that
subcontractors are often left inside cost of sales and still belong on 135
or 136.

Any other `cost_of_sales` balance is listed under cost of sales and is not
called purchases. Line 132 is shown only when income, purchases, and the
stock movement are all identified. Otherwise 132 is left blank rather than
filled with a figure that is not the accounts' gross profit.

## Expenses

| Name, on `operating_expenses` or `cost_of_sales` | Box |
| --- | --- |
| Wages, salaries, payroll, staff PRSI, staff pension, redundancy | 133 |
| Owner's wages, proprietor's wages, drawings | 146, not 133 |
| Staff training, staff welfare, staff party | 134 |
| The name says RCT, or Relevant Contracts Tax | 135 |
| Subcontractor, sub-contractor, locum, and the name does not say RCT | 136 |
| Accountancy, audit, legal, solicitor, professional fees, consultancy, architect, auctioneer, surveyor | 137 |
| Motor, travel, travelling, subsistence, mileage, fuel, motor tax, motor insurance, motor repairs | 138 |
| Repairs, renewals, maintenance, and the name does not say motor | 139 |
| Rent, rates, property service charge | 140 |
| Bad debt, provision for doubtful debts | 142. A credit reduction of that provision is 142(b) |
| Anything else on `operating_expenses` | 143 |

Light and heat, phone, insurance, advertising, bank charges, stationery,
and subscriptions have no box of their own. They are 143. The private
element of light, heat, and phone is line 162, which this summary does not
calculate.

`interest_expense` is 143. Bank interest is not a separate extracts box.

`depreciation`, when it is the profit-and-loss charge, is 141.
`amortisation`, when it is the profit-and-loss charge, is 141, which also
holds a goodwill or capital write-off. Accumulated depreciation and
accumulated amortisation are balance-sheet contras. They stay inside net
assets. They are not line 141.

A credit that reduces expenses, such as an exchange gain sitting on an
expense account, is 144 when the account is in credit. A debit expense is
not put in 144.

## Balance sheet and capital

| Confirmed line or name | Box |
| --- | --- |
| `inventory` | 148, closing stock |
| `trade_receivables`, `other_receivables`, `prepayments`, `accrued_income` | 149 |
| `cash` with a debit balance | 150 |
| `cash` with a credit balance, `loans`, or a name that says overdraft | 151 |
| Name says client account, debit | 152 |
| Name says client account, credit | 153 |
| `trade_payables`, `other_payables`, `accruals`, `deferred_income` | 154 |
| `taxes_payable`, `social_security_payable`, or a name that says VAT, PAYE, PRSI, income tax, RCT, or CGT and is a creditor | 155 |
| Name says drawings, or owner's wages | 146 |
| Name says capital introduced | 145 |
| `property_plant_equipment`, `intangible_assets`, `investments` | No extracts category. They are inside 156 only |
| `provisions` as a balance-sheet liability | Inside 156, not line 142. Line 142 is the profit-and-loss movement |
| `share_capital`, `share_premium`, `retained_earnings`, `revaluation_reserve`, `capital_contribution`, `dividends` | Not mapped. These are company equity. The summary says the chart looks like a company |

Line 156 is the trial balance's net assets when the trial balance balances.
It is not a second arithmetic over a subset of boxes.

Line 147, closing capital, is filled only when an account is already named
as closing capital. It is not derived by adding profit to equity accounts.

## Profit per the accounts

Line 157, or 158 if the result is a loss, is the trade result after
removing the rows listed as "not an extracts line" (interest income, rent,
dividends, company-equity movements). The removed rows are shown beside
the profit so the accountant can see the exclusion. No other adjustment is
made. Lines 159–168 stay blank.

## What is easier than FRS 102, and what is not

There is no disclosure note, no fixed-asset class, and no refusal for an
ordinary overhead. Insurance, advertising, and "Other expenses" all have a
home: line 143.

The rules still do not invent a box the form does not have. Government
payments stay out of turnover. The owner's wages stay out of staff wages.
RCT subcontractors are not assumed from the bare word "subcontractor".
Purchases are not assumed from the whole of cost of sales. The tax
add-backs are not calculated.
