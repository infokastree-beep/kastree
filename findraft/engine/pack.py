"""Content-pack manifest handling.
VERSION PINNING (spec §4.10 / Cursor rules §6): every pack carries a version
(e.g. "2024.09"). When the FRC issues a new edition, a NEW pack version is
created — the live pack is never edited in place. Periods/drafts record the
pack version in use at creation (year_ends.pack_version, draft_versions.
pack_version) and stay pinned to it; only NEW periods pick up the updated
pack. A mid-year standard change therefore can never silently alter an
in-progress statement.
"""
import json, pathlib, re
from datetime import date as _date

CONTENT_ROOT = pathlib.Path(__file__).resolve().parent.parent / "content"
DEFAULT_PACK = ("frs102-1a-ie", "2024.09")


def pack_dir(pack_id: str = DEFAULT_PACK[0], version: str = DEFAULT_PACK[1],
             root: pathlib.Path | None = None) -> pathlib.Path:
    """Directory of one IMMUTABLE pack version: content/<pack_id>/<version>/.
    A pinned draft always resolves to exactly the files it was pinned to."""
    if not re.fullmatch(r"[a-z0-9-]+", pack_id) or not re.fullmatch(r"\d{4}\.\d{2}", version):
        raise ValueError(f"invalid pack identity: {pack_id!r} {version!r}")
    d = (root or CONTENT_ROOT) / pack_id / version
    if not (d / "pack.json").is_file():
        raise FileNotFoundError(f"pack {pack_id} version {version} not found at {d}")
    m = json.loads((d / "pack.json").read_text())
    if m.get("pack") != pack_id or m.get("version") != version:
        raise ValueError(f"pack.json identity {m.get('pack')} {m.get('version')} "
                         f"does not match its directory {pack_id} {version}")
    return d


def load_manifest(pack_path=None) -> dict:
    path = pathlib.Path(pack_path) if pack_path else pack_dir() / "pack.json"
    m = json.loads(path.read_text(encoding="utf-8"))
    for key in ("pack", "version"):
        if key not in m or not m[key]:
            raise ValueError(f"pack manifest missing '{key}': {path}")
    if path.parent.name != m["version"] or path.parent.parent.name != m["pack"]:
        raise ValueError(f"manifest {m['pack']} {m['version']} does not match its directory {path.parent}")
    return m

def pin_pack_version(year_end_row: dict, manifest: dict,
                     period_start: str | None = None) -> dict:
    """Return the period/draft row augmented with its pinned pack identity.
    Called at period creation and at every draft-version creation."""
    row = dict(year_end_row)
    if row.get("pack_version") is not None:
        raise ValueError("period/draft already pinned to "
                         f"{row.get('pack_id')} {row['pack_version']} — create a new "
                         "draft version instead of re-pinning (immutability rule)")
    eff = manifest.get("effective_from")
    if period_start is not None and eff is not None and _date.fromisoformat(period_start) < _date.fromisoformat(eff):
        raise ValueError(f"{manifest['pack']} {manifest['version']} applies to periods "
                         f"beginning on or after {eff}; period starts {period_start}")
    row["pack_id"] = manifest["pack"]
    row["pack_version"] = manifest["version"]
    return row
