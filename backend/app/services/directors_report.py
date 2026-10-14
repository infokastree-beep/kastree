"""Directors' report facts stored on the year end. Python does not calculate them.

Companies Act 2014, sections 326, 328 and 329. A blank required fact prints a
placeholder and blocks FINAL. A business review stays optional for a small
company and has no column. The wording status is researched from the public
Act. It is not a reviewer sign-off.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.company import Company
from app.schemas.company_details import (
    DirectorsReportWrite,
    HoldingOut,
    InterestEndOut,
    InterestEndWrite,
    ShareInterestOut,
)
from app.services.audit import append_audit_log
from app.services.reconciliation import ReconciliationCheck
from app.services.statutory_display import currency_symbol
from findraft.models.year_end import YearEnd

_LOCATION = "[accounting records location not recorded]"
_INTERIM = "[interim dividend not recorded]"
_RECOMMENDED = "[recommended dividend not recorded]"
_INTERESTS = "[directors' and secretary's interests in shares not recorded]"
_OWN_SHARES = "[own shares particulars not recorded]"
_EVENTS = "[subsequent events not recorded]"
_RESEARCH = "[research and development particulars not recorded]"
_POLITICAL = "[political donations particulars not recorded]"
_CENTS = Decimal("0.01")
_MAX_PEOPLE = 40
_MAX_HOLDINGS = 12
_TEXT_LIMIT = 2000


class DirectorsReportRejected(Exception):
    def __init__(self, detail: str, status_code: int = 400) -> None:
        self.detail = detail
        self.status_code = status_code
        super().__init__(detail)


@dataclass(frozen=True)
class _Holding:
    undertaking: str
    shares: int
    amount: Decimal


@dataclass(frozen=True)
class _End:
    interested: bool
    holdings: tuple[_Holding, ...]


@dataclass(frozen=True)
class _Person:
    name: str
    role: Literal["director", "secretary"]
    at_start: _End
    at_end: _End


def directors_report_paragraphs(
    year_end: YearEnd,
    company: Company | None,
    *,
    currency: str,
    disclosure_flags: Mapping[str, bool] | None = None,
) -> list[str]:
    """Sentences appended to the directors' report. Amounts are the stored facts."""
    people = _people(year_end.share_interests)
    secretary = _blank(None if company is None else company.secretary)
    directors = _director_names(None if company is None else company.directors)
    paragraphs = [
        _location_sentence(year_end.accounting_records_location),
        _dividend_sentence(
            year_end.interim_dividend,
            currency=currency,
            blank=_INTERIM,
            nil="No interim dividend was paid during the financial year.",
            paid="An interim dividend of {amount} was paid during the financial year.",
        ),
        _dividend_sentence(
            year_end.recommended_dividend,
            currency=currency,
            blank=_RECOMMENDED,
            nil="The directors do not recommend a final dividend.",
            paid="The directors recommend a final dividend of {amount}.",
        ),
        _interest_sentence(people, directors, secretary, currency),
    ]
    own = _flag(disclosure_flags, "OWN_SHARES_HELD")
    if own is True:
        paragraphs.append(
            _conditional(_blank(year_end.own_shares_particulars), _OWN_SHARES)
        )
    events = _flag(disclosure_flags, "SUBSEQUENT_EVENTS")
    if events is True:
        text = _blank(year_end.subsequent_events_particulars)
        paragraphs.append(
            _EVENTS if text is None else f"Events since the balance sheet date: {text}"
        )
    paragraphs.extend(
        _relevance(
            year_end.research_development_relevant,
            year_end.research_development_detail,
            nil="No research and development information is required to be reported.",
            lead="Research and development",
            blank=_RESEARCH,
        )
    )
    paragraphs.extend(
        _relevance(
            year_end.political_donations_relevant,
            year_end.political_donations_detail,
            nil="No political donations are required to be reported.",
            lead="Political donations",
            blank=_POLITICAL,
        )
    )
    return paragraphs


