"""Upload checks for Product 2 source documents.

Week 2 acceptance (v7.6): cap size, verify the real file type, reject
macro-enabled workbooks, and cap decompressed zip size. The specification
names a 16-type document classifier and does not list those types, so this
module does not invent them. It classifies the bytes (pdf, xlsx, csv).

Spreadsheet row parsing lives in spreadsheet_import.py and is not called
from the request path.
"""

from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass
from typing import Literal

MAX_UPLOAD_BYTES = 50 * 1024 * 1024
# The spec requires a decompressed-size cap and does not set the number.
# 100 MiB is the enforced total of central-directory uncompressed sizes.
MAX_DECOMPRESSED_BYTES = 100 * 1024 * 1024
MAX_ZIP_MEMBERS = 1024
_CONTENT_TYPES_READ_CAP = 1024 * 1024

DetectedType = Literal["pdf", "xlsx", "csv"]

_FORMULA_LEAD = frozenset("=+-@")


class UploadRejected(Exception):
    """A file failed an upload-security check. ``detail`` is client-safe."""

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)


@dataclass(frozen=True)
class InspectedUpload:
    detected_type: DetectedType
    content_type: str
    filename: str


def escape_formula_text(value: str) -> str:
    """Prefix text that would be a formula when the file is opened as a sheet.

    Applies to account names and other text. Decimal amounts are not passed
    through here.
    """
    if value and value[0] in _FORMULA_LEAD:
        return "'" + value
    return value


def safe_filename(name: str | None) -> str:
    """Basename only, so a client-supplied path cannot choose the storage key."""
    raw = (name or "").replace("\x00", "").replace("\\", "/")
    base = raw.rsplit("/", 1)[-1].strip()
    if not base or base in {".", ".."}:
        return "upload"
    return base[:255]


def inspect_upload(content: bytes, filename: str | None) -> InspectedUpload:
    """Verify size, extension, and real type. Raises UploadRejected."""
    stored_name = safe_filename(filename)
    if not content:
        raise UploadRejected("File is empty")
    if len(content) > MAX_UPLOAD_BYTES:
        raise UploadRejected("File exceeds 50MB limit")

    extension = _extension(stored_name)
    if extension == "xlsm":
        raise UploadRejected("Macro-enabled workbooks are not accepted")

    detected = _detect(content)
    if extension not in {"pdf", "xlsx", "csv"}:
        raise UploadRejected("File type is not accepted")
    if detected is None or detected != extension:
        raise UploadRejected("File type does not match its contents")

    content_type = {
        "pdf": "application/pdf",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "csv": "text/csv",
    }[detected]
    return InspectedUpload(
        detected_type=detected,
        content_type=content_type,
        filename=stored_name,
    )


def _extension(filename: str) -> str:
    if "." not in filename:
        return ""
    return filename.rsplit(".", 1)[-1].lower()


def _detect(content: bytes) -> DetectedType | None:
    if content.startswith(b"%PDF-"):
        return "pdf"
    if content.startswith((b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")):
        return _detect_ooxml(content)
    if _looks_like_text(content):
        return "csv"
    return None


def _looks_like_text(content: bytes) -> bool:
    sample = content[:8192]
    if b"\x00" in sample:
        return False
    try:
        sample.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            sample.decode("cp1252")
        except UnicodeDecodeError:
            return False
    return True


def _detect_ooxml(content: bytes) -> DetectedType | None:
    """Return xlsx only for a macro-free workbook zip inside the size cap."""
    try:
        archive = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile as exc:
        raise UploadRejected("File type could not be verified") from exc

    with archive:
        infos = archive.infolist()
        if len(infos) > MAX_ZIP_MEMBERS:
            raise UploadRejected("File exceeds the decompressed size cap")
        total = 0
        names: list[str] = []
        for info in infos:
            if info.flag_bits & 0x1:
                raise UploadRejected("File type could not be verified")
            if info.file_size < 0 or info.file_size > MAX_DECOMPRESSED_BYTES:
                raise UploadRejected("File exceeds the decompressed size cap")
            total += info.file_size
            if total > MAX_DECOMPRESSED_BYTES:
                raise UploadRejected("File exceeds the decompressed size cap")
            names.append(info.filename.replace("\\", "/"))
            lowered = info.filename.lower()
            if "vbaproject" in lowered or lowered.endswith(".xlsm"):
                raise UploadRejected("Macro-enabled workbooks are not accepted")

        if "[Content_Types].xml" not in names or "xl/workbook.xml" not in names:
            return None
        content_types = _read_capped(archive, "[Content_Types].xml")
        lowered_types = content_types.lower()
        if b"vbaproject" in lowered_types or b"macroenabled" in lowered_types:
            raise UploadRejected("Macro-enabled workbooks are not accepted")
    return "xlsx"


def _read_capped(archive: zipfile.ZipFile, name: str) -> bytes:
    info = archive.getinfo(name)
    if info.file_size > _CONTENT_TYPES_READ_CAP or info.compress_size > _CONTENT_TYPES_READ_CAP:
        raise UploadRejected("File exceeds the decompressed size cap")
    with archive.open(info) as handle:
        data = handle.read(_CONTENT_TYPES_READ_CAP + 1)
    if len(data) > _CONTENT_TYPES_READ_CAP:
        raise UploadRejected("File exceeds the decompressed size cap")
    return data
