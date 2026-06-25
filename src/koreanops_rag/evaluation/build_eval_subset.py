from __future__ import annotations

from pathlib import Path

import typer

from koreanops_rag.io import read_jsonl, write_jsonl

app = typer.Typer(add_completion=False)


def parent_doc_id(row: dict) -> str:
    metadata = dict(row.get("metadata", {}))
    return str(metadata.get("parent_doc_id") or row["doc_id"])


def gold_parent_ids(questions_jsonl: Path) -> set[str]:
    parents = set()
    for row in read_jsonl(questions_jsonl):
        parents.update(str(doc_id) for doc_id in row.get("gold_doc_ids", []))
    return parents


def build_subset(documents_jsonl: Path, questions_jsonl: Path, max_rows: int):
    gold_parents = gold_parent_ids(questions_jsonl)
    gold_rows = []
    negative_rows = []
    for row in read_jsonl(documents_jsonl):
        if parent_doc_id(row) in gold_parents:
            gold_rows.append(row)
        elif len(gold_rows) + len(negative_rows) < max_rows:
            negative_rows.append(row)
    yield from gold_rows
    yield from negative_rows[: max(max_rows - len(gold_rows), 0)]


@app.command()
def run(
    documents_jsonl: Path,
    questions_jsonl: Path,
    output_jsonl: Path,
    max_rows: int = 10000,
) -> None:
    """Build a deterministic retrieval subset that always includes validation gold parents."""
    count = write_jsonl(output_jsonl, build_subset(documents_jsonl, questions_jsonl, max_rows))
    typer.echo(f"Wrote {count} subset rows to {output_jsonl}")


def main() -> None:
    app()