def directors_report_checks(
    company: Company,
    year_end: YearEnd,
    *,
    own_shares_held: bool | None = None,
    subsequent_events_yes: bool | None = None,
) -> tuple[ReconciliationCheck, ...]:
    """Required facts block FINAL. An unanswered optional fact does not."""
    location = _blank(year_end.accounting_records_location)
    interim = year_end.interim_dividend
    recommended = year_end.recommended_dividend
    people = _people(year_end.share_interests)
    secretary = _blank(company.secretary)
    directors = _director_names(company.directors)
    checks = [
        _check(
            "V-CO-029",
            location is not None,
            "The location of the accounting records is recorded."
            if location is not None
            else (
                "The exact location of the accounting records has not been recorded. "
                "Companies Act 2014, section 326."
            ),
        ),
        _check(
            "V-CO-030",
            interim is not None,
            "The interim dividend is recorded."
            if interim is not None
            else (
                "The interim dividend has not been recorded. "
                "Enter zero if none was paid. Companies Act 2014, section 326."
            ),
        ),
        _check(
            "V-CO-031",
            recommended is not None,
            "The recommended dividend is recorded."
            if recommended is not None
            else (
                "The recommended dividend has not been recorded. "
                "Enter zero if none is recommended. Companies Act 2014, section 326."
            ),
        ),
        _check(
            "V-CO-032",
            _interests_complete(people, directors, secretary),
            "Directors' and secretary's interests in shares are recorded."
            if _interests_complete(people, directors, secretary)
            else (
                "Directors' and secretary's interests in shares have not been "
                "recorded. Companies Act 2014, section 329."
            ),
        ),
    ]
    if own_shares_held is True:
        text = _blank(year_end.own_shares_particulars)
        checks.append(
            _check(
                "V-CO-033",
                text is not None,
                "Particulars of own shares are recorded."
                if text is not None
                else (
                    "Particulars of the company's own shares have not been recorded. "
                    "Companies Act 2014, section 328."
                ),
            )
        )
    if subsequent_events_yes is True:
        text = _blank(year_end.subsequent_events_particulars)
        checks.append(
            _check(
                "V-CO-034",
                text is not None,
                "Particulars of events since the balance sheet date are recorded."
                if text is not None
                else (
                    "Particulars of events since the balance sheet date have not "
                    "been recorded. Companies Act 2014, section 326."
                ),
            )
        )
    if year_end.research_development_relevant is True:
        detail = _blank(year_end.research_development_detail)
        checks.append(
            _check(
                "V-CO-035",
                detail is not None,
                "Research and development particulars are recorded."
                if detail is not None
                else (
                    "Research and development particulars have not been recorded. "
                    "Companies Act 2014, section 326."
                ),
            )
        )
    if year_end.political_donations_relevant is True:
        detail = _blank(year_end.political_donations_detail)
        checks.append(
            _check(
                "V-CO-036",
                detail is not None,
                "Political donation particulars are recorded."
                if detail is not None
                else (
                    "Political donation particulars have not been recorded. "
                    "Companies Act 2014, section 326."
                ),
            )
        )
    return tuple(checks)


def share_interests_out(value: object) -> list[ShareInterestOut]:
    """Stored interests for the form. A malformed value is shown as empty."""
    people = _people(value)
    if people is None:
        return []
    return [
        ShareInterestOut(
            name=person.name,
            role=person.role,
            at_start=_end_out(person.at_start),
            at_end=_end_out(person.at_end),
        )
        for person in people
    ]


