"""Ephemeral standalone Convert jobs — filesystem store (no org / RLS).

Subscriber Upload / trial_balances are never touched. Jobs live under
``{upload_dir}/standalone_conversions/{id}.json`` with a short TTL.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from typing import Any, Literal

from openpyxl import Workbook

from app.config import settings

logger = logging.getLogger(__name__)

CONVERT_PRODUCT = "kastree_convert"
CONVERT_AMOUNT_EUR_CENTS = 1900  # €19.00
JOB_TTL = timedelta(hours=48)

ConversionStatus = Literal["pending_payment", "paid", "expired"]


@dataclass
class ConvertRow:
    account_code: str
    account_name: str
    debit: Decimal
    credit: Decimal


def _store_dir() -> Path:
    root = Path(settings.upload_dir) / "standalone_conversions"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _job_path(conversion_id: uuid.UUID) -> Path:
    return _store_dir() / f"{conversion_id}.json"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def save_conversion(
    *,
    rows: list[dict[str, Any]],
    customer_email: str | None = None,
) -> uuid.UUID:
    conversion_id = uuid.uuid4()
    payload = {
        "id": str(conversion_id),
        "status": "pending_payment",
        "rows": rows,
        "stripe_session_id": None,
        "customer_email": customer_email,
        "created_at": _now().isoformat(),
        "paid_at": None,
        "expires_at": (_now() + JOB_TTL).isoformat(),
        "download_count": 0,
    }
    _job_path(conversion_id).write_text(json.dumps(payload), encoding="utf-8")
    return conversion_id


def load_conversion(conversion_id: uuid.UUID) -> dict[str, Any] | None:
    path = _job_path(conversion_id)
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    expires_at = datetime.fromisoformat(str(data["expires_at"]))
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if _now() > expires_at and data.get("status") != "paid":
        data["status"] = "expired"
        path.write_text(json.dumps(data), encoding="utf-8")
    return data


def load_conversion_by_session(session_id: str) -> dict[str, Any] | None:
    for path in _store_dir().glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if data.get("stripe_session_id") == session_id:
            return data
    return None


def update_conversion(conversion_id: uuid.UUID, **fields: Any) -> dict[str, Any] | None:
    data = load_conversion(conversion_id)
    if data is None:
        return None
    data.update(fields)
    _job_path(conversion_id).write_text(json.dumps(data), encoding="utf-8")
    return data


def mark_paid_by_session(session_id: str) -> dict[str, Any] | None:
    data = load_conversion_by_session(session_id)
    if data is None:
        return None
    if data.get("status") == "paid":
        return data
    return update_conversion(
        uuid.UUID(str(data["id"])),
        status="paid",
        paid_at=_now().isoformat(),
    )


def rows_to_xlsx_bytes(rows: list[dict[str, Any]]) -> bytes:
    """Build a four-column TB workbook for download."""
    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "Trial Balance"
    ws.append(["Account Code", "Account Name", "Debit", "Credit"])
    for row in rows:
        ws.append(
            [
                str(row.get("account_code", "")),
                str(row.get("account_name", "")),
                str(row.get("debit", "0")),
                str(row.get("credit", "0")),
            ]
        )
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def frontend_base_url() -> str:
    if settings.frontend_base_url:
        return settings.frontend_base_url.rstrip("/")
    origins = [
        origin.strip()
        for origin in settings.cors_origins.split(",")
        if origin.strip()
    ]
    if origins:
        return origins[0].rstrip("/")
    return "https://www.kastree.ie"
