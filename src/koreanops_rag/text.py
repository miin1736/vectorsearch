from __future__ import annotations

import html
import re
from typing import Any

TAG_RE = re.compile(r"<[^>]+>")
SPACE_RE = re.compile(r"\s+")


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = html.unescape(str(value))
    text = TAG_RE.sub(" ", text)
    return SPACE_RE.sub(" ", text).strip()


def split_tags(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [clean_text(v) for v in value if clean_text(v)]
    text = clean_text(value)
    if not text:
        return []
    return [part.strip() for part in re.split(r"[,;|]", text) if part.strip()]


def normalize_choice(value: Any, allowed: set[str], default: str = "unknown") -> str:
    text = clean_text(value).lower().replace("-", "_").replace(" ", "_")
    return text if text in allowed else default
