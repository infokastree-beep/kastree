"""Week 2 upload security: real type, macros, zip-bomb cap, formula escape."""

from __future__ import annotations

import io
import struct
import uuid
import zipfile
import zlib
from pathlib import Path

import openpyxl
import pytest

from app.services.spreadsheet_import import (
    MAX_SHEET_COLUMNS,
    MAX_SHEET_ROWS,
    SpreadsheetLimitError,
    read_csv_text,
    read_spreadsheet_text,
)
from app.services.source_storage import (
    LocalPracticeStorage,
    S3PracticeStorage,
    practice_storage_key,
)
from app.services.upload_security import (
    MAX_DECOMPRESSED_BYTES,
    MAX_UPLOAD_BYTES,
    UploadRejected,
    escape_formula_text,
    inspect_upload,
    safe_filename,
)
from tests.conftest import balanced_tb_xlsx_bytes


def _pdf() -> bytes:
    return b"%PDF-1.4\n1 0 obj<<>>endobj\n%%EOF\n"


def _csv() -> bytes:
    return b"code,name\n1000,Cash\n"


def _zip_claiming_uncompressed(claimed: int) -> bytes:
    name = b"xl/workbook.xml"
    payload = b"<workbook/>"
    compressed = zlib.compress(payload)
    crc = zlib.crc32(payload) & 0xFFFFFFFF
    local = (
        struct.pack(
            "<IHHHHHIIIHH",
            0x04034B50,
            20,
            0,
            8,
            0,
            0,
            crc,
            len(compressed),
            len(payload),
            len(name),
            0,
        )
        + name
        + compressed
    )
    central = (
        struct.pack(
            "<IHHHHHHIIIHHHHHII",
            0x02014B50,
            20,
            20,
            0,
            8,
            0,
            0,
            crc,
            len(compressed),
            claimed,
            len(name),
            0,
            0,
            0,
            0,
            0,
            0,
        )
        + name
    )
    end = struct.pack(
        "<IHHHHIIH",
        0x06054B50,
        0,
        0,
        1,
        1,
        len(central),
        len(local),
        0,
    )
    return local + central + end


def _with_vba(xlsx: bytes) -> bytes:
    source = io.BytesIO(xlsx)
    target = io.BytesIO()
    with zipfile.ZipFile(source) as inbound, zipfile.ZipFile(target, "w") as outbound:
        for info in inbound.infolist():
            outbound.writestr(info, inbound.read(info.filename))
        outbound.writestr("xl/vbaProject.bin", b"macro")
    return target.getvalue()


def _with_macro_content_type(xlsx: bytes) -> bytes:
    source = io.BytesIO(xlsx)
    target = io.BytesIO()
    with zipfile.ZipFile(source) as inbound, zipfile.ZipFile(target, "w") as outbound:
        for info in inbound.infolist():
            data = inbound.read(info.filename)
            if info.filename == "[Content_Types].xml":
                data = data.replace(
                    b"</Types>",
                    b'<Override PartName="/xl/vbaProject.bin" '
                    b'ContentType="application/vnd.ms-office.vbaProject"/></Types>',
                )
            outbound.writestr(info, data)
    return target.getvalue()


def test_size_cap_is_fifty_megabytes() -> None:
    assert MAX_UPLOAD_BYTES == 50 * 1024 * 1024
    assert MAX_DECOMPRESSED_BYTES == 100 * 1024 * 1024


def test_pdf_xlsx_and_csv_match_their_bytes() -> None:
    pdf = inspect_upload(_pdf(), "statement.PDF")
    assert pdf.detected_type == "pdf"
    sheet = inspect_upload(balanced_tb_xlsx_bytes(), "tb.XLSX")
    assert sheet.detected_type == "xlsx"
    table = inspect_upload(_csv(), "tb.csv")
    assert table.detected_type == "csv"


def test_extension_is_not_trusted() -> None:
    with pytest.raises(UploadRejected, match="does not match"):
        inspect_upload(_pdf(), "tb.xlsx")
    with pytest.raises(UploadRejected, match="does not match"):
        inspect_upload(balanced_tb_xlsx_bytes(), "tb.csv")
    with pytest.raises(UploadRejected, match="does not match"):
        inspect_upload(_csv(), "tb.pdf")


def test_xlsm_extension_is_rejected_even_when_the_bytes_are_a_clean_workbook() -> None:
    with pytest.raises(UploadRejected, match="Macro-enabled"):
        inspect_upload(balanced_tb_xlsx_bytes(), "tb.xlsm")


def test_macro_payload_inside_an_xlsx_name_is_rejected() -> None:
    with pytest.raises(UploadRejected, match="Macro-enabled"):
        inspect_upload(_with_vba(balanced_tb_xlsx_bytes()), "tb.xlsx")
    with pytest.raises(UploadRejected, match="Macro-enabled"):
        inspect_upload(_with_macro_content_type(balanced_tb_xlsx_bytes()), "tb.xlsx")


