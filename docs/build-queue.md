# Build queue

Status of the current build queue. Wording that is drawn from a public source stays "researched (public source)" until a qualified reviewer records a sign-off. The workspace label stays "source not confirmed". The banner stays "Statutory wording not yet reviewed by a qualified reviewer".

| Item | Status |
| --- | --- |
| 1. Housekeeping: merge the Postgres image cache, close docs PRs already on main | done |
| 2. Navigator restructure: note classes, report options, outputs, hide unbuilt, notes library | done |
| 3. Legal form dropdown and suffix rules | done |
| 4. Two signatories | done |
| 5. Directors' report required items | done |
| 6. Remuneration citation | done |
| 7. Compilation report letterhead | done. The compilation date and signatory block FINAL until both are recorded |
| 8. Particulars slots | done. The four columns and share capital by class are typed inputs on Notes. A Yes with an empty slot blocks FINAL |
| 9. Period message | done |
| 10. Dashboard work queue | done. Shared formatter and the key figures card |
| 11. Prior-year comparatives | migration y1z2a3b4c5 adds the source columns and does not map them. Readers wait until /health matches |
| 12. Trial balance re-adopt | design merged in #111. Build after item 11, migration first |
| 13. Roll forward | waiting |
| 14. Drafts list | waiting |
| 15. Statement of income and retained earnings | waiting |
| Notes, after item 15, in this order: dividends; taxation; stocks; defined-contribution pension; controlling party; government grants; provisions other than tax; deferred tax; fair-value designation; more than one statement line; combined format lines; set-off. Blocks that are not required for a small entity are labelled "optional for a small entity" and default off. Required rows keep today's behaviour. Deferred tax and provisions are ranked above the rare rows | approved, not started |
| Optional cash flow statement, after those notes | approved, build after item 15 |
| Larger frameworks (medium and large, full FRS 102) and prepared for audit | approved, not started |
| ESG and sustainability reporting | later pack, approved as its own design, not started |
| 16. Correction after final | design waiting approval |
| 17. Earlier-edition pack | design waiting approval |
| 18. Infrastructure | waiting |
| Deferred: disclosures library with Excel import and export; outputs matrix with Excel; per-statement options panel; in-review state with a reviewer role; fixed assets input; density option; iXBRL; other packs; consolidation; e-signatures | deferred |

Housekeeping left pull request 49 open. Its environment changes are not on main. The prior-year design is on main in pull request 113, and the trial-balance switch design is on main in pull request 111. Pull request 103 is closed.
