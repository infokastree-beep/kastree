# Larger frameworks, prepared for audit, and a later ESG pack

Status: approved, with the amendments in this note. Nothing in this note is built. No larger-framework block is started from this record.

Wording drawn from a public source stays "researched (public source)" and names the provision. Figures and product sentences that a reviewer still has to accept stay "reviewer-to-confirm". Neither status is a reviewer sign-off. The workspace label stays "source not confirmed". The banner stays "Statutory wording not yet reviewed by a qualified reviewer".

This pack shares the engine, the statutory workspace, and the section toggles with the small-company pack `frs102-1a-ie` / `2024.09`. A toggle appears only when its block is built. Until then the row is absent from the sidebar. The list of what is coming stays in `docs/build-queue.md`.

## 1. What this pack is

A second pack, `frs102-ie`, version `2024.09`, for a medium or large company that applies full FRS 102 (September 2024) with the Companies Act 2014. The small-company pack stays the pack a micro or small company uses unless that company explicitly chooses this one.

The edition pin matches the small pack: accounting periods beginning on or after 1 January 2026 (`effective_from` `2026-01-01`). A period that starts before that date stays on the existing pre-2026 gate. Section 280I of the Companies Act 2014 lets a company elect to treat the size-threshold amendments as applying to financial years beginning on or after 1 January 2024, or on or after 1 January 2023. That election is an earlier-edition question (queue item 17). This pack does not implement it. Status of that boundary: reviewer-to-confirm.

The small-pack golden figures stay 455,812.00 net assets, 157,650.00 profit, and 455,712.00 retained earnings closing. This pack gets its own golden files. Those files use different figures so a medium-company fixture cannot be mistaken for the small-company golden file.

No LLM. Python owns every amount. Decimal only.

## 2. How a company is classified

The whole table is reviewer-to-confirm. The provisions below are researched (public source). The product must not treat the figures as signed off.

A company qualifies by fulfilling two or more of the three conditions in the section, for the current year and the preceding year, subject to the first-year and subsequent-year rules in that section. Group sections are a different test. This pack does not consolidate, so sections 280B and 280G are not applied.

| Class | Provision | Turnover not exceeding | Balance sheet total not exceeding | Average employees not exceeding |
| --- | --- | --- | --- | --- |
| Micro | Companies Act 2014, section 280D(3), as amended by S.I. No. 301/2024, regulation 6, in operation 1 July 2024. The company must also qualify for the small companies regime. | €900,000 | €450,000 | 10 |
| Small | Section 280A(3), as amended by S.I. No. 301/2024, regulation 4 | €15,000,000 | €7,500,000 | 50 |
| Medium | Section 280F(3), as amended by S.I. No. 301/2024, regulation 7. The employee limb was not substituted by that regulation. | €50,000,000 | €25,000,000 | 250 |
| Large | Section 280H. A company that does not qualify as small under section 280A, micro under section 280D, or medium under section 280F. | The section is a negative test. It is not "all three medium conditions exceeded". | | |

Public sources: the revised text of sections 280A, 280D, 280F, and 280H on revisedacts.lawreform.ie, and S.I. No. 301/2024 on irishstatutebook.ie. A secondary summary that says a large company is one whose turnover, balance sheet, and employees all exceed the medium figures is a gloss. The build uses section 280H.

The small pack already stores €15,000,000, €7,500,000, and 50, with `size_rule_note.source_status` of `reviewer-to-confirm`. This design does not change those small-pack figures.

Micro is the band below small. This design does not add a micro-entity pack. A micro company remains on `frs102-1a-ie` unless it explicitly chooses the full pack.

## 3. How the framework is chosen

Two facts, both stored. The size-test result does not silently change the pack.

1. The size class from section 2, using the year-end size inputs that already exist. Unrecorded size stays unrecorded.
2. An explicit pack choice on the year end. The member selects `frs102-1a-ie` or `frs102-ie`. The default for a new year end stays `frs102-1a-ie`.

Gates, once this block is built:

- Medium or large, with the small pack still selected: FINAL is refused. The sentence names the recorded class and says the full FRS 102 pack has to be chosen. A Fix link opens the framework choice.
- Small or micro, with the full pack chosen: allowed. The dashboard shows a notice that the company recorded a small or micro class and chose the full pack.
- Size not recorded, full pack chosen: FINAL is refused until the size test is recorded.
- A year that already has a draft, and the pack choice changes: that is a new pin. A FINAL snapshot is left as it was. The change is refused on a final, locked, or frozen draft with the existing plain 409 sentences.

