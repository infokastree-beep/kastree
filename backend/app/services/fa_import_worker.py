"""Parse a stored fixed-asset register into an immutable version.

Called by a worker, not by the request handler. The grid is the engine's
build_fa_grid. The journal parser stays out of scope.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import set_rls_org_id
from app.models.fa_version import FixedAssetLine, FixedAssetVersion
from app.models.source_document import SourceDocument
from app.services.parser import ParseError
from app.services.source_storage import SourceObjectStorage
from app.services.spreadsheet_import import (
    SpreadsheetLimitError,
    read_csv_text,
    read_spreadsheet_text,
)
from findraft.engine.money import D, money
from findraft.engine.notes import build_fa_grid

_REQUIRED = ("class", "opening_cost", "additions", "disposals", "opening_dep", "charge")
_OPTIONAL = ("disposals_dep",)
_AMOUNT_FIELDS = (
    "opening_cost",
    "additions",
    "disposals",
    "disposals_dep",
    "opening_dep",
    "charge",
)


@dataclass(frozen=True)
class _FaClass:
    asset_class: str
    opening_cost: Decimal
    additions: Decimal
    disposals: Decimal
    disposals_dep: Decimal
    opening_dep: Decimal
    charge: Decimal


def process_fa_version(
    session: Session,
    *,
    org_id: uuid.UUID,
    version_id: uuid.UUID,
    storage: SourceObjectStorage,
) -> FixedAssetVersion | None:
    """Claim one pending register and parse it. Returns None if another worker holds it."""
    set_rls_org_id(session, org_id)
    claimed = session.execute(
        text(
            """
            SELECT id FROM findraft_fa_versions
            WHERE id = :id AND org_id = :org AND status = 'pending'
            FOR UPDATE SKIP LOCKED
            """
        ),
        {"id": str(version_id), "org": str(org_id)},
    ).scalar_one_or_none()
    if claimed is None:
        return None

    version = session.get(FixedAssetVersion, version_id)
    if version is None or version.status != "pending":
        return None
    document = session.get(SourceDocument, version.source_document_id)
    if document is None:
        version.status = "failed"
        version.error_message = "Source document was not found"
        session.commit()
        return version

    try:
        content = storage.get(key=document.storage_key)
        rows = _read_rows(content, document.detected_type)
        parsed = _parse_register(rows)
        grid = build_fa_grid(
            {
                row.asset_class: {
                    "opening_cost": row.opening_cost,
                    "additions": row.additions,
                    "disposals": row.disposals,
                    "disposals_dep": row.disposals_dep,
                    "opening_dep": row.opening_dep,
                    "charge": row.charge,
                }
                for row in parsed
            }
        )
        if not grid[-1].get("invariant_holds"):
            raise ParseError("Fixed asset grid does not satisfy the engine invariant")
        session.add_all(
            [
                FixedAssetLine(
                    org_id=version.org_id,
                    company_id=version.company_id,
                    fa_version_id=version.id,
                    line_no=index,
                    asset_class=row.asset_class,
                    opening_cost=row.opening_cost,
                    additions=row.additions,
                    disposals=row.disposals,
                    disposals_dep=row.disposals_dep,
                    opening_dep=row.opening_dep,
                    charge=row.charge,
                )
                for index, row in enumerate(parsed, start=1)
            ]
        )
        version.status = "ready"
        version.error_message = None
        session.commit()
        return version
    except (
        ParseError,
        SpreadsheetLimitError,
        ValueError,
        TypeError,
        ArithmeticError,
        KeyError,
    ) as exc:
        session.rollback()
        set_rls_org_id(session, org_id)
        failed = session.get(FixedAssetVersion, version_id)
        if failed is None:
            return None
        failed.status = "failed"
        failed.error_message = str(exc)[:500]
        session.commit()
        return failed


def _read_rows(content: bytes, detected_type: str) -> list[list[str]]:
    if detected_type == "xlsx":
        return read_spreadsheet_text(content)
    if detected_type == "csv":
        return read_csv_text(content)
    raise ParseError("Fixed asset import accepts xlsx or csv files")


def _header_name(cell: str) -> str:
    return cell.strip().lower().replace(" ", "_")


def _amount(raw: str) -> Decimal:
    try:
        parsed = D(raw.strip())
    except (TypeError, ValueError, ArithmeticError) as exc:
        raise ParseError("Amount must be a decimal string") from exc
    if parsed < 0:
        raise ParseError("Amount must be a non-negative exact cent amount")
    exponent = parsed.as_tuple().exponent
    if not isinstance(exponent, int) or exponent < -2:
        raise ParseError("Amount must be a non-negative exact cent amount")
    return money(parsed)


def _parse_register(rows: list[list[str]]) -> list[_FaClass]:
    header_index = next(
        (i for i, row in enumerate(rows) if any(cell.strip() for cell in row)), None
    )
    if header_index is None:
        raise ParseError("Fixed asset register has no header")
    header = [_header_name(cell) for cell in rows[header_index]]
    if len(header) != len(set(header)):
        raise ParseError("Fixed asset register has a duplicate column")
    allowed = set(_REQUIRED) | set(_OPTIONAL)
    unknown = [name for name in header if name not in allowed]
    missing = [name for name in _REQUIRED if name not in header]
    if unknown or missing:
        raise ParseError("Fixed asset register columns were not recognised")
    parsed: list[_FaClass] = []
    seen: set[str] = set()
    for row in rows[header_index + 1 :]:
        if not any(cell.strip() for cell in row):
            continue
        if len(row) != len(header):
            raise ParseError(
                "Fixed asset register has a row with the wrong column count"
            )
        values = dict(zip(header, row, strict=True))
        asset_class = values["class"].strip()
        if not asset_class or len(asset_class) > 200:
            raise ParseError("Fixed asset class name is missing or too long")
        if asset_class.casefold() == "total":
            raise ParseError("Fixed asset class Total is reserved")
        if asset_class in seen:
            raise ParseError(f"Duplicate fixed asset class: {asset_class}")
        seen.add(asset_class)
        amounts = {
            name: _amount(values[name] if name in values else "0.00")
            for name in _AMOUNT_FIELDS
        }
        parsed.append(
            _FaClass(
                asset_class=asset_class,
                opening_cost=amounts["opening_cost"],
                additions=amounts["additions"],
                disposals=amounts["disposals"],
                disposals_dep=amounts["disposals_dep"],
                opening_dep=amounts["opening_dep"],
                charge=amounts["charge"],
            )
        )
    if not parsed:
        raise ParseError("Fixed asset register has no classes")
    return parsed
