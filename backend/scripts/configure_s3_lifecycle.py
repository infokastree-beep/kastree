#!/usr/bin/env python3
"""One-time (idempotent) S3/R2 bucket lifecycle for FinDraft export files.

Product Spec §12.2 / §12.6: generated export files under exports/ are deleted
after 30 days by *bucket* lifecycle configuration — not by put_object(Expires=...)
(that header is only an HTTP caching hint) and not by application-level deletion.

Run once per environment after the bucket exists, or re-run safely anytime:

    cd backend && python -m scripts.configure_s3_lifecycle
    # or: python scripts/configure_s3_lifecycle.py

Verify on the real bucket (pytest cannot catch this):

    aws s3api get-bucket-lifecycle-configuration --bucket "$S3_BUCKET"
    # Expect a rule with Prefix exports/ (or retention=export-30d) and Expiration Days=30.

Terraform under terraform/ is Month 2+ (Cursor Rules §4); until then this script
(or the equivalent manual step in docs/runbooks/deployment.md) is the control.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

# Allow `python scripts/configure_s3_lifecycle.py` from backend/
if __name__ == "__main__" and __package__ is None:
    sys.path.insert(0, str(__file__).rsplit("/scripts/", 1)[0])

from app.config import settings  # noqa: E402

RULE_ID = "findraft-exports-expire-30d"
EXPORT_PREFIX = "exports/"
RETENTION_TAG_KEY = "retention"
RETENTION_TAG_VALUE = "export-30d"


def build_export_lifecycle_rule(*, days: int | None = None, r2: bool = False) -> dict[str, Any]:
    """Lifecycle rule: expire objects under exports/.

    AWS S3: prefix + retention tag (objects uploaded with Tagging=).
    Cloudflare R2: prefix only — R2 does not support object tagging on PutObject.
    """
    ttl = days if days is not None else settings.export_file_ttl_days
    if r2:
        return {
            "ID": RULE_ID,
            "Status": "Enabled",
            "Filter": {"Prefix": EXPORT_PREFIX},
            "Expiration": {"Days": ttl},
        }
    return {
        "ID": RULE_ID,
        "Status": "Enabled",
        "Filter": {
            "And": {
                "Prefix": EXPORT_PREFIX,
                "Tags": [
                    {"Key": RETENTION_TAG_KEY, "Value": RETENTION_TAG_VALUE},
                ],
            }
        },
        "Expiration": {"Days": ttl},
    }


def merge_lifecycle_rules(
    existing_rules: list[dict[str, Any]],
    export_rule: dict[str, Any],
) -> list[dict[str, Any]]:
    """Replace our rule by ID if present; leave all other rules untouched."""
    merged = [rule for rule in existing_rules if rule.get("ID") != RULE_ID]
    merged.append(export_rule)
    return merged


def get_existing_rules(client: Any, bucket: str) -> list[dict[str, Any]]:
    from botocore.exceptions import ClientError

    try:
        response = client.get_bucket_lifecycle_configuration(Bucket=bucket)
        return list(response.get("Rules") or [])
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        # NoSuchLifecycleConfiguration — empty bucket config is fine.
        if code in ("NoSuchLifecycleConfiguration", "404"):
            return []
        raise


def configure_export_lifecycle(
    client: Any,
    *,
    bucket: str | None = None,
    days: int | None = None,
) -> dict[str, Any]:
    """Idempotent put_bucket_lifecycle_configuration for the export retention rule.

    Returns the configuration that was applied (Rules list).
    """
    target = bucket or settings.s3_bucket
    r2 = bool(
        settings.normalized_s3_endpoint_url()
        and "r2.cloudflarestorage.com" in settings.normalized_s3_endpoint_url()
    )
    export_rule = build_export_lifecycle_rule(days=days, r2=r2)
    existing = get_existing_rules(client, target)
    rules = merge_lifecycle_rules(existing, export_rule)
    configuration = {"Rules": rules}
    client.put_bucket_lifecycle_configuration(
        Bucket=target,
        LifecycleConfiguration=configuration,
    )
    return configuration


def _build_s3_client() -> Any:
    import boto3

    kwargs: dict[str, Any] = {"region_name": settings.s3_region}
    endpoint = settings.normalized_s3_endpoint_url()
    if endpoint:
        kwargs["endpoint_url"] = endpoint
    if settings.aws_access_key_id and settings.aws_secret_access_key:
        kwargs["aws_access_key_id"] = settings.aws_access_key_id
        kwargs["aws_secret_access_key"] = settings.aws_secret_access_key
    return boto3.client("s3", **kwargs)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Configure idempotent S3/R2 lifecycle: expire exports/ objects "
            f"tagged {RETENTION_TAG_KEY}={RETENTION_TAG_VALUE} after "
            f"{settings.export_file_ttl_days} days."
        )
    )
    parser.add_argument(
        "--bucket",
        default=None,
        help=f"Bucket name (default: settings.s3_bucket={settings.s3_bucket!r})",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=None,
        help=f"Expiration days (default: {settings.export_file_ttl_days})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the merged Rules JSON without calling put_bucket_lifecycle_configuration",
    )
    args = parser.parse_args(argv)

    client = _build_s3_client()
    target = args.bucket or settings.s3_bucket
    export_rule = build_export_lifecycle_rule(days=args.days)
    existing = get_existing_rules(client, target)
    rules = merge_lifecycle_rules(existing, export_rule)
    configuration = {"Rules": rules}

    print(json.dumps(configuration, indent=2, default=str))
    if args.dry_run:
        print(f"\nDry run — would put_bucket_lifecycle_configuration on {target!r}")
        return 0

    client.put_bucket_lifecycle_configuration(
        Bucket=target,
        LifecycleConfiguration=configuration,
    )
    print(f"\nApplied lifecycle configuration on bucket {target!r} (rule id={RULE_ID})")
    print(
        "Verify: aws s3api get-bucket-lifecycle-configuration "
        f"--bucket {target}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
