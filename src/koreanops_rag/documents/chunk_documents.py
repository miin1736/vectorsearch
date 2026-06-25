from __future__ import annotations

from pathlib import Path
import re
from typing import Iterator

import typer

from koreanops_rag.io import read_jsonl, write_jsonl
from koreanops_rag.text import clean_text

app = typer.Typer(add_completion=False)


FIELD_LABELS = {
    "Subject": "subject",
    "Description": "description",
    "Resolution": "resolution",
    "Tags": "tags",
}

FIELD_RE = re.compile(r"\b(Subject|Description|Resolution|Tags):")


def _split_labeled_content(content: str) -> list[tuple[str, str]]:
    matches = list(FIELD_RE.finditer(content))
    if not matches:
        text = clean_text(content)
        return [("content", text)] if text else []

    parts: list[tuple[str, str]] = []
    for idx, match in enumerate(matches):
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(content)
        field = FIELD_LABELS[match.group(1)]
        text = clean_text(content[start:end])
        if text:
            parts.append((field, text))
    return parts


def document_to_field_chunks(doc: dict) -> Iterator[dict]:
    parent_doc_id = doc["doc_id"]
    if doc.get("source_type") != "ticket":
        chunk = dict(doc)
        chunk["metadata"] = {
            **dict(doc.get("metadata", {})),
            "parent_doc_id": parent_doc_id,
            "chunk_field": "message",
            "chunk_index": 0,
        }
        yield chunk
        return

    for idx, (field, text) in enumerate(_split_labeled_content(str(doc.get("content", "")))):
        chunk = dict(doc)
        chunk["doc_id"] = f"{parent_doc_id}__chunk_{idx:02d}_{field}"
        chunk["title"] = f"{doc.get('title', '')} [{field}]".strip()
        chunk["content"] = f"{field}: {text}"
        chunk["metadata"] = {
            **dict(doc.get("metadata", {})),
            "parent_doc_id": parent_doc_id,
            "chunk_field": field,
            "chunk_index": idx,
        }
        yield chunk


def iter_field_chunks(documents_jsonl: Path) -> Iterator[dict]:
    for doc in read_jsonl(documents_jsonl):
        yield from document_to_field_chunks(doc)


@app.command()
def run(documents_jsonl: Path, output_jsonl: Path) -> None:
    """Create field-aware retrieval chunks while preserving parent document ids."""
    count = write_jsonl(output_jsonl, iter_field_chunks(documents_jsonl))
    typer.echo(f"Wrote {count} field chunks to {output_jsonl}")


def main() -> None:
    app()
