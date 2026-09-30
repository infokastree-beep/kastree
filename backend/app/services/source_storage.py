"""Per-practice object storage for source documents.

Keys are ``practices/{org_id}/companies/{company_id}/documents/{document_id}``.
Production uses the existing S3 client (region default eu-west-1) when
credentials are configured. Local development uses the existing upload
directory. MinIO, Redis, and Celery are not added.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path
from typing import Protocol, cast
from uuid import UUID

from app.config import settings

_KEY_RE = re.compile(
    r"^practices/[0-9a-fA-F-]{36}/companies/[0-9a-fA-F-]{36}/documents/[0-9a-fA-F-]{36}$"
)


def practice_storage_key(*, org_id: UUID, company_id: UUID, document_id: UUID) -> str:
    return f"practices/{org_id}/companies/{company_id}/documents/{document_id}"


class SourceObjectStorage(Protocol):
    def put(self, *, key: str, body: bytes, content_type: str) -> None: ...

    def get(self, *, key: str) -> bytes: ...


class _ObjectBody(Protocol):
    def read(self) -> bytes: ...


class _S3Client(Protocol):
    def put_object(
        self, *, Bucket: str, Key: str, Body: bytes, ContentType: str
    ) -> object: ...

    def get_object(self, *, Bucket: str, Key: str) -> Mapping[str, _ObjectBody]: ...


def _require_key(key: str) -> str:
    if _KEY_RE.match(key) is None:
        raise ValueError("invalid storage key")
    return key


class LocalPracticeStorage:
    """Files under the upload directory, one prefix per practice."""

    def __init__(self, root: Path) -> None:
        self._root = root

    def put(self, *, key: str, body: bytes, content_type: str) -> None:
        del content_type
        path = self._path(_require_key(key))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)

    def list_keys(self) -> list[str]:
        root = self._root.resolve()
        if not root.exists():
            return []
        return sorted(
            path.relative_to(root).as_posix()
            for path in root.rglob("*")
            if path.is_file()
        )

    def get(self, *, key: str) -> bytes:
        return self._path(_require_key(key)).read_bytes()

    def _path(self, key: str) -> Path:
        root = self._root.resolve()
        path = (root / key).resolve()
        if path != root and root not in path.parents:
            raise ValueError("invalid storage key")
        return path


class S3PracticeStorage:
    """boto3-backed storage. No export TTL tags: source files are not exports."""

    def __init__(self, client: _S3Client | None = None) -> None:
        if client is not None:
            self._client = client
        else:
            import boto3  # type: ignore[import-untyped]

            kwargs: dict[str, object] = {"region_name": settings.s3_region}
            endpoint = settings.normalized_s3_endpoint_url()
            if endpoint:
                kwargs["endpoint_url"] = endpoint
            if settings.aws_access_key_id and settings.aws_secret_access_key:
                kwargs["aws_access_key_id"] = settings.aws_access_key_id
                kwargs["aws_secret_access_key"] = settings.aws_secret_access_key
            self._client = cast(_S3Client, boto3.client("s3", **kwargs))

    def put(self, *, key: str, body: bytes, content_type: str) -> None:
        self._client.put_object(
            Bucket=settings.s3_bucket,
            Key=_require_key(key),
            Body=body,
            ContentType=content_type,
        )

    def get(self, *, key: str) -> bytes:
        response = self._client.get_object(
            Bucket=settings.s3_bucket,
            Key=_require_key(key),
        )
        body = response["Body"].read()
        if not isinstance(body, bytes):
            raise TypeError("object body was not bytes")
        return body


def default_source_storage() -> SourceObjectStorage:
    if settings.aws_access_key_id and settings.aws_secret_access_key:
        return S3PracticeStorage()
    return LocalPracticeStorage(Path(settings.upload_dir) / "source-documents")


def get_source_storage() -> SourceObjectStorage:
    """FastAPI dependency. Tests override this."""
    return default_source_storage()
