"""FRS 102 Section 1A statement structures.
SoFP per 1A.12 -> Schedule 3A Part II, Companies Act 2014 (IE abridged format).
Income statement per 1A.14 -> Sch 3A Pt II P&L format (abridged: admin format lines).
Two different compliance statements, both required:
  - SoFP statement (FRS 102 1A.6A; Ireland: s.324(4A) CA 2014), prominently above the
    directors' signatures: SOFP_COMPLIANCE_STATEMENT below (the engine renders the same text;
    tests/test_v74_licensed_text.py keeps them identical).
  - Statement of compliance with Section 1A (1AD.3; s.291(7) CA 2014): note N1.
Note refs on each line auto-assigned from included notes (1AD.2 ordering).
"""
SOFP_COMPLIANCE_STATEMENT = ("These financial statements have been prepared in accordance with the "
                             "provisions applicable to companies subject to the small companies regime.")  # 1A.6A


SOFP = {
 "statement_id": "SOFP",
 "formatRef": "1A.12 / Sch 3A Pt II",
 "columns": ["note","current","prior"],
 "sections": [
  {"id":"FIXED_ASSETS","title":"Fixed assets","lines":[
    {"line":"INTANGIBLE_ASSETS","label":"Intangible assets","noteRef":"N2_FA"},
    {"line":"TANGIBLE_ASSETS","label":"Tangible assets","noteRef":"N2_FA"},
    {"line":"FINANCIAL_ASSETS","label":"Financial assets","noteRef":"N3_DEBTORS"},
  ], "subtotal":"TOTAL_FIXED_ASSETS"},
  {"id":"CURRENT_ASSETS","title":"Current assets","lines":[
    {"line":"STOCKS","label":"Stocks"},
    {"line":"TRADE_DEBTORS","label":"Trade debtors","noteRef":"N3_DEBTORS"},
    {"line":"OTHER_DEBTORS","label":"Other debtors","noteRef":"N3_DEBTORS"},
    {"line":"CASH","label":"Cash at bank and in hand","noteRef":"N3_DEBTORS"},
  ], "subtotal":"TOTAL_CURRENT_ASSETS"},
  {"id":"CREDITORS_LT1Y","title":"Creditors: amounts falling due within one year","lines":[
    {"line":"TRADE_CREDITORS","label":"Trade creditors","noteRef":"N4_CREDITORS"},
    {"line":"OTHER_CREDITORS","label":"Other creditors","noteRef":"N4_CREDITORS"},
    {"line":"ACCRUALS","label":"Accruals","noteRef":"N4_CREDITORS"},
    {"line":"TAXATION","label":"Corporation tax","noteRef":"N4_CREDITORS"},
    {"line":"LOANS_LT1Y","label":"Loans","noteRef":"N4_CREDITORS/N5_LOANS"},
    {"line":"OVERDRAFT","label":"Bank overdraft","noteRef":"N4_CREDITORS"},
  ], "subtotal":"TOTAL_CREDITORS_LT1Y","signed":-1},
  {"computed":"NET_CURRENT_ASSETS","label":"Net current assets (liabilities)"},
  {"computed":"TOTAL_ASSETS_LESS_CURRENT_LIABILITIES","label":"Total assets less current liabilities"},
  {"id":"CREDITORS_GT1Y","title":"Creditors: amounts falling due after more than one year","lines":[
    {"line":"LOANS_GT1Y","label":"Loans","noteRef":"N5_LOANS"},
    {"line":"OTHER_LT_CREDITORS","label":"Other creditors","noteRef":"N4_CREDITORS"},
  ], "subtotal":"TOTAL_CREDITORS_GT1Y","signed":-1},
  {"line":"PROVISIONS","label":"Provisions for liabilities","noteRef":"N9_COMMITMENTS"},
  {"computed":"NET_ASSETS","label":"Net assets"},
  {"id":"CAPITAL_AND_RESERVES","title":"Capital and reserves","lines":[
    {"line":"SHARE_CAPITAL","label":"Called up share capital","noteRef":"N6_CAPITAL"},
    {"line":"SHARE_PREMIUM","label":"Share premium account","noteRef":"N6_CAPITAL"},
    {"line":"REVALUATION_RESERVE","label":"Revaluation reserve","noteRef":"N6_CAPITAL"},
    {"line":"OTHER_RESERVES","label":"Other reserves","noteRef":"N6_CAPITAL"},
    {"line":"RETAINED_EARNINGS","label":"Profit and loss account","noteRef":"N6_CAPITAL"},
  ], "subtotal":"TOTAL_EQUITY"},
 ],
 "approval_block": {
   "text":"Approved by the board and authorised for issue on {{approval_date}}.",
   "signed_by":"{{director_name}}","role":"Director"
 }
}

INCOME_STATEMENT = {
 "statement_id":"IS","formatRef":"1A.14 / Sch 3A Pt II",
 "columns":["note","current","prior"],
 "sections":[
  {"line":"REVENUE","label":"Turnover","noteRef":"N1_POLICIES"},
  {"line":"COST_OF_SALES","label":"Cost of sales","signed":-1},
  {"computed":"GROSS_PROFIT","label":"Gross profit"},
  {"line":"ADMIN_EXPENSES","label":"Administrative expenses","signed":-1},
  {"line":"DISTRIBUTION","label":"Distribution costs","signed":-1},
  {"line":"OTHER_OPERATING_INCOME","label":"Other operating income"},
  {"computed":"OPERATING_PROFIT","label":"Operating profit"},
  {"line":"INTEREST_RECEIVABLE","label":"Interest receivable"},
  {"line":"INTEREST_PAYABLE","label":"Interest payable","signed":-1},
  {"computed":"PROFIT_BEFORE_TAX","label":"Profit before tax"},
  {"line":"TAXATION","label":"Tax on profit on ordinary activities","signed":-1},
  {"computed":"PROFIT_FOR_YEAR","label":"Profit for the financial year"},
 ]
}
