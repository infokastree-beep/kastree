"""Company letterhead and this year's approval. No figures are calculated here."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal, InvalidOperation

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.company import Company
from app.schemas.company_details import (
    AdviserRecord,
    ApprovalWrite,
    CompanyDetailsResponse,
    CompanyDetailsWrite,
    DirectorRecord,
    ShareClassOut,
    ShareClassWrite,
)
from app.services.audit import append_audit_log
from app.services.reconciliation import ReconciliationCheck
from findraft.models.year_end import YearEnd

_BLOCKING = frozenset({"V-CO-001", "V-CO-002", "V-CO-005", "V-CO-006"})


class CompanyDetailsRejected(Exception):
    def __init__(self, detail: str, status_code: int = 400) -> None:
        self.detail = detail
        self.status_code = status_code
        super().__init__(detail)


def blocks_final(checks: tuple[ReconciliationCheck, ...]) -> bool:
    return any(not item.passed and item.code in _BLOCKING for item in checks)


def _blank(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    return text or None


def _single_line(value: str | None, *, label: str, limit: int) -> str | None:
    text = _blank(value)
    if text is None:
        return None
    if any(ord(char) < 32 for char in text):
        raise CompanyDetailsRejected(f"{label} cannot include a line break.")
    if len(text) > limit:
        raise CompanyDetailsRejected(f"{label} is too long.")
    return text


def _address(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return None
    if any(ord(char) < 32 and char != "\n" for char in text):
        raise CompanyDetailsRejected(
            "Business address contains a character that cannot be stored."
        )
    if len(text) > 2000:
        raise CompanyDetailsRejected("Business address is too long.")
    return text


def _employees(value: int | None) -> int | None:
    if value is None:
        return None
    if value < 0 or value > 1_000_000:
        raise CompanyDetailsRejected(
            "Average number of employees must be a whole number from 0 to 1000000."
        )
    return value


def _company_number(value: str | None) -> str | None:
    text = _blank(value)
    if text is None:
        return None
    compact = text.replace(" ", "")
    if not compact.isalnum() or len(compact) > 20:
        raise CompanyDetailsRejected(
            "Company number must be letters and numbers, up to 20 characters."
        )
    return compact


def _directors(rows: list[DirectorRecord]) -> list[dict[str, object]]:
    if len(rows) > 40:
        raise CompanyDetailsRejected("Record at most 40 directors.")
    stored: list[dict[str, object]] = []
    seen: set[str] = set()
    for row in rows:
        name = row.name.strip()
        if not name or any(ord(char) < 32 for char in name):
            raise CompanyDetailsRejected("Each director needs a name.")
        if len(name) > 200:
            raise CompanyDetailsRejected("A director name is too long.")
        if name in seen:
            raise CompanyDetailsRejected(f"Director '{name}' is listed twice.")
        if (
            row.appointed_on is not None
            and row.resigned_on is not None
            and row.resigned_on < row.appointed_on
        ):
            raise CompanyDetailsRejected("Resigned date is before the appointed date.")
        seen.add(name)
        record: dict[str, object] = {
            "name": name,
            "appointed_on": None
            if row.appointed_on is None
            else row.appointed_on.isoformat(),
            "resigned_on": None
            if row.resigned_on is None
            else row.resigned_on.isoformat(),
        }
        stored.append(record)
    return stored


def _advisers(rows: list[AdviserRecord]) -> list[dict[str, object]]:
    if len(rows) > 20:
        raise CompanyDetailsRejected("Record at most 20 advisers.")
    stored: list[dict[str, object]] = []
    for row in rows:
        role = row.role.strip()
        name = row.name.strip()
        if (
            not role
            or not name
            or any(ord(char) < 32 for char in role)
            or any(ord(char) < 32 for char in name)
        ):
            raise CompanyDetailsRejected("Each adviser needs a role and a name.")
        if len(role) > 100 or len(name) > 200:
            raise CompanyDetailsRejected("An adviser role or name is too long.")
        stored.append({"role": role, "name": name})
    return stored


def _nominal(value: str) -> Decimal:
    text = value.strip()
    if not text or any(ord(char) < 32 for char in text):
        raise CompanyDetailsRejected("Nominal value must be a money amount.")
    try:
        amount = Decimal(text)
    except InvalidOperation as exc:
        raise CompanyDetailsRejected("Nominal value must be a money amount.") from exc
    if not amount.is_finite() or amount < 0:
        raise CompanyDetailsRejected("Nominal value must be a money amount.")
    cents = amount.quantize(Decimal("0.01"))
    if amount != cents:
        raise CompanyDetailsRejected("Nominal value is in whole cents.")
    return cents


def _share_classes(rows: list[ShareClassWrite]) -> list[dict[str, object]]:
    """Store the inputs. The issued amount is calculated when the note is built."""
    if len(rows) > 20:
        raise CompanyDetailsRejected("Record at most 20 share classes.")
    stored: list[dict[str, object]] = []
    seen: set[str] = set()
    for row in rows:
        name = row.class_name.strip()
        if not name or any(ord(char) < 32 for char in name):
            raise CompanyDetailsRejected("Each share class needs a name.")
        if len(name) > 100:
            raise CompanyDetailsRejected("A share class name is too long.")
        key = name.casefold()
        if key in seen:
            raise CompanyDetailsRejected(f"Share class '{name}' is listed twice.")
        seen.add(key)
        stored.append(
            {
                "class_name": name,
                "authorised_number": row.authorised_number,
                "issued_number": row.issued_number,
                "nominal_value": format(_nominal(row.nominal_value), "f"),
            }
        )
    return stored


def _issued_amount(nominal_value: str, issued_number: int) -> str:
    amount = (_nominal(nominal_value) * Decimal(issued_number)).quantize(
        Decimal("0.01")
    )
    return format(amount, "f")


def director_names(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    names: list[str] = []
    for item in value:
        if isinstance(item, dict):
            name = item.get("name")
            if isinstance(name, str) and name.strip():
                names.append(name.strip())
        elif isinstance(item, str) and item.strip():
            names.append(item.strip())
    return tuple(names)


def _signing_names(names: list[str], directors: object) -> list[str]:
    if len(names) > 40:
        raise CompanyDetailsRejected("Record at most 40 signing directors.")
    allowed = set(director_names(directors))
    stored: list[str] = []
    seen: set[str] = set()
    for raw in names:
        name = raw.strip()
        if not name:
            continue
        if name not in allowed:
            raise CompanyDetailsRejected(
                f"Signing director '{name}' is not one of the directors on the company."
            )
        if name in seen:
            raise CompanyDetailsRejected(f"Signing director '{name}' is listed twice.")
        seen.add(name)
        stored.append(name)
    return stored


def _iso(value: object) -> date | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _read_directors(value: object) -> list[DirectorRecord]:
    if not isinstance(value, list):
        return []
    rows: list[DirectorRecord] = []
    for item in value:
        if isinstance(item, str) and item.strip():
            rows.append(DirectorRecord(name=item.strip()))
            continue
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        rows.append(
            DirectorRecord(
                name=name.strip(),
                appointed_on=_iso(item.get("appointed_on")),
                resigned_on=_iso(item.get("resigned_on")),
            )
        )
    return rows


def _read_signing(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    names: list[str] = []
    for item in value:
        if isinstance(item, str) and item.strip():
            names.append(item.strip())
    return names


def _read_advisers(value: object) -> list[AdviserRecord]:
    if not isinstance(value, list):
        return []
    rows: list[AdviserRecord] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        name = item.get("name")
        if not isinstance(role, str) or not isinstance(name, str):
            continue
        if not role.strip() or not name.strip():
            continue
        rows.append(AdviserRecord(role=role.strip(), name=name.strip()))
    return rows


def _read_share_classes(value: object) -> list[ShareClassOut]:
    if not isinstance(value, list):
        return []
    rows: list[ShareClassOut] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        name = item.get("class_name")
        issued = item.get("issued_number")
        nominal = item.get("nominal_value")
        authorised = item.get("authorised_number")
        if not isinstance(name, str) or not name.strip():
            continue
        if isinstance(issued, bool) or not isinstance(issued, int):
            continue
        if not isinstance(nominal, str):
            continue
        if authorised is not None and (
            isinstance(authorised, bool) or not isinstance(authorised, int)
        ):
            continue
        try:
            issued_amount = _issued_amount(nominal, issued)
            shown_nominal = format(_nominal(nominal), "f")
        except CompanyDetailsRejected:
            continue
        rows.append(
            ShareClassOut(
                class_name=name.strip(),
                authorised_number=authorised,
                issued_number=issued,
                nominal_value=shown_nominal,
                issued_amount=issued_amount,
            )
        )
    return rows


def _share_class_audit(value: object) -> list[dict[str, object]]:
    """Class name and share counts only. Nominal value and the product stay out."""
    if not isinstance(value, list):
        return []
    rows: list[dict[str, object]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                "class_name": item.get("class_name"),
                "authorised_number": item.get("authorised_number"),
                "issued_number": item.get("issued_number"),
            }
        )
    return rows


def company_details_response(
    company: Company, year_end: YearEnd
) -> CompanyDetailsResponse:
    return CompanyDetailsResponse(
        registered_office=company.registered_office,
        business_address=company.business_address,
        company_number=company.company_number,
        incorporated_on=company.incorporated_on,
        principal_activity=company.principal_activity,
        secretary=company.secretary,
        average_employees=company.average_employees,
        directors=_read_directors(company.directors),
        advisers=_read_advisers(company.advisers),
        share_classes=_read_share_classes(company.share_classes),
        approval_date=year_end.approval_date,
        signing_directors=_read_signing(year_end.signing_directors),
    )


def _company_snapshot(company: Company) -> dict[str, object]:
    return {
        "registered_office": company.registered_office,
        "business_address": company.business_address,
        "company_number": company.company_number,
        "incorporated_on": None
        if company.incorporated_on is None
        else company.incorporated_on.isoformat(),
        "principal_activity": company.principal_activity,
        "secretary": company.secretary,
        "average_employees": company.average_employees,
        "directors": company.directors,
        "advisers": company.advisers,
        "share_classes": _share_class_audit(company.share_classes),
    }


def _approval_snapshot(year_end: YearEnd) -> dict[str, object]:
    return {
        "approval_date": None
        if year_end.approval_date is None
        else year_end.approval_date.isoformat(),
        "signing_directors": year_end.signing_directors,
    }


async def save_company_details(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    user_id: uuid.UUID | None,
    company: Company,
    year_end: YearEnd,
    body: CompanyDetailsWrite,
) -> CompanyDetailsResponse:
    previous = _company_snapshot(company)
    company.registered_office = _single_line(
        body.registered_office, label="Registered office", limit=500
    )
    company.business_address = _address(body.business_address)
    company.company_number = _company_number(body.company_number)
    company.incorporated_on = body.incorporated_on
    company.principal_activity = _single_line(
        body.principal_activity, label="Principal activity", limit=500
    )
    company.secretary = _single_line(body.secretary, label="Secretary", limit=200)
    company.average_employees = _employees(body.average_employees)
    company.directors = _directors(body.directors)
    company.advisers = _advisers(body.advisers)
    company.share_classes = _share_classes(body.share_classes)
    await append_audit_log(
        session,
        org_id=org_id,
        user_id=user_id,
        action="company_details_saved",
        entity_type="company",
        entity_id=company.id,
        old_value=previous,
        new_value=_company_snapshot(company),
    )
    return company_details_response(company, year_end)


async def save_approval_details(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    user_id: uuid.UUID | None,
    company: Company,
    year_end: YearEnd,
    body: ApprovalWrite,
) -> CompanyDetailsResponse:
    previous = _approval_snapshot(year_end)
    year_end.approval_date = body.approval_date
    year_end.signing_directors = _signing_names(
        body.signing_directors, company.directors
    )
    await append_audit_log(
        session,
        org_id=org_id,
        user_id=user_id,
        action="year_end_approval_saved",
        entity_type="year_end",
        entity_id=year_end.id,
        old_value=previous,
        new_value=_approval_snapshot(year_end),
    )
    return company_details_response(company, year_end)


def _check(code: str, severity: str, passed: bool, message: str) -> ReconciliationCheck:
    return ReconciliationCheck(
        code=code, severity=severity, passed=passed, message=message
    )


def company_detail_checks(
    company: Company, year_end: YearEnd
) -> tuple[ReconciliationCheck, ...]:
    """Dashboard facts. A missing value is not filled in."""
    names = director_names(company.directors)
    office = _blank(company.registered_office)
    number = _blank(company.company_number)
    if office and number:
        identity = _check(
            "V-CO-002",
            "WARNING",
            True,
            "Registered office and company number are recorded.",
        )
    elif office is None and number is None:
        identity = _check(
            "V-CO-002",
            "WARNING",
            False,
            "Registered office and company number have not been recorded.",
        )
    elif office is None:
        identity = _check(
            "V-CO-002",
            "WARNING",
            False,
            "Registered office has not been recorded.",
        )
    else:
        identity = _check(
            "V-CO-002",
            "WARNING",
            False,
            "Company number has not been recorded.",
        )
    signing = _read_signing(year_end.signing_directors)
    allowed = set(names)
    stranger = next((name for name in signing if name not in allowed), None)
    if stranger is not None:
        signature = _check(
            "V-CO-006",
            "WARNING",
            False,
            f"Signing director '{stranger}' is not one of the directors on the company.",
        )
    elif signing:
        signature = _check(
            "V-CO-006",
            "WARNING",
            True,
            "A signing director is recorded.",
        )
    else:
        signature = _check(
            "V-CO-006",
            "WARNING",
            False,
            "A signing director has not been recorded.",
        )
    currency = _currency_notice(company, year_end)
    checks = [
        _check(
            "V-CO-001",
            "WARNING",
            bool(names),
            "Directors are recorded." if names else "Directors have not been recorded.",
        ),
        identity,
        _check(
            "V-CO-003",
            "NOTICE",
            _blank(company.secretary) is not None,
            "The company secretary is recorded."
            if _blank(company.secretary)
            else "The company secretary has not been recorded.",
        ),
        _check(
            "V-CO-004",
            "NOTICE",
            _blank(company.principal_activity) is not None,
            "Principal activity is recorded."
            if _blank(company.principal_activity)
            else "Principal activity has not been recorded.",
        ),
        _check(
            "V-CO-005",
            "WARNING",
            year_end.approval_date is not None,
            "Approval date is recorded."
            if year_end.approval_date is not None
            else "Approval date has not been recorded.",
        ),
        signature,
    ]
    if currency is not None:
        checks.append(currency)
    return tuple(checks)


def _currency_notice(company: Company, year_end: YearEnd) -> ReconciliationCheck | None:
    """Irish pack only. A non-euro currency is a notice, never a block."""
    if year_end.pack_id != "frs102-1a-ie":
        return None
    code = company.functional_currency.strip().upper()
    if not code or code == "EUR":
        return None
    return _check(
        "V-CO-007",
        "NOTICE",
        False,
        f"Company currency is {code}. Confirm this is intended.",
    )