The choice is a column added in a migration-only pull request before any screen reads it. The migration is nullable, with no server default.

## 4. Statements this pack requires

FRS 102 (September 2024) Section 1A is the reduced regime. Paragraphs 1A.7 and 1A.7A, which relieve a small entity from a statement of cash flows, do not apply. Paragraph 1A.9, which makes a statement of comprehensive income and a statement of changes in equity conditional, does not apply. The pack locks these sections on:

| Statement | FRS 102 (September 2024) | Pack lock |
| --- | --- | --- |
| Statement of financial position | Sections 3 and 4 | locked on, shared with the small pack |
| Income statement and a statement of comprehensive income, or one statement of comprehensive income | Section 5 | locked on. The small pack's income statement is the starting point. Other comprehensive income is a new block. |
| Statement of changes in equity | Section 6 | locked on |
| Statement of cash flows | Section 7 | locked on. Indirect method only. The direct method stays out. |
| Notes | Sections 3 and 8, and the sections in the next table | locked on |

A statement of income and retained earnings (paragraphs 6.4 and 6.5) is available only when the only changes in equity are profit or loss, dividends, corrections of prior-period material errors, and changes in accounting policy. It is not the default for this pack. Queue item 15 is the small-pack proposal for that statement. This pack does not build it as a substitute for the statement of changes in equity.

The cash-flow function is the one described in the approved notes design: indirect, opening cash from the prior cash balance, first financial period opening cash zero and the statement says so, reconcile within €0.01 or withhold. Overdrafts repayable on demand count as cash. Hire-purchase and lease-financed additions are non-cash. Income tax paid is operating unless specifically identified with investing or financing. Interest paid and dividends paid are financing, and that choice is reviewer-to-confirm. On this pack the section is locked on, so there is no off switch. The small pack keeps cash flow optional and off until that optional block is built. The engine does not read the toggle. Prior-year balances come from queue item 11. The function does not change the income statement, the balance sheet, or the small-pack golden figures.

## 5. Notes and disclosures beyond the small pack

Each row is its own build: pack wording with the provision and status "researched (public source)", a typed input or an engine figure that already exists, a test that the amount ties or that the nil is the nil, the parity role printed in that test, and Add and Omit in the notes library. Company information and the basis of preparation stay the two rows that cannot be omitted, matching the approved small-pack rule. An added block with an empty particular still blocks FINAL. Omitting a block the checklist would have included is a notice in plain English.

The small pack's 1AD notes stay the small pack's notes. This pack does not copy a 1AD sentence into a full-section note and call it Section 11 or Section 17.

