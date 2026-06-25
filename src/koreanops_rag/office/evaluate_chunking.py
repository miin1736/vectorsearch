from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

import typer

from koreanops_rag.io import ensure_parent, read_jsonl
from koreanops_rag.office.chunking import token_count
from koreanops_rag.office.common import normalize_for_matching

app = typer.Typer(add_completion=False)


def evaluate_golden_evidence(chunks: list[dict], questions: list[dict]) -> dict[str, float]:
    by_parent: dict[str, list[dict]] = defaultdict(list)
    for chunk in chunks:
        parent = chunk.get("metadata", {}).get("parent_doc_id") or chunk["doc_id"]
        by_parent[parent].append(chunk)
    contained = 0
    page_covered = 0
    fragmented = 0
    evaluated = 0
    for question in questions:
        evidence = normalize_for_matching(question.get("evidence_text", ""))
        if not evidence:
            continue
        evaluated += 1
        candidates = [
            chunk
            for doc_id in question.get("gold_doc_ids", [])
            for chunk in by_parent.get(doc_id, [])
        ]
        normalized_chunks = [
            normalize_for_matching(str(chunk.get("content", ""))) for chunk in candidates
        ]
        hits = sum(bool(text and text in evidence or evidence in text) for text in normalized_chunks)
        contained += int(hits > 0)
        fragmented += int(hits == 0 and any(
            evidence[: max(len(evidence) // 2, 1)] in text for text in normalized_chunks
        ))
        gold_pages = set(int(page) for page in question.get("gold_pages", []))
        page_covered += int(any(
            set(range(
                int(chunk.get("metadata", {}).get("page_start", 0)),
                int(chunk.get("metadata", {}).get("page_end", 0)) + 1,
            )) & gold_pages
            for chunk in candidates
        ))
    lengths = [token_count(str(chunk.get("content", ""))) for chunk in chunks]
    return {
        "chunks": float(len(chunks)),
        "questions": float(evaluated),
        "gold_containment_rate": contained / max(evaluated, 1),
        "gold_page_coverage": page_covered / max(evaluated, 1),
        "fragmentation_proxy": fragmented / max(evaluated, 1),
        "empty_chunk_rate": sum(length == 0 for length in lengths) / max(len(lengths), 1),
        "mean_chunk_tokens": sum(lengths) / max(len(lengths), 1),
    }


@app.command()
def run(
    golden_questions_jsonl: Path,
    output_csv: Path,
    chunk_files: list[Path] = typer.Argument(...),
) -> None:
    """Compare Golden evidence containment across chunk JSONL variants."""
    questions = list(read_jsonl(golden_questions_jsonl))
    rows = []
    for chunk_file in chunk_files:
        chunks = list(read_jsonl(chunk_file))
        metrics = evaluate_golden_evidence(chunks, questions)
        rows.append({"strategy": chunk_file.stem, **metrics})
    ensure_parent(output_csv)
    with output_csv.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]) if rows else [])
        if rows:
            writer.writeheader()
            writer.writerows(rows)
    typer.echo(f"Wrote chunking metrics for {len(rows)} strategies to {output_csv}")


def main() -> None:
    app()