def test_zip_bomb_claimed_size_is_rejected_without_decompressing_it() -> None:
    bomb = _zip_claiming_uncompressed(MAX_DECOMPRESSED_BYTES + 1)
    assert len(bomb) < 10_000
    with pytest.raises(UploadRejected, match="decompressed size"):
        inspect_upload(bomb, "tb.xlsx")


def test_decompressed_cap_rejects_an_honest_archive_over_the_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.services.upload_security.MAX_DECOMPRESSED_BYTES",
        32,
    )
    with pytest.raises(UploadRejected, match="decompressed size"):
        inspect_upload(balanced_tb_xlsx_bytes(), "tb.xlsx")


def test_over_upload_cap_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.services.upload_security.MAX_UPLOAD_BYTES", 8)
    with pytest.raises(UploadRejected, match="50MB"):
        inspect_upload(b"%PDF-1.4\nmore-than-eight", "a.pdf")


def test_filename_cannot_choose_a_path() -> None:
    assert safe_filename("../../etc/passwd.xlsx") == "passwd.xlsx"
    assert safe_filename("folder\\tb.csv") == "tb.csv"
    inspected = inspect_upload(_csv(), "../../secret.csv")
    assert inspected.filename == "secret.csv"


def test_formula_leading_text_is_escaped() -> None:
    assert escape_formula_text("=SUM(A1)") == "'=SUM(A1)"
    assert escape_formula_text("+cmd") == "'+cmd"
    assert escape_formula_text("-item") == "'-item"
    assert escape_formula_text("@name") == "'@name"
    assert escape_formula_text("Cash") == "Cash"


def test_worker_reader_escapes_formula_text_and_enforces_caps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.append(["=SUM(A1)", "Cash", 12])
    buffer = io.BytesIO()
    workbook.save(buffer)
    rows = read_spreadsheet_text(buffer.getvalue())
    assert rows[0][0] == "'=SUM(A1)"
    assert rows[0][1] == "Cash"
    assert rows[0][2] == "12"

    escaped = read_csv_text(b"=cmd,Cash\n")
    assert escaped == [["'=cmd", "Cash"]]

    monkeypatch.setattr("app.services.spreadsheet_import.MAX_SHEET_COLUMNS", 1)
    with pytest.raises(SpreadsheetLimitError, match="column"):
        read_spreadsheet_text(buffer.getvalue())
    with pytest.raises(SpreadsheetLimitError, match="column"):
        read_csv_text(b"a,b\n")

    monkeypatch.setattr("app.services.spreadsheet_import.MAX_SHEET_COLUMNS", MAX_SHEET_COLUMNS)
    monkeypatch.setattr("app.services.spreadsheet_import.MAX_SHEET_ROWS", 0)
    assert MAX_SHEET_ROWS == 50_000
    with pytest.raises(SpreadsheetLimitError, match="row"):
        read_csv_text(b"a\n")


def test_request_router_does_not_parse_spreadsheets() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "routers"
        / "source_documents.py"
    ).read_text()
    assert "openpyxl" not in source
    assert "spreadsheet_import" not in source
    assert "read_spreadsheet_text" not in source


def test_storage_key_is_per_practice_and_rejects_escape(tmp_path: Path) -> None:
    org = "11111111-1111-1111-1111-111111111111"
    company = "22222222-2222-2222-2222-222222222222"
    document = "33333333-3333-3333-3333-333333333333"
    key = practice_storage_key(
        org_id=uuid.UUID(org),
        company_id=uuid.UUID(company),
        document_id=uuid.UUID(document),
    )
    assert key == f"practices/{org}/companies/{company}/documents/{document}"
    store = LocalPracticeStorage(tmp_path)
    store.put(key=key, body=b"%PDF-1.4\n", content_type="application/pdf")
    assert store.get(key=key) == b"%PDF-1.4\n"
    with pytest.raises(ValueError, match="invalid storage key"):
        store.put(key="../secrets", body=b"x", content_type="text/plain")


def test_s3_storage_uses_the_practice_key_without_export_tags() -> None:
    class _Body:
        def read(self) -> bytes:
            return b"csv"

    class _Client:
        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []

        def put_object(self, **kwargs: object) -> object:
            self.calls.append(kwargs)
            return {}

        def get_object(self, **kwargs: object) -> dict[str, _Body]:
            self.calls.append(kwargs)
            return {"Body": _Body()}

    client = _Client()
    store = S3PracticeStorage(client=client)
    key = practice_storage_key(
        org_id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
        company_id=uuid.UUID("22222222-2222-2222-2222-222222222222"),
        document_id=uuid.UUID("33333333-3333-3333-3333-333333333333"),
    )
    store.put(key=key, body=b"csv", content_type="text/csv")
    assert store.get(key=key) == b"csv"
    assert client.calls[0]["Key"] == key
    assert "Tagging" not in client.calls[0]
    assert "Expires" not in client.calls[0]
