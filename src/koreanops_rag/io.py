from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def read_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def read_model_jsonl(path: Path, model: type[T]) -> Iterator[T]:
    for row in read_jsonl(path):
        yield model.model_validate(row)


def write_jsonl(path: Path, rows: Iterable[BaseModel | dict[str, Any]]) -> int:
    ensure_parent(path)
    count = 0
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            payload = row.model_dump(mode="json") if isinstance(row, BaseModel) else row
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
            count += 1
    return count
