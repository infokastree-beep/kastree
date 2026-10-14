"""Company letterhead and this year's approval. No figures are calculated here."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.company import Company
from app.schemas.company_details import (
    AdviserRecord,
    ApprovalWrite,
    CompanyDetailsResponse,
    CompilationWrite,
    CompanyDetailsWrite,
    CurrencyConfirmationResponse,
    DirectorRecord,
    ShareClassOut,
    ShareClassWrite,
)
from app.services.audit import append_audit_log
from app.services.directors_report import (
    directors_report_checks,
    money_text,
    share_interests_out,
)
from app.services.legal_forms import record_legal_form_change
from app.services.countries import country_label
from app.services.reconciliation import ReconciliationCheck
from findraft.models.year_end import YearEnd

_BLOCKING = frozenset(
    {
        "V-CO-001",
        "V-CO-002",
        "V-CO-004",
        "V-CO-005",
        "V-CO-006",
        "V-CO-008",
        "V-CO-009",
        "V-CO-010",
        "V-CO-011",
        "V-CO-037",
        "V-CO-020",
        "V-CO-022",
        "V-CO-023",
        "V-CO-024",
        "V-CO-029",
        "V-CO-030",
        "V-CO-031",
        "V-CO-032",
        "V-CO-033",
        "V-CO-034",
        "V-CO-035",
        "V-CO-036",
        "V-CO-038",
        "V-CO-039",
        "V-CO-040",
        "V-CO-041",
        "V-CO-042",
        "V-CO-043",
    }
)
_AUDIT_NOT_RECORDED = (
    "The audit position has not been recorded. "
    "Record whether the audit exemption is claimed."
)
_AUDIT_REQUIRED = "An audit is required. An auditor's report is out of scope."
_AUDIT_SIZE_MISSING = (
    "The size test has not been recorded. "
    "Record it before the audit exemption can be evidenced."
)
_AUDIT_NOT_EVIDENCED = (
    "The recorded size test does not evidence the audit exemption. "
    "An audit is required. An auditor's report is out of scope."
)
_AUDIT_CLAIMED = "The audit exemption is claimed and the size test is recorded."
_EXCLUDED_MISSING = (
    "Record the directors' confirmation that the company is not an excluded class "
    "(Fifth Schedule to the Companies Act 2014)."
)
_EXCLUDED_REFUSED = (
    "The company is recorded as an excluded class. "
    "The audit exemption is not available."
)
_EXCLUDED_RECORDED = (
    "The directors have recorded that the company is not an excluded class."
)
_NOTICE_MISSING = (
    "Record the directors' confirmation that no notice under section 334 "
    "of the Companies Act 2014 has been served."
)
_NOTICE_REFUSED = (
    "A notice under section 334 is recorded. The audit exemption is not available."
)
_NOTICE_RECORDED = (
    "The directors have recorded that no notice under section 334 has been served."
)
_RETURNS_MISSING = (
    "Record the directors' confirmation that annual returns were not filed late "
    "more than once in five years (section 363 of the Companies Act 2014, "
    "as substituted by section 22 of the Companies (Corporate Governance, "
    "Enforcement and Regulatory Provisions) Act 2024)."
)
_RETURNS_REFUSED = (
    "Annual returns are recorded as filed late more than once in five years. "
    "The audit exemption is not available."
)
_RETURNS_RECORDED = (
    "The directors have recorded that annual returns were not filed late "
    "more than once in five years."
)
MISSING_INCORPORATION = "Country of incorporation not recorded"


def foreign_pack_message(country: str | None) -> str:
    """Name the stored country. A code with no English name stays as stored."""
    recorded = country_label(country)
    if recorded == "":
        recorded = "not recorded"
    return (
        "This pack is for a company incorporated in Ireland. "
        f"Country of incorporation is recorded as {recorded}. "
        "No other country's pack is available."
    )


_IRISH_PACK = "frs102-1a-ie"


class CompanyDetailsRejected(Exception):
    def __init__(self, detail: str, status_code: int = 400) -> None:
        self.detail = detail
        self.status_code = status_code
        super().__init__(detail)


def blocks_final(checks: tuple[ReconciliationCheck, ...]) -> bool:
    return any(not item.passed and item.code in _BLOCKING for item in checks)


def incorporation_gate(
    country: str | None, pack_id: str
) -> Literal["open", "missing", "foreign"]:
    """Irish pack only. IE is unchanged. NULL is missing. Any other code is foreign."""
    if pack_id != _IRISH_PACK:
        return "open"
    code = "" if country is None else country.strip().upper()
    if code == "":
        return "missing"
    if code == "IE":
        return "open"
    return "foreign"


def incorporation_output_message(
    country: str | None, pack_id: str, *, final: bool
) -> str | None:
    """Message that blocks this output, or none when the output may proceed.

    A missing country blocks FINAL only. A country other than Ireland blocks
    the draft as well as FINAL, PDF, and Word.
    """
    gate = incorporation_gate(country, pack_id)
    if gate == "foreign":
        return foreign_pack_message(country)
    if gate == "missing" and final:
        return MISSING_INCORPORATION
    return None


async def incorporation_output_message_for_year_end(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    year_end: YearEnd,
    final: bool,
) -> str | None:
    company = await session.get(Company, year_end.company_id)
    country = None
    if company is not None and company.org_id == org_id and not company.is_deleted:
        country = company.country_of_incorporation
    return incorporation_output_message(country, year_end.pack_id, final=final)


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


_ONE_SIGNATORY = "A signing director is recorded."
_TWO_SIGNATORIES = "Two signing directors are recorded."
_NO_SIGNATORY = "A signing director has not been recorded."
_TWO_REQUIRED = (
    "Two directors must sign the balance sheet and the directors' report. "
    "Companies Act 2014, sections 324 and 332."
)
_RESIGNED_SIGNATORY = "The signing director has to be a director still in office."


def current_director_names(value: object) -> tuple[str, ...]:
    """Directors still in office. A resigned director does not sign."""
    if not isinstance(value, list):
        return ()
    names: list[str] = []
    for item in value:
        if isinstance(item, str) and item.strip():
            names.append(item.strip())
            continue
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        resigned = item.get("resigned_on")
        if isinstance(resigned, str) and resigned.strip():
            continue
        names.append(name.strip())
    return tuple(names)


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
        country_of_incorporation=company.country_of_incorporation,
        legal_form=company.legal_form,
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
        accounting_records_location=year_end.accounting_records_location,
        interim_dividend=money_text(year_end.interim_dividend),
        recommended_dividend=money_text(year_end.recommended_dividend),
        share_interests=share_interests_out(year_end.share_interests),
        own_shares_particulars=year_end.own_shares_particulars,
        subsequent_events_particulars=year_end.subsequent_events_particulars,
        research_development_relevant=year_end.research_development_relevant,
        research_development_detail=year_end.research_development_detail,
        political_donations_relevant=year_end.political_donations_relevant,
        political_donations_detail=year_end.political_donations_detail,
        accounting_period_change_filed=year_end.accounting_period_change_filed,
        compilation_date=year_end.compilation_date,
        compilation_signatory=year_end.compilation_signatory,
        related_party_particulars=year_end.related_party_particulars,
        directors_remuneration_particulars=year_end.directors_remuneration_particulars,
        loan_terms_particulars=year_end.loan_terms_particulars,
        guarantee_particulars=year_end.guarantee_particulars,
    )


def _company_snapshot(company: Company) -> dict[str, object]:
    return {
        "country_of_incorporation": company.country_of_incorporation,
        "legal_form": company.legal_form,
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
    role: str,
    company: Company,
    year_end: YearEnd,
    body: CompanyDetailsWrite,
) -> CompanyDetailsResponse:
    previous = _company_snapshot(company)
    previous_form = company.legal_form
    if "country_of_incorporation" in body.model_fields_set:
        company.country_of_incorporation = body.country_of_incorporation
    if "legal_form" in body.model_fields_set:
        if body.legal_form != company.legal_form and role not in {"owner", "admin"}:
            raise CompanyDetailsRejected(
                "Only an owner or an administrator can change the legal form.",
                status_code=403,
            )
        company.legal_form = body.legal_form
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
    await record_legal_form_change(
        session,
        org_id=org_id,
        user_id=user_id,
        company_id=company.id,
        previous=previous_form,
        current=company.legal_form,
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


def _compilation_snapshot(year_end: YearEnd) -> dict[str, object]:
    recorded = year_end.compilation_date
    return {
        "compilation_date": None if recorded is None else recorded.isoformat(),
        "compilation_signatory": year_end.compilation_signatory,
    }


async def save_compilation_report(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    user_id: uuid.UUID | None,
    company: Company,
    year_end: YearEnd,
    body: CompilationWrite,
) -> CompanyDetailsResponse:
    """Store the practice compilation date and signatory. Amounts stay out."""
    previous = _compilation_snapshot(year_end)
    year_end.compilation_date = body.compilation_date
    year_end.compilation_signatory = _single_line(
        body.compilation_signatory, label="Compilation signatory", limit=200
    )
    await append_audit_log(
        session,
        org_id=org_id,
        user_id=user_id,
        action="compilation_report_saved",
        entity_type="year_end",
        entity_id=year_end.id,
        old_value=previous,
        new_value=_compilation_snapshot(year_end),
    )
    return company_details_response(company, year_end)


def _confirmation_snapshot(year_end: YearEnd) -> dict[str, object]:
    confirmed_at = year_end.currency_confirmed_at
    confirmed_by = year_end.currency_confirmed_by_user_id
    return {
        "currency": year_end.currency_confirmed_code,
        "confirmed_at": None if confirmed_at is None else confirmed_at.isoformat(),
        "confirmed_by_user_id": None if confirmed_by is None else str(confirmed_by),
    }


async def confirm_currency(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    company: Company,
    year_end: YearEnd,
) -> CurrencyConfirmationResponse:
    """Record that this year end reports in the company's currency.

    The company currency is copied as a label. Amounts are not converted.
    """
    code = company.functional_currency.strip().upper()
    if not code:
        raise CompanyDetailsRejected("Company currency is not recorded.")
    previous = _confirmation_snapshot(year_end)
    confirmed_at = datetime.now(UTC)
    year_end.currency_confirmed_code = code
    year_end.currency_confirmed_by_user_id = user_id
    year_end.currency_confirmed_at = confirmed_at
    await append_audit_log(
        session,
        org_id=org_id,
        user_id=user_id,
        action="currency_confirmed",
        entity_type="year_end",
        entity_id=year_end.id,
        old_value=previous,
        new_value=_confirmation_snapshot(year_end),
    )
    return CurrencyConfirmationResponse(
        year_end_id=year_end.id,
        currency=code,
        confirmed_at=confirmed_at,
        confirmed_by_user_id=user_id,
    )


def _signature_check(directors: object, signing_value: object) -> ReconciliationCheck:
    """One signature for a sole director. Two when two or more are in office.

    Sections 324 and 332 of the Companies Act 2014. The citation is researched
    from the public Act and is not a reviewer sign-off.
    """
    signing = _read_signing(signing_value)
    allowed = set(director_names(directors))
    stranger = next((name for name in signing if name not in allowed), None)
    if stranger is not None:
        return _check(
            "V-CO-006",
            "WARNING",
            False,
            f"Signing director '{stranger}' is not one of the directors on the company.",
        )
    current = set(current_director_names(directors))
    qualifying = [name for name in signing if name in current]
    required = 2 if len(current) >= 2 else 1
    if len(qualifying) >= required:
        recorded = _TWO_SIGNATORIES if required == 2 else _ONE_SIGNATORY
        return _check("V-CO-006", "WARNING", True, recorded)
    if required == 2:
        return _check("V-CO-006", "WARNING", False, _TWO_REQUIRED)
    if signing:
        return _check("V-CO-006", "WARNING", False, _RESIGNED_SIGNATORY)
    return _check("V-CO-006", "WARNING", False, _NO_SIGNATORY)


def _check(code: str, severity: str, passed: bool, message: str) -> ReconciliationCheck:
    return ReconciliationCheck(
        code=code, severity=severity, passed=passed, message=message
    )


def _practice_letterhead_check(
    name: str | None,
    address: str | None,
    contact: str | None,
) -> ReconciliationCheck:
    missing = [
        label
        for label, value in (
            ("legal name", name),
            ("address", address),
            ("contact", contact),
        )
        if _blank(value) is None
    ]
    if not missing:
        return _check(
            "V-CO-038",
            "WARNING",
            True,
            "The practice letterhead is recorded.",
        )
    if len(missing) == 3:
        sentence = (
            "The practice legal name, address, and contact have not been recorded."
        )
    elif len(missing) == 2:
        sentence = f"The practice {missing[0]} and {missing[1]} have not been recorded."
    else:
        sentence = f"The practice {missing[0]} has not been recorded."
    return _check("V-CO-038", "WARNING", False, sentence)


def _compilation_check(year_end: YearEnd) -> ReconciliationCheck:
    """Both facts are one blocker. A blank signatory is the same as a missing one."""
    date_missing = year_end.compilation_date is None
    signatory_missing = _blank(year_end.compilation_signatory) is None
    if not date_missing and not signatory_missing:
        return _check(
            "V-CO-039",
            "WARNING",
            True,
            "The compilation date and signatory are recorded.",
        )
    if date_missing and signatory_missing:
        message = "The compilation date and signatory have not been recorded."
    elif date_missing:
        message = "The compilation date has not been recorded."
    else:
        message = "The compilation signatory has not been recorded."
    return _check("V-CO-039", "WARNING", False, message)


def company_detail_checks(
    company: Company,
    year_end: YearEnd,
    *,
    turnover: Decimal | None = None,
    profit_before_tax: Decimal | None = None,
    tax_charge: Decimal | None = None,
    corporation_tax: Decimal | None = None,
    subsequent_events_answered: bool | None = None,
    own_shares_held: bool | None = None,
    subsequent_events_yes: bool | None = None,
    practice_name: str | None = None,
    practice_address: str | None = None,
    practice_contact: str | None = None,
    disclosure_flags: Mapping[str, bool] | None = None,
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
    signature = _signature_check(company.directors, year_end.signing_directors)
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
            "WARNING",
            _blank(company.principal_activity) is not None,
            "Principal activity is recorded."
            if _blank(company.principal_activity)
            else (
                "Principal activities have not been recorded. "
                "Companies Act 2014, section 326."
            ),
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
    gate = incorporation_gate(company.country_of_incorporation, year_end.pack_id)
    if gate == "missing":
        checks.append(_check("V-CO-008", "NOTICE", False, MISSING_INCORPORATION))
    elif gate == "foreign":
        checks.append(
            _check(
                "V-CO-009",
                "BLOCKED",
                False,
                foreign_pack_message(company.country_of_incorporation),
            )
        )
    from app.services.company_data_checks import company_data_checks

    checks.extend(
        company_data_checks(
            company,
            year_end,
            turnover=turnover,
            profit_before_tax=profit_before_tax,
            tax_charge=tax_charge,
            corporation_tax=corporation_tax,
            subsequent_events_answered=subsequent_events_answered,
        )
    )
    checks.extend(
        directors_report_checks(
            company,
            year_end,
            own_shares_held=own_shares_held,
            subsequent_events_yes=subsequent_events_yes,
        )
    )
    from app.services.particulars import particulars_checks

    checks.extend(particulars_checks(year_end, disclosure_flags))
    checks.extend(audit_position_checks(year_end))
    checks.append(
        _practice_letterhead_check(practice_name, practice_address, practice_contact)
    )
    checks.append(_compilation_check(year_end))
    return tuple(checks)


def _claim_snapshot(year_end: YearEnd) -> dict[str, object]:
    """Who, when, and the three-state value. Amounts stay off this log."""
    actor = year_end.audit_exemption_claimed_by_user_id
    claimed_at = year_end.audit_exemption_claimed_at
    return {
        "claimed": year_end.audit_exemption_claimed,
        "claimed_by_user_id": None if actor is None else str(actor),
        "claimed_at": None if claimed_at is None else claimed_at.isoformat(),
    }


def _claim_never_recorded(year_end: YearEnd) -> bool:
    return (
        year_end.audit_exemption_claimed is None
        and year_end.audit_exemption_claimed_by_user_id is None
        and year_end.audit_exemption_claimed_at is None
    )


async def record_audit_exemption(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    year_end: YearEnd,
    claimed: bool | None,
) -> YearEnd:
    """Store claimed, not claimed, or clear the position back to not recorded."""
    previous = None if _claim_never_recorded(year_end) else _claim_snapshot(year_end)
    if claimed is None:
        year_end.audit_exemption_claimed = None
        year_end.audit_exemption_claimed_by_user_id = None
        year_end.audit_exemption_claimed_at = None
    else:
        year_end.audit_exemption_claimed = claimed
        year_end.audit_exemption_claimed_by_user_id = user_id
        year_end.audit_exemption_claimed_at = datetime.now(UTC)
    await append_audit_log(
        session,
        org_id=org_id,
        user_id=user_id,
        action="audit_exemption_claimed",
        entity_type="year_end",
        entity_id=year_end.id,
        old_value=previous,
        new_value=_claim_snapshot(year_end),
    )
    await session.flush()
    return year_end


def _conditions_snapshot(year_end: YearEnd) -> dict[str, object]:
    """Who, when, and the three confirmations. Amounts stay off this log."""
    actor = year_end.audit_exemption_conditions_by_user_id
    recorded_at = year_end.audit_exemption_conditions_at
    return {
        "not_excluded": year_end.audit_exemption_not_excluded,
        "no_member_notice": year_end.audit_exemption_no_member_notice,
        "returns_not_late": year_end.audit_exemption_returns_not_late,
        "conditions_by_user_id": None if actor is None else str(actor),
        "conditions_at": None if recorded_at is None else recorded_at.isoformat(),
    }


def _conditions_never_recorded(year_end: YearEnd) -> bool:
    return (
        year_end.audit_exemption_not_excluded is None
        and year_end.audit_exemption_no_member_notice is None
        and year_end.audit_exemption_returns_not_late is None
        and year_end.audit_exemption_conditions_by_user_id is None
        and year_end.audit_exemption_conditions_at is None
    )


async def record_audit_exemption_conditions(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    year_end: YearEnd,
    not_excluded: bool | None,
    no_member_notice: bool | None,
    returns_not_late: bool | None,
) -> YearEnd:
    """Store the three directors' confirmations, or clear them back to not recorded."""
    values = (not_excluded, no_member_notice, returns_not_late)
    if any(item is None for item in values) and any(
        item is not None for item in values
    ):
        raise CompanyDetailsRejected(
            "Record all three directors' confirmations together, or clear them together."
        )
    previous = (
        None if _conditions_never_recorded(year_end) else _conditions_snapshot(year_end)
    )
    if not_excluded is None:
        year_end.audit_exemption_not_excluded = None
        year_end.audit_exemption_no_member_notice = None
        year_end.audit_exemption_returns_not_late = None
        year_end.audit_exemption_conditions_by_user_id = None
        year_end.audit_exemption_conditions_at = None
    else:
        year_end.audit_exemption_not_excluded = not_excluded
        year_end.audit_exemption_no_member_notice = no_member_notice
        year_end.audit_exemption_returns_not_late = returns_not_late
        year_end.audit_exemption_conditions_by_user_id = user_id
        year_end.audit_exemption_conditions_at = datetime.now(UTC)
    await append_audit_log(
        session,
        org_id=org_id,
        user_id=user_id,
        action="audit_exemption_conditions",
        entity_type="year_end",
        entity_id=year_end.id,
        old_value=previous,
        new_value=_conditions_snapshot(year_end),
    )
    await session.flush()
    return year_end


