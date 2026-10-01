"""Child process that renders one statutory DOCX under an address-space cap.

Run as ``python -m app.services.docx_child <in.json> <out.docx>``. The cap is
applied before python-docx is imported.
"""

from __future__ import annotations

import json
import resource
import sys
from pathlib import Path

RENDER_AS_LIMIT = 256 * 1024 * 1024


def apply_memory_cap() -> None:
    """Limit this process's address space. Does not affect the parent."""
    resource.setrlimit(resource.RLIMIT_AS, (RENDER_AS_LIMIT, RENDER_AS_LIMIT))


def main(argv: list[str] | None = None) -> None:
    apply_memory_cap()
    args = sys.argv if argv is None else argv
    if len(args) != 3:
        raise SystemExit(
            "usage: python -m app.services.docx_child <in.json> <out.docx>"
        )
    from app.services.statutory_docx import build_docx

    payload = json.loads(Path(args[1]).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit("DOCX payload is not an object")
    build_docx(payload, Path(args[2]))


if __name__ == "__main__":
    main()
