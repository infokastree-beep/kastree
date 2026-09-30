# Content pack: frs102-1a-ie, version 2024.09
FRS 102 (September 2024) Section 1A — small entities, Republic of Ireland.
This directory is one immutable pack version: content/<pack>/<version>/. A new FRC
edition is a new sibling directory; pinned drafts keep resolving to this one.

## Files
- pack.json — manifest {pack, standard, section, version, effective, effective_from,
  jurisdiction}; its pack and version must match this directory's path.
- disclosure-checklist.json — Appendix D items 1AD.1–1AD.55 {id, topic, note, statuteRef,
  statuteRefStatus, includeWhen?, evidence?}; every reference checked against the licensed
  text (v7.4); verification labels enforced by
  tests/test_checklist_integrity.py.
- notes/N0..N9 — 10 note templates; includeWhen predicates (including nested ones) are
  validated at load; tableSpec.lines_from lists canonical line names only.
  N1 carries the statement of compliance with Section 1A (1AD.3); the separate 1A.6A
  balance-sheet statement is in statements.py.
- policies.py — 12 policy blocks, individually toggleable; fixed wording (no LLM).
- mapping-defaults.py — keyword dictionary + Sage-style code ranges + confidence constants.
- statements.py — pack-side SoFP / income statement formats and SOFP_COMPLIANCE_STATEMENT
  (1A.6A; s.324(4A) CA 2014, identical to the engine's by test); layouts not yet read by the engine
  (the engine's layout is authoritative until the pack-schema decision).
- review-rules.json — 5 review rules as JSON data, evaluated by engine/predicates.py (never executed).
- test_pack_completeness.py — asserts full 1AD coverage.

## Rules enforced elsewhere (Cursor rules §3/§5)
- Ordering per 1AD.2 (note order = SoFP item order, then income statement).
- 1A.17A materiality: any 1AD item omittable if immaterial unless CA2014 requires regardless.
- 1A.9: engine must detect OCI items / non-P&L equity changes and warn if fuller statements
  (SoCIE / SoIRE) are triggered.
- Wording herein is original authored text satisfying the cited requirements — not a
  reproduction of FRS 102 (FRC/IFRS Foundation copyright). Firms may customise via the
  report-options/disclosure-library override path.

## UK variant (frs102-1a-uk)
Same engine; Appendix C (1AC) disclosure checklist + CA 2006 wording deltas. Build by
copying this pack and swapping checklist/notes where 1AC differs.
