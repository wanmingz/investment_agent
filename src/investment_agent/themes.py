"""Theme identity helpers for cross-agent merge and history."""

from __future__ import annotations

import re

_THEME_KEY_RE = re.compile(r"[^a-z0-9]+")


def theme_key(name: str) -> str:
    """Stable id for clustering similar theme titles across agents."""
    raw = name.lower().strip()
    key = _THEME_KEY_RE.sub("-", raw).strip("-")
    return key or "theme"
