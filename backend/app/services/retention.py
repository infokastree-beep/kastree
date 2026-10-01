"""Retention wins over erasure for accounting records.

The 7-year period is the 6-year statutory floor plus a 1-year buffer.
The buffer is an engineering margin. It is not itself a statutory period.
"""

from __future__ import annotations

STATUTORY_FLOOR_YEARS = 6
RETENTION_YEARS = 7
REDACTED_CLIENT_NAME = "[Redacted Client]"
ERASED_EMAIL_DOMAIN = "erased.invalid"

RETAINED_ON_ERASURE: tuple[str, ...] = (
    "audit_logs",
    "archived_records",
    "companies",
    "trial_balances",
    "findraft_draft_versions",
    "findraft_source_documents",
)

RETENTION_POLICY_STATEMENT = (
    "Accounting records are kept for 7 years. That period is the 6-year floor "
    "in Companies Act 2014 section 285 and Taxes Consolidation Act 1997 "
    "section 886, plus a 1-year engineering buffer. The buffer is not a "
    "statutory requirement. An erasure request replaces a user's email and "
    "login identifier with a non-identifying value, and replaces a client "
    "name with [Redacted Client]. It does not delete or rewrite trial "
    "balances, mappings, drafts, statements, source documents, company legal "
    "names, director names, archived_records, or audit_logs. Those records "
    "win over erasure. Archived records keep their hash and retention_until. "
    "The audit log is append-only. Erasure adds a new row and does not copy "
    "the erased name into it. A name already stored in an earlier archive "
    "stays there."
)
