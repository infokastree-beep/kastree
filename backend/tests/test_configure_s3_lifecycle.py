"""Unit tests for export bucket lifecycle rule shaping (no live S3).

Actual object deletion cannot be verified here — that depends on
put_bucket_lifecycle_configuration on the real bucket. See
docs/runbooks/deployment.md and scripts/configure_s3_lifecycle.py.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from botocore.exceptions import ClientError

from scripts.configure_s3_lifecycle import (
    RULE_ID,
    build_export_lifecycle_rule,
    configure_export_lifecycle,
    merge_lifecycle_rules,
)


def test_build_export_lifecycle_rule_shape() -> None:
    rule = build_export_lifecycle_rule(days=30)
    assert rule["ID"] == RULE_ID
    assert rule["Status"] == "Enabled"
    assert rule["Expiration"] == {"Days": 30}
    assert rule["Filter"]["And"]["Prefix"] == "exports/"
    assert rule["Filter"]["And"]["Tags"] == [
        {"Key": "retention", "Value": "export-30d"}
    ]


def test_merge_lifecycle_rules_is_idempotent() -> None:
    ours = build_export_lifecycle_rule(days=30)
    other = {"ID": "keep-me", "Status": "Enabled", "Expiration": {"Days": 7}}
    first = merge_lifecycle_rules([other, ours], ours)
    second = merge_lifecycle_rules(first, build_export_lifecycle_rule(days=30))
    assert len(second) == 2
    assert {r["ID"] for r in second} == {RULE_ID, "keep-me"}
    # Re-applying replaces our rule rather than duplicating it.
    assert sum(1 for r in second if r["ID"] == RULE_ID) == 1


def test_configure_export_lifecycle_puts_merged_rules() -> None:
    client = MagicMock()
    error = ClientError(
        {"Error": {"Code": "NoSuchLifecycleConfiguration", "Message": "none"}},
        "GetBucketLifecycleConfiguration",
    )
    client.get_bucket_lifecycle_configuration.side_effect = error

    config = configure_export_lifecycle(client, bucket="findraft-uploads-dev", days=30)

    client.put_bucket_lifecycle_configuration.assert_called_once()
    kwargs = client.put_bucket_lifecycle_configuration.call_args.kwargs
    assert kwargs["Bucket"] == "findraft-uploads-dev"
    rules = kwargs["LifecycleConfiguration"]["Rules"]
    assert len(rules) == 1
    assert rules[0]["ID"] == RULE_ID
    assert rules[0]["Expiration"]["Days"] == 30
    assert config == kwargs["LifecycleConfiguration"]