def money_text(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return format(value.quantize(_CENTS, rounding=ROUND_HALF_UP), "f")


async def save_directors_report(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    user_id: uuid.UUID | None,
    year_end: YearEnd,
    body: DirectorsReportWrite,
) -> None:
    """Store the typed facts. The audit row names what was recorded, not amounts."""
    previous = _audit_snapshot(year_end)
    year_end.accounting_records_location = _prose(
        body.accounting_records_location, label="Accounting records location"
    )
    year_end.interim_dividend = _money(body.interim_dividend, label="Interim dividend")
    year_end.recommended_dividend = _money(
        body.recommended_dividend, label="Recommended dividend"
    )
    year_end.share_interests = _stored_interests(body)
    year_end.own_shares_particulars = _prose(
        body.own_shares_particulars, label="Own shares particulars"
    )
    year_end.subsequent_events_particulars = _prose(
        body.subsequent_events_particulars, label="Subsequent events particulars"
    )
    year_end.research_development_relevant = body.research_development_relevant
    year_end.research_development_detail = _detail(
        body.research_development_relevant,
        body.research_development_detail,
        label="Research and development",
    )
    year_end.political_donations_relevant = body.political_donations_relevant
    year_end.political_donations_detail = _detail(
        body.political_donations_relevant,
        body.political_donations_detail,
        label="Political donations",
    )
    year_end.accounting_period_change_filed = body.accounting_period_change_filed
    await append_audit_log(
        session,
        org_id=org_id,
        user_id=user_id,
        action="directors_report_saved",
        entity_type="year_end",
        entity_id=year_end.id,
        old_value=previous,
        new_value=_audit_snapshot(year_end),
    )


def _check(code: str, passed: bool, message: str) -> ReconciliationCheck:
    return ReconciliationCheck(
        code=code, severity="WARNING", passed=passed, message=message
    )


def _blank(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    return text or None


def _flag(flags: Mapping[str, bool] | None, name: str) -> bool | None:
    if flags is None or name not in flags:
        return None
    return bool(flags[name])


def _director_names(value: object) -> tuple[str, ...]:
    from app.services.company_details import director_names

    return director_names(value)


def _prose(value: str | None, *, label: str) -> str | None:
    text = _blank(value)
    if text is None:
        return None
    if any(ord(char) < 32 and char != "\n" for char in text):
        raise DirectorsReportRejected(
            f"{label} contains a character that cannot be stored."
        )
    if len(text) > _TEXT_LIMIT:
        raise DirectorsReportRejected(f"{label} is too long.")
    return text


def _money(value: str | None, *, label: str) -> Decimal | None:
    text = _blank(value)
    if text is None:
        return None
    cleaned = (
        text.replace(",", "")
        .replace("€", "")
        .replace("£", "")
        .replace("$", "")
        .replace(" ", "")
    )
    if cleaned.startswith("(") and cleaned.endswith(")"):
        cleaned = "-" + cleaned[1:-1]
    try:
        amount = Decimal(cleaned)
    except InvalidOperation as exc:
        raise DirectorsReportRejected(f"{label} must be a decimal amount.") from exc
    cents = amount.quantize(_CENTS, rounding=ROUND_HALF_UP)
    if cents != amount:
        raise DirectorsReportRejected(f"{label} must be in cents.")
    return cents


def _detail(relevant: bool | None, value: str | None, *, label: str) -> str | None:
    if relevant is not True:
        return None
    return _prose(value, label=label)


def _stored_interests(body: DirectorsReportWrite) -> list[dict[str, object]] | None:
    if len(body.share_interests) > _MAX_PEOPLE:
        raise DirectorsReportRejected("Record at most 40 people with share interests.")
    seen: set[tuple[str, str]] = set()
    stored: list[dict[str, object]] = []
    for person in body.share_interests:
        name = person.name.strip()
        key = (name.casefold(), person.role)
        if key in seen:
            raise DirectorsReportRejected(
                "Each director and the secretary is recorded once."
            )
        seen.add(key)
        stored.append(
            {
                "name": name,
                "role": person.role,
                "at_start": _stored_end(person.at_start),
                "at_end": _stored_end(person.at_end),
            }
        )
    return stored or None


def _stored_end(end: InterestEndWrite) -> dict[str, object]:
    if not end.interested and end.holdings:
        raise DirectorsReportRejected(
            "A person with no interest does not record a holding."
        )
    if end.interested and not end.holdings:
        raise DirectorsReportRejected(
            "Record the shares and the amount for each interest."
        )
    if len(end.holdings) > _MAX_HOLDINGS:
        raise DirectorsReportRejected("Record at most 12 holdings for one person.")
    rows: list[dict[str, object]] = []
    for holding in end.holdings:
        amount = _money(holding.amount, label="Share interest amount")
        if amount is None:
            raise DirectorsReportRejected("Record the amount of each share interest.")
        rows.append(
            {
                "undertaking": holding.undertaking.strip(),
                "shares": holding.shares,
                "amount": format(amount, "f"),
            }
        )
    return {"interested": end.interested, "holdings": rows}


def _people(value: object) -> tuple[_Person, ...] | None:
    if value is None:
        return None
    if not isinstance(value, list):
        return None
    people: list[_Person] = []
    for item in value:
        person = _person(item)
        if person is None:
            return None
        people.append(person)
    return tuple(people)


def _person(value: object) -> _Person | None:
    if not isinstance(value, dict):
        return None
    name = value.get("name")
    role = value.get("role")
    if not isinstance(name, str) or not name.strip():
        return None
    if role not in {"director", "secretary"}:
        return None
    start = _end(value.get("at_start"))
    end = _end(value.get("at_end"))
    if start is None or end is None:
        return None
    return _Person(name=name.strip(), role=role, at_start=start, at_end=end)


def _end(value: object) -> _End | None:
    if not isinstance(value, dict) or not isinstance(value.get("interested"), bool):
        return None
    raw = value.get("holdings")
    if not isinstance(raw, list):
        return None
    holdings: list[_Holding] = []
    for item in raw:
        holding = _holding(item)
        if holding is None:
            return None
        holdings.append(holding)
    interested = bool(value["interested"])
    if interested and not holdings:
        return None
    if not interested and holdings:
        return None
    return _End(interested=interested, holdings=tuple(holdings))


def _holding(value: object) -> _Holding | None:
    if not isinstance(value, dict):
        return None
    undertaking = value.get("undertaking")
    shares = value.get("shares")
    amount = value.get("amount")
    if not isinstance(undertaking, str) or not undertaking.strip():
        return None
    if isinstance(shares, bool) or not isinstance(shares, int) or shares < 0:
        return None
    if not isinstance(amount, str):
        return None
    try:
        parsed = Decimal(amount)
    except InvalidOperation:
        return None
    cents = parsed.quantize(_CENTS, rounding=ROUND_HALF_UP)
    if cents != parsed:
        return None
    return _Holding(undertaking=undertaking.strip(), shares=shares, amount=cents)


def _end_out(end: _End) -> InterestEndOut:
    return InterestEndOut(
        interested=end.interested,
        holdings=[
            HoldingOut(
                undertaking=holding.undertaking,
                shares=holding.shares,
                amount=format(holding.amount, "f"),
            )
            for holding in end.holdings
        ],
    )


def _interests_complete(
    people: tuple[_Person, ...] | None,
    directors: tuple[str, ...],
    secretary: str | None,
) -> bool:
    if people is None:
        return False
    needed = {(name.casefold(), "director") for name in directors}
    if secretary is not None:
        needed.add((secretary.casefold(), "secretary"))
    if not needed:
        return False
    found = {(person.name.casefold(), person.role) for person in people}
    return needed <= found


def _location_sentence(value: str | None) -> str:
    location = _blank(value)
    if location is None:
        return _LOCATION
    return (
        "The directors have taken the measures necessary to secure compliance "
        "with sections 281 to 285 of the Companies Act 2014. "
        f"The accounting records are kept at {location}."
    )


def _dividend_sentence(
    value: Decimal | None,
    *,
    currency: str,
    blank: str,
    nil: str,
    paid: str,
) -> str:
    if value is None:
        return blank
    if abs(value) <= _CENTS:
        return nil
    return paid.format(amount=_money_phrase(value, currency))


def _interest_sentence(
    people: tuple[_Person, ...] | None,
    directors: tuple[str, ...],
    secretary: str | None,
    currency: str,
) -> str:
    if not _interests_complete(people, directors, secretary) or people is None:
        return _INTERESTS
    if all(
        not person.at_start.interested and not person.at_end.interested
        for person in people
    ):
        if secretary is None:
            return (
                "No director had an interest in the shares of the company, or of "
                "any group undertaking, at the beginning or the end of the "
                "financial year."
            )
        return (
            "No director and the secretary had an interest in the shares of the "
            "company, or of any group undertaking, at the beginning or the end "
            "of the financial year."
        )
    return " ".join(_person_sentence(person, currency) for person in people)


def _person_sentence(person: _Person, currency: str) -> str:
    role = "director" if person.role == "director" else "secretary"
    return (
        f"{person.name}, {role}: {_end_sentence(person.at_start, currency, 'beginning')}"
        f" {_end_sentence(person.at_end, currency, 'end')}"
    )


def _end_sentence(end: _End, currency: str, when: str) -> str:
    if not end.interested:
        return f"no interest at the {when}."
    parts = [
        (
            f"{holding.shares:,} shares in {holding.undertaking} "
            f"({_money_phrase(holding.amount, currency)})"
        )
        for holding in end.holdings
    ]
    return f"at the {when}, {'; '.join(parts)}."


def _conditional(text: str | None, placeholder: str) -> str:
    if text is None:
        return placeholder
    return text


def _relevance(
    relevant: bool | None,
    detail: str | None,
    *,
    nil: str,
    lead: str,
    blank: str,
) -> list[str]:
    if relevant is None:
        return []
    if relevant is False:
        return [nil]
    text = _blank(detail)
    if text is None:
        return [blank]
    return [f"{lead}: {text}"]


_DIVIDEND_NOTE_NIL = (
    "No dividend was paid during the financial year and the directors "
    "do not recommend a dividend."
)
_DIVIDEND_NOTE_INTERIM_NIL = "No interim dividend was paid during the financial year."
_DIVIDEND_NOTE_INTERIM_PAID = (
    "An interim dividend of {amount} was paid during the financial year."
)
_DIVIDEND_NOTE_RECOMMENDED_NIL = "The directors do not recommend a dividend."
_DIVIDEND_NOTE_RECOMMENDED_PAID = "A dividend of {amount} is recommended."


def dividend_note_paragraphs(
    interim: Decimal | None,
    recommended: Decimal | None,
    *,
    currency: str,
) -> tuple[str, ...] | None:
    """1AD.35 from the recorded interim and recommended amounts.

    A blank is not a nil. Both amounts must be recorded before the note
    prints. Zero is the recorded nil. These amounts are not the
    trial-balance dividends line, and they are not added together.
    The wording is researched (public source). It is not a reviewer sign-off.
    """
    if interim is None or recommended is None:
        return None
    interim_nil = abs(interim) <= _CENTS
    recommended_nil = abs(recommended) <= _CENTS
    if interim_nil and recommended_nil:
        return (_DIVIDEND_NOTE_NIL,)
    parts: list[str] = []
    if interim_nil:
        parts.append(_DIVIDEND_NOTE_INTERIM_NIL)
    else:
        parts.append(
            _DIVIDEND_NOTE_INTERIM_PAID.format(amount=_money_phrase(interim, currency))
        )
    if recommended_nil:
        parts.append(_DIVIDEND_NOTE_RECOMMENDED_NIL)
    else:
        parts.append(
            _DIVIDEND_NOTE_RECOMMENDED_PAID.format(
                amount=_money_phrase(recommended, currency)
            )
        )
    return tuple(parts)


def _money_phrase(amount: Decimal, currency: str) -> str:
    cents = amount.quantize(_CENTS, rounding=ROUND_HALF_UP)
    negative = cents < 0
    text = f"{abs(cents):,.2f}"
    symbol = currency_symbol(currency)
    shown = f"{symbol}{text}" if symbol else text
    if negative:
        return f"({shown})"
    return shown


def _audit_snapshot(year_end: YearEnd) -> dict[str, object]:
    """Who and what was answered. Amounts and particulars stay off this row."""
    people = _people(year_end.share_interests)
    interests: list[dict[str, object]] = []
    if people is not None:
        interests = [
            {
                "name": person.name,
                "role": person.role,
                "at_start_interested": person.at_start.interested,
                "at_end_interested": person.at_end.interested,
            }
            for person in people
        ]
    return {
        "accounting_records_location": year_end.accounting_records_location,
        "interim_dividend_recorded": year_end.interim_dividend is not None,
        "recommended_dividend_recorded": year_end.recommended_dividend is not None,
        "share_interests": interests,
        "own_shares_particulars_recorded": _blank(year_end.own_shares_particulars)
        is not None,
        "subsequent_events_particulars_recorded": _blank(
            year_end.subsequent_events_particulars
        )
        is not None,
        "research_development_relevant": year_end.research_development_relevant,
        "research_development_detail_recorded": _blank(
            year_end.research_development_detail
        )
        is not None,
        "political_donations_relevant": year_end.political_donations_relevant,
        "political_donations_detail_recorded": _blank(
            year_end.political_donations_detail
        )
        is not None,
        "accounting_period_change_filed": year_end.accounting_period_change_filed,
    }
