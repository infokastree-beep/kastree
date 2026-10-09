# findraft table privileges

Migration `e1f2a3b4c5` (`backend/alembic/versions/e1f2a3b4c5_findraft_least_privilege.py`)
narrows the `findraft` login. It revises `d0e1f2a3b4` and is the only revision
after that one. Apply it as the last step of `alembic upgrade head`, after
`d0e1f2a3b4` (company and approval details). There is no other pending
migration in this tree.

Do not apply this to the production database until you have taken the
privilege snapshot below and you are ready to run the smoke checklist.
Merging the branch to `main` starts a Railway deploy, and that deploy runs
migrations. Leave the pull request unmerged until you choose to apply it.

The grants themselves are `backend/scripts/findraft_table_privileges.sql`.
`backend/scripts/provision_findraft_app_role.sql` runs that file. Re-running
the provision script after a migration does not put `UPDATE` or `DELETE`
back on an append-only table, and it does not grant `TRUNCATE`,
`REFERENCES`, or `TRIGGER`. Sequence grants stay `ALL`.

`subscription_events` keeps `UPDATE`. The Stripe webhook inserts the event
and then sets `processed_at`. `DELETE` on that table stays revoked.

The hash-tamper check rewrites `archived_records.archived_data` as the
migration owner (`DATABASE_OWNER_URL`). The `findraft` login has no
`UPDATE` on that table, so the app cannot perform the same rewrite.

## Privilege snapshot (run on the production database)

Run this before the migration and again after it. Diff the two results.

```sql
SELECT table_name, privilege_type
FROM information_schema.role_table_grants
WHERE grantee = 'findraft'
  AND table_schema = 'public'
ORDER BY table_name, privilege_type;
```

psql's `\dp public.*` shows the same grants with the grantee on each line.
Use the query above for a diff. Sequences are not part of either result.

## Rollback

As the superuser that owns the tables:

```bash
psql "$DATABASE_URL_SYNC" -v ON_ERROR_STOP=1 \
  -f backend/scripts/rollback_findraft_table_privileges.sql
```

That restores `GRANT ALL PRIVILEGES ON ALL TABLES` and the previous default
table privileges. It does not change sequences. `alembic downgrade d0e1f2a3b4`
does the same grants and also removes this revision from `alembic_version`.

## Smoke checklist (after you apply it)

Sign in as a normal practice user. Use a client you can throw away.

1. Upload a trial balance (`.xlsx` or `.csv`).
2. Confirm the account mapping.
3. Generate statements and open them.
4. Statutory continue from that trial balance (year end opens).
5. Confirm a sub-line mapping on the statutory trial balance.
6. Post a balanced adjustment. Post it again with the same idempotency key
   and confirm one journal.
7. Save a disclosure answer.
8. Save company details (address, activity, incorporated date).
9. Lock the draft.
10. Download the draft PDF.
11. Sign up a new organisation (Clerk webhook / first-user provisioning)
    and confirm the new practice can open its own client.
12. Deliver a Stripe test webhook and confirm the organisation's
    subscription fields change.
13. Soft-delete a client, then call client erasure. The client row remains,
    the name is redacted, and `archived_records` gains an insert. The archive
    row is not updated or deleted.

Product 1 trial-balance delete (`DELETE /trial-balances/{id}`) and client
delete (`DELETE /clients/{id}`) are both soft. Each sets `is_deleted` and
`deleted_at` and inserts `archived_records`. Neither deletes the row, so
neither fires `ON DELETE CASCADE` or `ON DELETE SET NULL`. Neither updates
or deletes `archived_records`, `audit_logs`, `subscription_events`,
`findraft_draft_operations`, `findraft_tb_lines`, `findraft_fa_lines`, or
`findraft_confirmed_mappings`.

Hard deletes that remain, on tables that still have `DELETE`: a failed-parse
re-upload deletes `processing_jobs` and `financial_statements`; regenerating
statements deletes `financial_statements`; clearing a disclosure deletes
`findraft_disclosure_answers`; replacing prior-year lines deletes
`findraft_prior_year_lines`. `findraft_year_ends.adopted_trial_balance_id`
is `ON DELETE SET NULL` only when the trial-balance row itself is deleted.
The product's delete endpoint does not do that.

## Users foreign key gap

`g3h4i5j6k7` adds `findraft_year_ends.currency_confirmed_by_user_id` and
tries `REFERENCES users (id)`. The migration login in this environment is
`findraft`. That role has `REFERENCES` revoked, so the constraint raises
`permission denied for table users` and the migration records a notice and
continues. The column is stored. The foreign key is not created unless a
role that can reference `users` runs the same statement. This is the gap:
the acknowledgement user id is not enforced by the database under the
current migration role.

`i5j6k7l8m9` adds `findraft_render_jobs.draft_id` and tries a foreign key to
`findraft_draft_versions (id, org_id, company_id)`. That unique key already
exists (`findraft_draft_versions_id_org_company_key` from `v2w3x4y5z6`), so
the migration does not add it. A non-superuser `findraft` login cannot add
the foreign key because `REFERENCES` is revoked. The migration records a
notice and keeps the column. A superuser migration creates the key.

