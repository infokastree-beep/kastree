# Database backups (not committed to git)

Walkthrough snapshot taken 2026-08-30 ~20:55 UTC.

## File

- `findraft_dev_walkthrough_20260830.dump` — PostgreSQL custom-format full dump (`pg_dump -Fc`)
- SHA-256: `95b6746e21a0815353bce37d9ee0e963877cc13017f382940a04282ae6ff2b90`
- Size: ~71 KB

## Restore into a fresh `findraft_dev` database

```bash
# Drop and recreate (destructive — local dev only)
dropdb -U findraft findraft_dev 2>/dev/null || true
createdb -U findraft findraft_dev

pg_restore -U findraft -d findraft_dev --no-owner --no-acl \
  /path/to/findraft_dev_walkthrough_20260830.dump
```

If `pg_restore` errors on existing objects, add `--clean --if-exists` before `-d`.

Walkthrough TB id: `9980d6b0-5f10-4fd0-b25f-63314084a904`  
Org id: `cb328f72-8a5f-56e4-bdc4-5b067897d65a`

Download this file before the cloud workspace is discarded — it is **not** in git.
