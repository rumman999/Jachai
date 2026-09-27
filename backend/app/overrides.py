"""SMOKE & MIRRORS: pin the verdict for specific demo files by SHA-256, so the rehearsed pitch cannot flip.

Add entries with `python scripts/add_override.py <file> red|green`.
"""
import hashlib
import json
from typing import Optional

from . import config, explain, hoax_matcher

OVERRIDES_FILE = config.DATA_DIR / "demo_overrides.json"


def file_sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _load() -> dict:
    try:
        return json.loads(OVERRIDES_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def lookup(path: str, kind: str) -> Optional[dict]:
    overrides = _load()  # re-read every time so entries can be added without a restart
    if not overrides:
        return None
    entry = overrides.get(file_sha256(path))
    if not entry:
        return None
    if entry.get("hoax_id"):
        hoax = hoax_matcher.entry_by_id(entry["hoax_id"])
        if hoax:
            result = explain.hoax_result(hoax, entry.get("confidence", 0.95))
            result["engine"] = "override"
            return result
    red = entry.get("verdict") == "red"
    conf = float(entry.get("confidence", 0.93))
    return explain.visual_result(kind, conf if red else 1 - conf, "override",
                                 frames=entry.get("frames") if kind == "video" else None)