| Order | Disclosure | FRS 102 (September 2024) | Why it is separate from the small pack |
| --- | --- | --- | --- |
| 1 | Going concern uncertainties, when they exist | Section 3 | The small pack prints a going-concern basis. A material uncertainty is a particular. |
| 2 | Other comprehensive income line analysis | Section 5 | The small pack has no OCI statement. |
| 3 | Statement of changes in equity analysis, including dividends declared | Section 6 | Share capital on the small pack is not this statement. |
| 4 | Cash flow notes: non-cash transactions and cash composition | Section 7 | They sit with the required cash flow. |
| 5 | Basic financial instruments | Section 11 | 1AD covers a reduced set. Categories, defaults, and breaches are inputs. |
| 6 | Other financial instruments | Section 12 | Only when the yes answer says they exist. No valuation calculated by the product. |
| 7 | Inventories | Section 13 | Carrying amount by class, not only the one-line stocks repeat from the small-pack list. |
| 8 | Investment property | Section 16 | Yes, plus the model the preparer records. The product does not fair-value the property. |
| 9 | Property, plant and equipment reconciliation | Section 17 | A full movement. A grid still needs the fixed-asset register when one exists. Cost movement is not inferred from net book value. |
| 10 | Intangible assets other than goodwill | Section 18 | Useful lives and the movement. |
| 11 | Business combinations and goodwill | Section 19 | Only when the yes answer says a combination exists. |
| 12 | Leases | Section 20 | The September 2024 edition's lease model, for periods beginning on or after 1 January 2026. The small-pack lease policy is Section 1A wording and is not reused. |
| 13 | Provisions and contingencies | Section 21 | Movement and a particular. The amount ties to the face when a provision line exists. |
| 14 | Revenue | Section 23 | The September 2024 revenue section. The small-pack revenue policy is not reused. |
| 15 | Government grants | Section 24 | The policy and the amount the preparer records. |
| 16 | Borrowing costs | Section 25 | Capitalised or expensed, as the preparer records. |
| 17 | Share-based payment | Section 26 | Only when the yes answer says an arrangement exists. |
| 18 | Impairment | Section 27 | Losses the preparer records, tied to the face when a line exists. |
| 19 | Employee benefits | Section 28 | Defined contribution is the common case. Defined benefit is a yes, and the product does not calculate a scheme surplus or deficit. |
| 20 | Income tax, including deferred tax | Section 29 | A tax reconciliation is in this pack. The small-pack taxation note is a repeat of the face and is not this reconciliation. Deferred tax is the amount the preparer records. |
| 21 | Foreign currency | Section 30 | The rate basis and the exchange difference the preparer records. |
| 22 | Events after the reporting period | Section 32 | The small-pack subsequent-events particular is the starting input. This note is the fuller Section 32 wording. |
| 23 | Related parties, including key management personnel compensation | Section 33 | Section 1A points a small entity at the Companies Act. This pack uses Section 33. Amounts are inputs. |
| 24 | Specialised activities | Section 34 | A question. Agriculture, extractive activities, service concessions, and financial institutions are not default notes. Whether a financial institution is refused this pack is reviewer-to-confirm. |
| 25 | First-time adoption | Section 35 | Only when the preparer records that this is the first period under FRS 102. |

Associates (Section 14) and joint ventures (Section 15) wait with consolidation. Hyperinflation (Section 31) is a question that prints a notice that this pack has no hyperinflation statements. Consolidated financial statements (Section 9) stay out.

## 6. Directors' report for a medium or large company

The small pack keeps the sentence "This is a small-company directors' report. It does not include a business review." This pack replaces that sentence with the sections below. Each is an input. The product does not draft the narrative.

Researched (public source):

