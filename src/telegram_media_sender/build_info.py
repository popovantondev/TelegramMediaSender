"""Read build identity bundled into frozen app candidates."""
from __future__ import annotations

import json
from pathlib import Path
import sys

from . import __version__


def build_label() -> str:
    """Return a concise version/candidate string for the window title."""
    runtime_root = Path(getattr(sys, "_MEIPASS", None) or Path(__file__).resolve().parents[2])
    metadata = runtime_root / "build-info.json"
    if metadata.is_file():
        try:
            info = json.loads(metadata.read_text(encoding="utf-8"))
            version = str(info.get("version") or __version__)
            candidate = str(info.get("candidate_id") or "candidate")
            return f"{version} · {candidate}"
        except (OSError, ValueError, TypeError):
            pass
    return f"{__version__} · development"
