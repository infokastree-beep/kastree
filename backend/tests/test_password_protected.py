"""Password-protected upload detection (PDF + Excel) with generic-fallback checks."""

from __future__ import annotations

from datetime import date

import pytest

from app.services.gl_to_tb import GlToTbError, convert_gl_file_to_tb, parse_gl_pdf
from app.services.parser import (
    PASSWORD_PROTECTED_MESSAGE,
    ParseError,
    PasswordProtectedError,
    looks_like_encrypted_office,
    parse_tb_file,
    pdf_is_password_protected,
)
from app.services.pdf_tb_extract import PdfTbExtractError, extract_trial_balance_from_pdf

# OLE2 / Compound-File-Binary signature — the first 8 bytes of every
# password-encrypted OOXML (.xlsx) workbook (a normal .xlsx starts with "PK").
OLE2_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


def _encrypted_pdf_bytes(user_pw: str = "secret") -> bytes:
    import fitz

    doc = fitz.open()
    doc.new_page().insert_text((72, 72), "Confidential")
    return doc.tobytes(encryption=fitz.PDF_ENCRYPT_AES_256, owner_pw="owner", user_pw=user_pw)


def _plain_pdf_bytes() -> bytes:
    import fitz

    doc = fitz.open()
    doc.new_page().insert_text((72, 72), "Just some text, no table")
    return doc.tobytes()


def _encrypted_xlsx_bytes() -> bytes:
    # Genuine OLE2/CFB signature (what a real encrypted workbook begins with).
    return OLE2_MAGIC + b"\x00" * 1024


# --------------------------------------------------------------------------- #
# Detectors
# --------------------------------------------------------------------------- #
def test_pdf_is_password_protected_true_for_encrypted() -> None:
    assert pdf_is_password_protected(_encrypted_pdf_bytes()) is True


def test_pdf_is_password_protected_false_for_plain() -> None:
    assert pdf_is_password_protected(_plain_pdf_bytes()) is False


def test_looks_like_encrypted_office_true_for_ole2() -> None:
    assert looks_like_encrypted_office(_encrypted_xlsx_bytes()) is True


def test_looks_like_encrypted_office_false_for_zip_xlsx() -> None:
    assert looks_like_encrypted_office(b"PK\x03\x04rest-of-a-normal-xlsx") is False


# --------------------------------------------------------------------------- #
# Excel upload paths
# --------------------------------------------------------------------------- #
def test_tb_upload_password_protected_xlsx_message() -> None:
    with pytest.raises(PasswordProtectedError) as exc:
        parse_tb_file(_encrypted_xlsx_bytes(), filename="protected.xlsx")
    assert str(exc.value) == PASSWORD_PROTECTED_MESSAGE
    assert isinstance(exc.value, ParseError)  # existing handlers still catch it


def test_gl_upload_password_protected_xlsx_message() -> None:
    with pytest.raises(GlToTbError) as exc:
        convert_gl_file_to_tb(
            _encrypted_xlsx_bytes(), "protected.xlsx",
            period_start=date(2026, 1, 1), period_end=date(2026, 12, 31), mode="C",
        )
    assert str(exc.value) == PASSWORD_PROTECTED_MESSAGE


def test_tb_upload_generic_broken_xlsx_is_not_password_message() -> None:
    with pytest.raises(ParseError) as exc:
        parse_tb_file(b"this is definitely not a spreadsheet", filename="broken.xlsx")
    assert str(exc.value) != PASSWORD_PROTECTED_MESSAGE
    assert not isinstance(exc.value, PasswordProtectedError)
    assert "not a valid Excel" in str(exc.value)


# --------------------------------------------------------------------------- #
# PDF upload paths
# --------------------------------------------------------------------------- #
def test_pdf_tb_extract_password_protected_message() -> None:
    with pytest.raises(PdfTbExtractError) as exc:
        extract_trial_balance_from_pdf(_encrypted_pdf_bytes())
    assert str(exc.value) == PASSWORD_PROTECTED_MESSAGE


def test_gl_pdf_password_protected_message() -> None:
    with pytest.raises(GlToTbError) as exc:
        parse_gl_pdf(_encrypted_pdf_bytes())
    assert str(exc.value) == PASSWORD_PROTECTED_MESSAGE


def test_gl_convert_pdf_password_protected_message() -> None:
    with pytest.raises(GlToTbError) as exc:
        convert_gl_file_to_tb(
            _encrypted_pdf_bytes(), "protected.pdf",
            period_start=date(2026, 1, 1), period_end=date(2026, 12, 31), mode="C",
        )
    assert str(exc.value) == PASSWORD_PROTECTED_MESSAGE


def test_plain_pdf_does_not_trigger_password_message() -> None:
    # A normal (non-encrypted) PDF with no TB table must fail generically, never
    # with the password message.
    with pytest.raises(PdfTbExtractError) as exc:
        extract_trial_balance_from_pdf(_plain_pdf_bytes())
    assert str(exc.value) != PASSWORD_PROTECTED_MESSAGE
