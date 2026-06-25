from __future__ import annotations

from pathlib import Path
from typing import Iterator

import typer

from koreanops_rag.io import read_model_jsonl, write_jsonl
from koreanops_rag.schemas import LogRecord, RagDocument, Ticket
from koreanops_rag.text import clean_text

app = typer.Typer(add_completion=False)


def _valid_tags(tags: list[str]) -> list[str]:
    return [tag for tag in tags if tag and tag.lower() != "nan"]


def _join_embedding_parts(parts: list[tuple[str, str]]) -> str:
    return clean_text(" ".join(f"{label}: {value}" for label, value in parts if value))


def ticket_to_document(ticket: Ticket) -> RagDocument | None:
    tags = _valid_tags(ticket.tags)
    content_parts = [
        f"Subject: {ticket.subject}",
        f"Description: {ticket.description}",
        f"Resolution: {ticket.resolution}",
        f"Tags: {', '.join(tags)}" if tags else "",
    ]
    content = clean_text("\n".join(part for part in content_parts if part))
    if not content:
        return None
    embedding_text = _join_embedding_parts(
        [
            ("ticket subject", ticket.subject),
            ("issue description", ticket.description),
            ("known resolution", ticket.resolution),
            ("priority", ticket.priority if ticket.priority != "unknown" else ""),
            ("ticket type", ticket.ticket_type if ticket.ticket_type != "unknown" else ""),
            ("support queue", ticket.queue),
            ("business type", ticket.business_type),
            ("tags", ", ".join(tags)),
        ]
    )
    return RagDocument(
        doc_id=f"ticket_{ticket.source_dataset}_{ticket.ticket_id}",
        source_type="ticket",
        title=ticket.subject or f"Ticket {ticket.ticket_id}",
        content=content,
        embedding_text=embedding_text or content,
        metadata={
            "ticket_id": ticket.ticket_id,
            "source_dataset": ticket.source_dataset,
            "priority": ticket.priority,
            "ticket_type": ticket.ticket_type,
            "queue": ticket.queue,
            "business_type": ticket.business_type,
            "status": ticket.status,
        },
    )


def log_to_document(log: LogRecord) -> RagDocument | None:
    content = clean_text(log.message or log.raw_log)
    if not content:
        return None
    embedding_text = _join_embedding_parts(
        [
            ("system", log.system if log.system != "unknown" else ""),
            ("severity", log.severity if log.severity != "unknown" else ""),
            ("component", log.component),
            ("log message", log.message),
            ("template", log.template),
        ]
    )
    return RagDocument(
        doc_id=f"log_{log.source_dataset}_{log.log_id}",
        source_type="log",
        title=f"{log.system.upper()} {log.severity} log",
        content=content,
        embedding_text=embedding_text or content,
        metadata={
            "log_id": log.log_id,
            "source_dataset": log.source_dataset,
            "system": log.system,
            "severity": log.severity,
            "component": log.component,
            "is_anomaly": log.is_anomaly,
            "template": log.template,
        },
    )


def iter_documents(ticket_jsonl: Path | None, log_jsonl: Path | None) -> Iterator[RagDocument]:
    if ticket_jsonl:
        for ticket in read_model_jsonl(ticket_jsonl, Ticket):
            doc = ticket_to_document(ticket)
            if doc:
                yield doc
    if log_jsonl:
        for log in read_model_jsonl(log_jsonl, LogRecord):
            doc = log_to_document(log)
            if doc:
                yield doc


@app.command()
def run(
    output_jsonl: Path,
    ticket_jsonl: Path | None = None,
    log_jsonl: Path | None = None,
) -> None:
    """Build retrieval-ready RAG documents from normalized ticket and log JSONL files."""
    count = write_jsonl(output_jsonl, iter_documents(ticket_jsonl, log_jsonl))
    typer.echo(f"Wrote {count} documents to {output_jsonl}")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
