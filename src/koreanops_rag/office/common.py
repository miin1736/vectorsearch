from __future__ import annotations

import re
from pathlib import Path


DOCUMENT_ID_RE = re.compile(r"OC2_\d+_[A-Z0-9-]+_\d+")


def document_id(value: str) -> str:
    match = DOCUMENT_ID_RE.search(Path(value).stem)
    return match.group(0) if match else Path(value).stem


def split_from_path(path: Path) -> str:
    return "validation" if "Validation" in path.parts else "training"


def document_type_from_archive(path: Path) -> str:
    name = path.name
    if "." in name:
        name = name.split(".", 1)[1]
    return name.split("_", 1)[0]


def normalize_line(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def normalize_for_matching(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z가-힣]", "", value).lower()
