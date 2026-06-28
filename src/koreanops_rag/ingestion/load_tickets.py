from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

import pandas as pd
import typer
import yaml

from koreanops_rag.io import write_jsonl
from koreanops_rag.observability import RunRecorder, default_reports_dir
from koreanops_rag.schemas import Ticket
from koreanops_rag.text import clean_text, normalize_choice, split_tags

app = typer.Typer(add_completion=False)

PRIORITIES = {"low", "medium", "high", "critical", "unknown"}
TICKET_TYPES = {"incident", "request", "problem", "question", "unknown"}
STATUSES = {"open", "closed", "resolved", "unknown"}


def _parse_datetime(value: Any) -> datetime | None:
    if value is None or str(value).strip() == "" or str(value).lower() == "nan":
        return None
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.to_pydatetime()


def _get(row: pd.Series, columns: dict[str, Any], key: str) -> Any:
    column = columns.get(key, "")
    if isinstance(column, list):
        return [row[item] for item in column if item in row]
    if column and column in row:
        return row[column]
    return None


def load_mapping(path: Path, dataset_key: str) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    return raw.get(dataset_key) or raw.get("default") or {}


def iter_tickets(
    input_csv: Path,
    source_dataset: str,
    mapping: dict[str, Any],
    limit: int | None = None,
    chunksize: int = 10_000,
) -> Iterator[Ticket]:
    produced = 0
    for chunk in pd.read_csv(input_csv, chunksize=chunksize):
        for _, row in chunk.iterrows():
            ticket_id = clean_text(_get(row, mapping, "ticket_id")) or f"{source_dataset}_{produced}"
            subject = clean_text(_get(row, mapping, "subject"))
            description = clean_text(_get(row, mapping, "description"))
            resolution = clean_text(_get(row, mapping, "resolution"))
            raw_text = " ".join(part for part in [subject, description, resolution] if part)
            yield Ticket(
                ticket_id=ticket_id,
                source_dataset=source_dataset,
                created_at=_parse_datetime(_get(row, mapping, "created_at")),
                ticket_type=normalize_choice(
                    _get(row, mapping, "ticket_type"), TICKET_TYPES
                ),  # type: ignore[arg-type]
                priority=normalize_choice(
                    _get(row, mapping, "priority"), PRIORITIES
                ),  # type: ignore[arg-type]
                queue=clean_text(_get(row, mapping, "queue")),
                business_type=clean_text(_get(row, mapping, "business_type")),
                subject=subject,
                description=description,
                resolution=resolution,
                tags=split_tags(_get(row, mapping, "tags")),
                status=normalize_choice(
                    _get(row, mapping, "status"), STATUSES
                ),  # type: ignore[arg-type]
                raw_text=raw_text,
            )
            produced += 1
            if limit and produced >= limit:
                return


@app.command()
def run(
    input_csv: Path,
    output_jsonl: Path,
    source_dataset: str = "customer_support",
    mapping_file: Path = Path("configs/ticket_columns.yaml"),
    dataset_key: str = "default",
    limit: int | None = None,
    run_id: str | None = None,
) -> None:
    """Normalize a Kaggle ticket CSV into the standard Ticket JSONL schema."""
    mapping = load_mapping(mapping_file, dataset_key)
    with RunRecorder(
        "load_tickets",
        default_reports_dir(),
        run_id=run_id,
        command="koreanops-load-tickets",
        config_path=mapping_file,
        input_paths=[input_csv, mapping_file],
        output_paths=[output_jsonl],
    ) as recorder:
        count = write_jsonl(
            output_jsonl,
            iter_tickets(input_csv, source_dataset, mapping, limit=limit),
        )
        recorder.set_record_count(count)
    typer.echo(f"Wrote {count} tickets to {output_jsonl}")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
