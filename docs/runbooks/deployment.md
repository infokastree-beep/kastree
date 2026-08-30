# Deployment Runbook

## Pre-launch checklist (object storage)

Terraform under `terraform/` is Month 2+ (Cursor Rules §4). Until IaC owns the
bucket, run these steps once per environment after the S3/R2 bucket exists.

### Export file retention (Product Spec §12.2 / §12.6)

Generated Excel/PDF/CSV files must expire after **30 days**. Deletion is
enforced only by a **bucket-level lifecycle configuration** — not by
`put_object(Expires=...)` (that sets an HTTP caching header only) and not by
application-level deletion logic.

1. Configure the lifecycle rule (idempotent; safe to re-run):

   ```bash
   cd backend
   python scripts/configure_s3_lifecycle.py
   # or: python -m scripts.configure_s3_lifecycle
   ```

   The script merges a rule (`findraft-exports-expire-30d`) that:
   - Filters on prefix `exports/` **and** tag `retention=export-30d`
   - Sets `Expiration.Days` to `export_file_ttl_days` (default 30)

2. **Verify on the real bucket** (unit tests against a mocked S3 client cannot
   prove objects are deleted):

   ```bash
   aws s3api get-bucket-lifecycle-configuration --bucket "$S3_BUCKET"
   ```

   Confirm the rule is `Enabled`, matches `exports/` + the retention tag, and
   `Expiration.Days` is `30`.

3. Application uploads (`S3ObjectStorage.put_export`) must continue to set
   `Tagging=retention=export-30d` so the tag filter matches. `Expires=` on
   put is optional (caching hint only) and must not be treated as retention.

If a download is requested after the object is gone, the exporter regenerates
from retained statement data in Postgres (`regenerate_export_if_missing`).
