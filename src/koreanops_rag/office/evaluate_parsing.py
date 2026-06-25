from __future__ import annotations

import csv
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from pathlib import Path

import typer

from koreanops_rag.io import ensure_parent, read_jsonl
from koreanops_rag.office.common import normalize_for_matching

app = typer.Typer(add_completion=False)


def _character_scores(parsed: str, gold: str) -> tuple[float, float, float]:
    parsed_normalized = normalize_for_matching(parsed)
    gold_normalized = normalize_for_matching(gold)
    matcher = SequenceMatcher(None, parsed_normalized, gold_normalized, autojunk=False)
    matched = sum(block.size for block in matcher.get_matching_blocks())
    precision = matched / max(len(parsed_normalized), 1)
    recall = matched / max(len(gold_normalized), 1)
    similarity = matcher.ratio()
    return precision, recall, similarity


def _duplicate_ratio(text: str, n: int = 20) -> float:
    normalized = normalize_for_matching(text)
    if len(normalized) < n:
        return 0.0
    grams = [normalized[index : index + n] for index in range(len(normalized) - n + 1)]
    counts = Counter(grams)
    duplicates = sum(count - 1 for count in counts.values() if count > 1)
    return duplicates / max(len(grams), 1)


@app.command()
def run(
    parsed_pages_jsonl: Path,
    oracle_pages_jsonl: Path,
    details_csv: Path,
    report_md: Path,
) -> None:
    """Compare PDF-only parsing against Oracle page text."""
    parsed = {
        (row["doc_id"], int(row["page_num"])): str(
            row.get("clean_text") or row.get("raw_text") or ""
        )
        for row in read_jsonl(parsed_pages_jsonl)
    }
    oracle = {
        (row["doc_id"], int(row["page_num"])): str(row.get("content") or "")
        for row in read_jsonl(oracle_pages_jsonl)
    }
    ensure_parent(details_csv)
    rows = []
    by_document: dict[str, list[dict]] = defaultdict(list)
    for key, gold in oracle.items():
        parsed_text = parsed.get(key, "")
        precision, recall, similarity = _character_scores(parsed_text, gold)
        row = {
            "doc_id": key[0],
            "page_num": key[1],
            "parsed_chars": len(parsed_text),
            "gold_chars": len(gold),
            "character_precision": precision,
            "character_recall": recall,
            "normalized_edit_similarity": similarity,
            "duplicate_ratio": _duplicate_ratio(parsed_text),
            "page_extracted": float(bool(parsed_text.strip())),
        }
        rows.append(row)
        by_document[key[0]].append(row)
    with details_csv.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]) if rows else [])
        if rows:
            writer.writeheader()
            writer.writerows(rows)
    means = {
        field: sum(float(row[field]) for row in rows) / max(len(rows), 1)
        for field in (
            "character_precision",
            "character_recall",
            "normalized_edit_similarity",
            "duplicate_ratio",
            "page_extracted",
        )
    }
    ensure_parent(report_md)
    report_md.write_text(
        "\n".join(
            [
                "# PDF Parsing Quality",
                "",
                f"- Oracle pages: {len(rows):,}",
                f"- Documents: {len(by_document):,}",
                f"- Character precision: {means['character_precision']:.4f}",
                f"- Character recall: {means['character_recall']:.4f}",
                f"- Normalized edit similarity: {means['normalized_edit_similarity']:.4f}",
                f"- Page extraction success: {means['page_extracted']:.4f}",
                f"- Duplicate ratio: {means['duplicate_ratio']:.4f}",
                "",
                "Detailed page metrics are stored in the companion CSV.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    typer.echo(f"Evaluated {len(rows)} parsed pages against Oracle text")


def main() -> None:
    app()