def _confirmation_check(
    code: str,
    value: bool | None,
    missing: str,
    refused: str,
    recorded: str,
) -> ReconciliationCheck:
    if value is True:
        return _check(code, "WARNING", True, recorded)
    if value is False:
        return _check(code, "WARNING", False, refused)
    return _check(code, "WARNING", False, missing)


def _confirmation_checks(year_end: YearEnd) -> tuple[ReconciliationCheck, ...]:
    """Each directors' confirmation is its own check. NULL and false both fail."""
    return (
        _confirmation_check(
            "V-CO-022",
            year_end.audit_exemption_not_excluded,
            _EXCLUDED_MISSING,
            _EXCLUDED_REFUSED,
            _EXCLUDED_RECORDED,
        ),
        _confirmation_check(
            "V-CO-023",
            year_end.audit_exemption_no_member_notice,
            _NOTICE_MISSING,
            _NOTICE_REFUSED,
            _NOTICE_RECORDED,
        ),
        _confirmation_check(
            "V-CO-024",
            year_end.audit_exemption_returns_not_late,
            _RETURNS_MISSING,
            _RETURNS_REFUSED,
            _RETURNS_RECORDED,
        ),
    )


def audit_position_checks(year_end: YearEnd) -> tuple[ReconciliationCheck, ...]:
    """NULL, false, and true are different. A notice does not block FINAL."""
    claimed = year_end.audit_exemption_claimed
    if claimed is None:
        position: tuple[ReconciliationCheck, ...] = (
            _check("V-CO-020", "WARNING", False, _AUDIT_NOT_RECORDED),
        )
    elif claimed is False:
        position = (_check("V-CO-020", "WARNING", False, _AUDIT_REQUIRED),)
    elif year_end.size_checked_at is None:
        position = (_check("V-CO-020", "WARNING", False, _AUDIT_SIZE_MISSING),)
    elif year_end.size_eligible is not True:
        position = (_check("V-CO-020", "WARNING", False, _AUDIT_NOT_EVIDENCED),)
    else:
        checks = [_check("V-CO-020", "WARNING", True, _AUDIT_CLAIMED)]
        condition_failed = (
            year_end.size_current_met is not None and year_end.size_current_met < 3
        ) or (
            year_end.size_preceding_met is not None and year_end.size_preceding_met < 3
        )
        if condition_failed:
            checks.append(
                _check(
                    "V-CO-021",
                    "NOTICE",
                    False,
                    year_end.size_message or "",
                )
            )
        position = tuple(checks)
    if claimed is True:
        return position + _confirmation_checks(year_end)
    return position


def _currency_notice(company: Company, year_end: YearEnd) -> ReconciliationCheck | None:
    """Irish pack only. A non-euro currency is a notice, never a block.

    A confirmation applies only while it names the company's current currency.
    """
    if year_end.pack_id != "frs102-1a-ie":
        return None
    code = company.functional_currency.strip().upper()
    if not code or code == "EUR":
        return None
    confirmed = (year_end.currency_confirmed_code or "").strip().upper()
    if confirmed == code:
        return None
    return _check(
        "V-CO-007",
        "NOTICE",
        False,
        f"Company currency is {code}. Confirm this is intended.",
    )