- Section 325(1) lists the directors' report contents: general matters (section 326), the business review (section 327), interests in shares and debentures (section 329), the statement on relevant audit information (section 330), and the Central Bank notice where section 331 applies. Own shares are section 328.
- Section 325(1A): a company preparing under the small companies regime is not required to include a business review. A micro company may omit a directors' report where the section 328 information is a note or footnote to the balance sheet. Those reliefs do not apply on this pack.
- Section 327(1): a fair review and a description of the principal risks and uncertainties. Section 327(1A) exempts small and micro companies from subsection (1).
- Section 327(2): a balanced and comprehensive analysis of development and performance and of the assets, liabilities, and financial position.
- Section 327(3): financial key performance indicators, and where appropriate non-financial indicators including environmental and employee matters. Section 327(3A) exempts a small or micro company that elects to give subsection (1) from subsection (3)(b).
- Section 327(5): an indication of likely future developments.
- Section 325(2) brings in the audit-committee statement under section 167(3) for a large private company, and the directors' compliance statement under section 225(2) where section 225 applies.
- Section 225(7), enacted text: the compliance statement applies where the balance sheet total exceeds €12,500,000 and the turnover exceeds €25,000,000, or a prescribed amount under section 943(1)(i), and to a PLC. Both monetary conditions apply. This is not the two-of-three size test. S.I. No. 301/2024 lists sections 280A(3), 280B(4), 280D(3)(b), 280F(3), and 280G(4) as the provisions it amends. It does not list section 225. The CRO large-company page still quotes €12,500,000 and €25,000,000. Status of the trigger figures, and of whether a prescribed amount exists: reviewer-to-confirm.
- Section 330 is the statement that the directors have taken all the steps to make themselves aware of relevant audit information. Until a reviewer signs the prepared-for-audit rules, a missing section 330 statement is a notice, not a FINAL block.
- Enacted section 351 exempts a small or medium company from section 326(3) (financial instruments in the directors' report) and from section 327(3) (the KPI analysis). Later text in section 327(1A) exempts small and micro companies from the business review itself. Which of those texts applies to a medium company on this pack is reviewer-to-confirm. Until that sign-off, this pack asks for the business review, the risks, and the future developments, and it asks for the KPI analysis as an input that does not block FINAL.

Inputs, all member work, each audited without amounts:

- Business review text. Blank blocks FINAL on this pack.
- Principal risks. Blank blocks FINAL.
- Future developments. Blank blocks FINAL.
- Financial KPI particulars. Blank is a notice until the section 351 question is signed off.
- Non-financial KPI particulars, including environmental and employee matters. Same notice rule.
- Directors' compliance statement. Shown when the recorded legal form is a PLC, or when both section 225 figures are exceeded. The directors confirm the statement or record why it is not made. Blank blocks FINAL only in that case. The figures stay reviewer-to-confirm, so the block stays a notice until sign-off of the trigger.
- Audit-committee statement. Shown for a recorded large company. Blank is a notice until the section 167 trigger is signed off.
- Section 330 relevant-audit-information confirmation. Notice until prepared-for-audit sign-off.
- Section 331. A yes/no. Yes with an empty particular blocks FINAL. No prints nothing.

Sections 326, 328, and 329 stay the inputs the small pack already has.

## 7. Prepared for audit

Today a year end whose audit exemption is recorded as not claimed fails `V-CO-020` with "An audit is required. An auditor's report is out of scope." The same block fires when the size test is missing or does not evidence the exemption while a claim is attempted. That check is in `_BLOCKING`, so FINAL is refused. The engine page says the draft does not claim the exemption.

This design adds a third recorded position, beside "not recorded" and "exemption claimed": **prepared for audit**.

The practice prepares the financial statements. The auditor's report is a separate file. The product does not write an opinion.

What the practice's document says, on the cover and at the top of the financial statements:

"These financial statements were prepared for audit. They do not include an auditor's report."

The standing banner remains. Under it, the same sentence is repeated. The compilation report continues to say the engagement is not an audit. The directors' report does not say the accounts have been audited.

The uploaded file is labelled "Auditor's report — not prepared by this practice". It is stored as its own document. It is not appended to the statement PDF or the Word file. The product does not read figures out of it.

A medium or large company cannot claim the small-company audit exemption. A small or micro company that chose the full pack can still claim the exemption when the existing section 358 conditions pass. Claiming the exemption and prepared-for-audit on the same year is refused.

The prepared-for-audit document never looks final. The banner stays "Statutory wording not yet reviewed by a qualified reviewer". The cover sentence stays "These financial statements were prepared for audit. They do not include an auditor's report." Both stay on every copy. Whether any later status may look final is a reviewer decision. It is recorded here as reviewer-to-confirm. This design does not decide it.

What is blocked:

- Any sentence that is an audit opinion, including "we have audited" and "true and fair view" written as an auditor's opinion. The directors' responsibilities language that the Act already requires is a separate, already-printed statement.
- Marking the set "audited", or giving the practice's statements a final appearance.
- Dropping the banner or the prepared-for-audit cover sentence from a year end in that position.
- Merging the uploaded report into the statement file.
- A final, locked, or frozen draft refusing the status change, with the existing plain 409 sentences.

What can proceed:

- Saving the practice's statements in the prepared-for-audit position once the other gates that do not depend on a final appearance have passed. The banner and the cover sentence stay. The document does not look final.
- Attaching the auditor's file. The attachment does not make the statements look final and does not reopen a snapshot. Who attached it, and when, is audited. The file body is not copied into the audit row.

Reviewer sign-off, all reviewer-to-confirm until then:

- The cover sentence, which stays as written above.
- The banner, which stays as written above.
- Whether any later status may look final. The reviewer decision is recorded. The product does not treat the prepared-for-audit document as final.
- The file-label wording.
- Whether a missing section 330 statement blocks a save. This design keeps it a notice.
- Whether the uploaded file may be a PDF only. This design allows PDF only, checked by magic number, with the existing size cap.

Until this block is built, the current refusal stays. A company that needs an audit still cannot reach a finished set.

## 8. ESG and sustainability reporting — a later pack

This is a separate pack. It is not part of `frs102-ie`. It is not built from this design.

Known, researched (public source) at the level of the instrument's existence, and still reviewer-to-confirm before any sentence is printed:

- The Corporate Sustainability Reporting Directive and the European Sustainability Reporting Standards exist for some large undertakings and public-interest entities, with phased dates.
- An earlier non-financial statement under the Accounting Directive applies to some large public-interest entities.
- Ireland implements those instruments by statutory instrument. The instrument that applies to a given year end has to be pinned the same way the FRS edition is pinned.
- Section 327(3)(b) of the Companies Act 2014 is a directors' report point about non-financial key performance indicators. It is not a sustainability report. Those particulars live in section 6 of this design, not in the ESG pack.

Unknown, and left unknown:

- Which companies on this product are in scope.
- The Omnibus amendments and the phase-in dates that apply after 2026.
- EU taxonomy alignment, and whether any numeric taxonomy figure would be an input or a calculation.
- What assurance the report needs, and whether an assurance provider's report would follow the prepared-for-audit pattern.
- Whether the product would generate ESRS content or only a pointer that a separate report is required.
- Which Irish statutory instrument applies to a period beginning on or after 1 January 2026.

## 9. Golden files

- The existing small-company golden file is unchanged and stays on `frs102-1a-ie`.
- One medium-company file: size inputs in the medium band, pack `frs102-ie`, a balanced trial balance, prior year present, indirect cash flow that ties within €0.01, OCI nil, and a statement of changes in equity that ties to the face.
- One large-company file: the same shape, with size inputs in the large band and the prepared-for-audit position once that block exists. That file keeps the banner and the cover sentence. It is not a finished set.
- One refusal file: medium size inputs with the small pack still selected, FINAL refused, figures unprinted as a statutory set.
- Money in the files is Decimal. No float.

## 10. Effort by block

Effort is a rough size: small, medium, or large. It is not a calendar estimate.

| Block | Effort | What moves | Risk |
| --- | --- | --- | --- |
| Pack skeleton | small | A new content directory and a catalogue row. No statements. | Isolated. The small pack must stay the default. |
| Size class and explicit choice | medium | One nullable column, a classifier, refusal sentences, a Fix link. Migration first. | Easy to let the size result switch the pack by itself. The choice stays explicit. |
| Effective-date pin | small | Reuse the pre-2026 gate for the new pack id. | A period before 2026 must keep the current refusal. |
| Other comprehensive income | medium | New statement builder and a presentation page. | Must not change the income-statement profit. |
| Statement of changes in equity | medium | New statement. Depends on prior-year balances (item 11). | Must tie to share capital and retained earnings. The small-pack golden retained earnings stay 455,712.00. |
| Required cash flow | medium | The approved indirect function, locked on. Depends on item 11 and on the small-pack optional cash flow existing. | Withhold when it does not tie. Do not invent an opening balance. |
| Notes, one section at a time | large | Twenty-five rows in section 5. Each has wording, an input, tests, and Add and Omit. Sections 20 and 23 are the large parts, because the September 2024 text is not the small-pack policy. | A 1AD sentence reused under a full-section heading. |
| Fuller directors' report | large | New text inputs and two conditional statements. Migration first. | Small-pack business-review sentence must remain on the small pack. |
| Prepared for audit | medium | A third audit position, the banner, the cover sentence, and a separate labelled upload. The document never looks final. | The current "out of scope" refusal must remain until this block is on. The upload must stay out of the statement file. |
| Golden files | small | Three new fixtures and the refusal fixture. | Reusing 455,812.00 or 157,650.00 on a medium file. |
| ESG pack | large | A later pack of its own, after the unknowns in section 8 are answered. | Building it inside `frs102-ie`. |

## 11. Recommended order

Each block waits until the one above it is merged. Toggles stay hidden until that block is built. No block in this list is built from this record.

1. Pack skeleton and catalogue row. Effort: small.
2. Size classifier and the explicit choice. Effort: medium. Migration-only pull request first.
3. Effective-date pin for `frs102-ie`. Effort: small.
4. Other comprehensive income. Effort: medium.
5. Statement of changes in equity. Effort: medium.
6. Required cash flow. Effort: medium.
7. Notes in the section 5 order, one pull request per section. Effort: large.
8. Fuller directors' report. Effort: large. Migration-only pull request first.
9. Prepared for audit. Effort: medium.
10. Golden files for medium, large, and the refusal case. Effort: small.
11. ESG pack, only as its own later pack. Effort: large.

This order starts after the small-pack queue has finished items 7 to 15 and the approved notes and optional cash flow, because the required cash flow reuses that function and the statement of changes in equity reuses prior-year balances.
