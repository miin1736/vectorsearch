from __future__ import annotations

from pathlib import Path
from typing import Iterator

import typer

from koreanops_rag.documents.chunk_documents import _split_labeled_content
from koreanops_rag.io import read_jsonl, write_jsonl
from koreanops_rag.text import clean_text

app = typer.Typer(add_completion=False)


def _metadata_context(doc: dict) -> str:
    metadata = dict(doc.get("metadata", {}))
    parts = [
        ("title", str(doc.get("title", ""))),
        ("priority", metadata.get("priority", "")),
        ("ticket type", metadata.get("ticket_type", "")),
        ("queue", metadata.get("queue", "")),
        ("status", metadata.get("status", "")),
        ("business type", metadata.get("business_type", "")),
    ]
    return clean_text(" ".join(f"{label}: {value}" for label, value in parts if value))


def document_to_contextual_chunks(doc: dict) -> Iterator[dict]:
    parent_doc_id = doc["doc_id"]
    if doc.get("source_type") != "ticket":
        chunk = dict(doc)
        chunk["embedding_text"] = str(doc.get("embedding_text") or doc.get("content", ""))
        chunk["metadata"] = {
            **dict(doc.get("metadata", {})),
            "parent_doc_id": parent_doc_id,
            "chunk_field": "message",
            "chunk_index": 0,
            "chunking_strategy": "contextual",
        }
        yield chunk
        return

    context = _metadata_context(doc)
    for idx, (field, text) in enumerate(_split_labeled_content(str(doc.get("content", "")))):
        contextual_text = clean_text(
            f"Ticket context: {context} Current field: {field}. Field text: {text}"
        )
        chunk = dict(doc)
        chunk["doc_id"] = f"{parent_doc_id}__ctx_{idx:02d}_{field}"
        chunk["title"] = f"{doc.get('title', '')} [{field}]".strip()
        chunk["content"] = contextual_text
        chunk["embedding_text"] = contextual_text
        chunk["metadata"] = {
            **dict(doc.get("metadata", {})),
            "parent_doc_id": parent_doc_id,
            "chunk_field": field,
            "chunk_index": idx,
            "chunking_strategy": "contextual",
        }
        yield chunk


def iter_contextual_chunks(documents_jsonl: Path) -> Iterator[dict]:
    for doc in read_jsonl(documents_jsonl):
        yield from document_to_contextual_chunks(doc)


@app.command()
def run(documents_jsonl: Path, output_jsonl: Path) -> None:
    """Create contextual chunks with parent ticket metadata repeated in every chunk."""
    count = write_jsonl(output_jsonl, iter_contextual_chunks(documents_jsonl))
    typer.echo(f"Wrote {count} contextual chunks to {output_jsonl}")


def main() -> None:
    app()
