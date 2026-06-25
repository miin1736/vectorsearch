from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Iterator

import typer

from koreanops_rag.io import write_jsonl
from koreanops_rag.schemas import LogRecord
from koreanops_rag.text import clean_text

app = typer.Typer(add_completion=False)

SEVERITY_RE = re.compile(r"\b(INFO|WARN|WARNING|ERROR|ERR|FATAL|ALERT)\b", re.IGNORECASE)


def _stable_id(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]


def _severity(line: str) -> str:
    match = SEVERITY_RE.search(line)
    if not match:
        return "unknown"
    value = match.group(1).lower()
    if value == "warn":
        return "warning"
    if value in {"err", "fatal"}:
        return "error"
    return value


def iter_logs(
    input_path: Path,
    source_dataset: str,
    system: str,
    limit: int | None = None,
) -> Iterator[LogRecord]:
    with input_path.open("r", encoding="utf-8", errors="ignore") as f:
        for idx, line in enumerate(f):
            if limit and idx >= limit:
                break
            raw = line.strip()
            if not raw:
                continue
            label_alert = raw.startswith("1 ") or raw.startswith("ALERT")
            message = clean_text(raw)
            yield LogRecord(
                log_id=f"{source_dataset}_{_stable_id(raw)}",
                source_dataset=source_dataset,
                timestamp=None,
                system=system,
                severity=_severity(raw),  # type: ignore[arg-type]
                component="",
                message=message,
                is_anomaly=True if label_alert else None,
                template="",
                raw_log=raw,
            )


@app.command()
def run(
    input_path: Path,
    output_jsonl: Path,
    source_dataset: str = "loghub",
    system: str = "hdfs",
    limit: int | None = None,
) -> None:
    """Convert raw LogHub-style log lines into standard LogRecord JSONL."""
    count = write_jsonl(output_jsonl, iter_logs(input_path, source_dataset, system, limit=limit))
    typer.echo(f"Wrote {count} log records to {output_jsonl}")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
