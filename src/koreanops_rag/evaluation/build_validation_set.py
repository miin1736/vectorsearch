from __future__ import annotations

import json
import random
import re
from pathlib import Path

import typer

from koreanops_rag.io import read_jsonl

app = typer.Typer(add_completion=False)


def _clean(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _question_from_doc(doc: dict) -> str:
    metadata = doc.get("metadata", {})
    if doc["source_type"] == "ticket":
        parts = [
            doc.get("title", ""),
            metadata.get("priority", ""),
            metadata.get("ticket_type", ""),
            metadata.get("queue", ""),
            doc.get("content", "")[:240],
        ]
    else:
        parts = [
            metadata.get("system", ""),
            metadata.get("severity", ""),
            metadata.get("component", ""),
            doc.get("content", "")[:240],
        ]
    return _clean(" ".join(_clean(part) for part in parts if _clean(part)))


@app.command()
def run(
    documents_jsonl: Path,
    output_jsonl: Path,
    ticket_count: int = 400,
    log_count: int = 40,
    seed: int = 42,
) -> None:
    """Build a deterministic validation set using sampled documents as gold labels."""
    random.seed(seed)
    tickets: list[dict] = []
    logs: list[dict] = []
    for doc in read_jsonl(documents_jsonl):
        if doc["source_type"] == "ticket":
            tickets.append(doc)
        elif doc["source_type"] == "log":
            logs.append(doc)

    sampled = random.sample(tickets, min(ticket_count, len(tickets))) + random.sample(
        logs, min(log_count, len(logs))
    )
    random.shuffle(sampled)
    output_jsonl.parent.mkdir(parents=True, exist_ok=True)
    with output_jsonl.open("w", encoding="utf-8", newline="\n") as f:
        for doc in sampled:
            row = {
                "question": _question_from_doc(doc),
                "gold_doc_ids": [doc["doc_id"]],
                "source_type": doc["source_type"],
            }
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    typer.echo(
        f"Wrote {len(sampled)} validation questions "
        f"({min(ticket_count, len(tickets))} tickets, {min(log_count, len(logs))} logs) "
        f"to {output_jsonl}"
    )


def main() -> None:
    app()
