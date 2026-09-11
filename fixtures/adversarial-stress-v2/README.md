# Adversarial stress fixtures (v2)

Deliberately tricky trial-balance / GL / corrupt files for pipeline stress testing.

| File | Intent |
|------|--------|
| `01_mixed_currency_iso_column_tb.xlsx` | EUR+USD+GBP via Currency column (numeric-balanced, FX-mixed) |
| `01b_same_account_two_currencies_tb.xlsx` | Same account code in EUR and USD |
| `01c_mixed_symbol_gl.xlsx` | GL debit/credit cells with € and £ symbols |
| `02_duplicate_near_duplicate_gl.xlsx` | Exact duplicate invoice, near-dupe rent, triple bank fee |
| `03_holding_company_group_structure_tb.xlsx` | Investments, IC loans, NCI, goodwill, FCTR, impairments |
| `04_fiscal_year_apr_mar_boundary_gl.xlsx` | Apr–Mar FY with pre/post and boundary dates |
| `05a_truncated_mid_stream.xlsx` | Truncated xlsx |
| `05b_empty.xlsx` / `.csv` / `.pdf` | Empty files |
| `05c_password_protected_tb.pdf` | Password-protected PDF (`stress-test-secret`) |
| `05d_html_masquerading_as_xlsx.xlsx` | HTML saved as `.xlsx` |
| `05e_headers_only.csv` | Header row only |
| `05f_random_noise.xlsx` | Random bytes with `.xlsx` name |

Runner: `backend/scripts/run_adversarial_stress_v2.py`  
Evidence: `/opt/cursor/artifacts/stress-v2/results.json`
