"""Append-only audit log.

Each row links to the previous row for that practice with prev_hash.
The database trigger refuses UPDATE and DELETE. This module never updates
a stored row.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import aset_rls_org_id
from app.models.audit_log import AuditLog
from app.services.upload_security import escape_formula_text

GENESIS_HASH = "0" * 64

_CSV_COLUMNS = (
    "chain_seq",
    "created_at",
    "action",
    "entity_type",
    "entity_id",
    "user_id",
    "old_value",
    "new_value",
    "prev_hash",
    "row_hash",
)


def audit_row_hash(row: AuditLog) -> str:
    """SHA-256 of the stored action. prev_hash is inside the payload."""
    return _hash_fields(
        action=row.action,
        chain_seq=row.chain_seq,
        created_at=row.created_at,
        entity_id=row.entity_id,
        entity_type=row.entity_type,
        ip_address=row.ip_address,
        new_value=row.new_value,
        old_value=row.old_value,
        org_id=row.org_id,
        prev_hash=row.prev_hash,
        user_agent=row.user_agent,
        user_id=row.user_id,
    )


def verify_audit_chain(rows: Sequence[AuditLog]) -> bool:
    """True when every row links to the previous hash and its own hash matches."""
    previous = GENESIS_HASH
    expected_seq = 1
    ordered = sorted(rows, key=lambda item: item.chain_seq)
    for row in ordered:
        if row.chain_seq != expected_seq or row.prev_hash != previous:
            return False
        if row.row_hash != audit_row_hash(row):
            return False
        previous = row.row_hash
        expected_seq += 1
    return True


async def append_audit_log(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    user_id: uuid.UUID | None,
    action: str,
    entity_type: str,
    entity_id: uuid.UUID,
    old_value: dict[str, object] | None = None,
    new_value: dict[str, object] | None = None,
) -> AuditLog:
    """Insert one row. The practice row is locked so two writers cannot fork the chain."""
    await aset_rls_org_id(session, org_id)
    await session.execute(
        text("SELECT id FROM organisations WHERE id = :id FOR UPDATE"),
        {"id": str(org_id)},
    )
    previous = await session.scalar(
        select(AuditLog)
        .where(AuditLog.org_id == org_id)
        .order_by(AuditLog.chain_seq.desc())
        .limit(1)
    )
    if previous is None:
        chain_seq = 1
        prev_hash = GENESIS_HASH
    else:
        chain_seq = previous.chain_seq + 1
        prev_hash = previous.row_hash
    created_at = datetime.now(UTC)
    staged = _Staged(
        chain_seq=chain_seq,
        prev_hash=prev_hash,
        row_hash="",
        org_id=org_id,
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        old_value=old_value,
        new_value=new_value,
        ip_address=None,
        user_agent=None,
        created_at=created_at,
    )
    row_hash = _hash_fields(
        action=staged.action,
        chain_seq=staged.chain_seq,
        created_at=staged.created_at,
        entity_id=staged.entity_id,
        entity_type=staged.entity_type,
        ip_address=staged.ip_address,
        new_value=staged.new_value,
        old_value=staged.old_value,
        org_id=staged.org_id,
        prev_hash=staged.prev_hash,
        user_agent=staged.user_agent,
        user_id=staged.user_id,
    )
    record = AuditLog(
        org_id=org_id,
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        old_value=old_value,
        new_value=new_value,
        chain_seq=chain_seq,
        prev_hash=prev_hash,
        row_hash=row_hash,
        created_at=created_at,
    )
    session.add(record)
    await session.flush()
    return record


async def load_audit_log(session: AsyncSession, *, org_id: uuid.UUID) -> list[AuditLog]:
    await aset_rls_org_id(session, org_id)
    return list(
        (
            await session.scalars(
                select(AuditLog)
                .where(AuditLog.org_id == org_id)
                .order_by(AuditLog.chain_seq.asc())
            )
        ).all()
    )


def render_audit_csv(rows: Sequence[AuditLog]) -> str:
    """CSV of the chain. Every cell is escaped when it starts with = + - or @."""
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=_CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow(
            {
                "chain_seq": _cell(str(row.chain_seq)),
                "created_at": _cell(_stamp(row.created_at)),
                "action": _cell(row.action),
                "entity_type": _cell(row.entity_type),
                "entity_id": _cell(str(row.entity_id)),
                "user_id": _cell("" if row.user_id is None else str(row.user_id)),
                "old_value": _cell(_json_cell(row.old_value)),
                "new_value": _cell(_json_cell(row.new_value)),
                "prev_hash": _cell(row.prev_hash),
                "row_hash": _cell(row.row_hash),
            }
        )
    return buffer.getvalue()


class _Staged:
    def __init__(
        self,
        *,
        chain_seq: int,
        prev_hash: str,
        row_hash: str,
        org_id: uuid.UUID,
        user_id: uuid.UUID | None,
        action: str,
        entity_type: str,
        entity_id: uuid.UUID,
        old_value: dict[str, object] | None,
        new_value: dict[str, object] | None,
        ip_address: str | None,
        user_agent: str | None,
        created_at: datetime,
    ) -> None:
        self.chain_seq = chain_seq
        self.prev_hash = prev_hash
        self.row_hash = row_hash
        self.org_id = org_id
        self.user_id = user_id
        self.action = action
        self.entity_type = entity_type
        self.entity_id = entity_id
        self.old_value = old_value
        self.new_value = new_value
        self.ip_address = ip_address
        self.user_agent = user_agent
        self.created_at = created_at


def _hash_fields(
    *,
    action: str,
    chain_seq: int,
    created_at: datetime,
    entity_id: uuid.UUID,
    entity_type: str,
    ip_address: str | None,
    new_value: dict[str, object] | None,
    old_value: dict[str, object] | None,
    org_id: uuid.UUID,
    prev_hash: str,
    user_agent: str | None,
    user_id: uuid.UUID | None,
) -> str:
    payload = {
        "action": action,
        "chain_seq": chain_seq,
        "created_at": _stamp(created_at),
        "entity_id": str(entity_id),
        "entity_type": entity_type,
        "ip_address": None if ip_address is None else str(ip_address),
        "new_value": new_value,
        "old_value": old_value,
        "org_id": str(org_id),
        "prev_hash": prev_hash,
        "user_agent": user_agent,
        "user_id": None if user_id is None else str(user_id),
    }
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _stamp(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat()


def _json_cell(value: dict[str, object] | None) -> str:
    if value is None:
        return ""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _cell(value: str) -> str:
    return escape_formula_text(value)
