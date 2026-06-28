from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path
from statistics import mean, median
from typing import Any

import typer

from koreanops_rag.io import ensure_parent, read_jsonl

app = typer.Typer(add_completion=False)

FALLBACK_QUESTION_PREFIXES = (
    "이 문서",
    "이 문서가",
    "이 문서에서",
    "??臾몄꽌",
    "??臾몄꽌媛",
    "??臾몄꽌???",
)


def _question_key(question: str) -> str:
    return " ".join(question.strip().lower().split())


def _looks_like_question(text: str) -> bool:
    stripped = text.strip()
    return stripped.endswith("?") or stripped.endswith("？") or stripped.endswith("??")


def review_row(
    row: dict[str, Any],
    seen_questions: set[str] | None = None,
    min_evidence_chars: int = 80,
    min_answer_chars: int = 2,
    low_overlap_threshold: float = 0.05,
) -> dict[str, Any]:
    """Add deterministic review metadata to one Golden Set candidate.

    The function only auto-rejects issues that are very likely to distort retrieval
    evaluation. Softer quality concerns are emitted as flags for manual inspection.
    """
    seen_questions = seen_questions if seen_questions is not None else set()
    flags: list[str] = []
    reject_reasons: list[str] = []

    question = str(row.get("question", "")).strip()
    answer = str(row.get("reference_answer", "")).strip()
    evidence = str(row.get("evidence_text", "")).strip()
    gold_doc_ids = row.get("gold_doc_ids") or []
    gold_pages = row.get("gold_pages") or []
    lexical_overlap = float(row.get("lexical_overlap") or 0.0)

    if not question:
        reject_reasons.append("missing_question")
    if not answer:
        reject_reasons.append("missing_reference_answer")
    if not evidence:
        reject_reasons.append("missing_evidence")
    if not gold_doc_ids:
        reject_reasons.append("missing_gold_doc_ids")
    if not gold_pages:
        reject_reasons.append("missing_gold_pages")

    key = _question_key(question)
    if key and key in seen_questions:
        reject_reasons.append("duplicate_question")
    elif key:
        seen_questions.add(key)

    if any(question.startswith(prefix) for prefix in FALLBACK_QUESTION_PREFIXES):
        reject_reasons.append("fallback_question_template")

    if evidence and len(evidence) < min_evidence_chars:
        reject_reasons.append("too_short_evidence")
    if answer and len(answer) < min_answer_chars:
        flags.append("very_short_answer")
    if question and not _looks_like_question(question):
        flags.append("question_mark_missing")
    if lexical_overlap < low_overlap_threshold:
        flags.append("low_lexical_overlap")

    reviewed = dict(row)
    reviewed["review_flags"] = flags
    reviewed["auto_reject_reasons"] = reject_reasons
    reviewed["review_status"] = "rejected" if reject_reasons else "approved"
    return reviewed


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    ensure_parent(path)
    with path.open("w", encoding="utf-8", newline="\n") as file:
        for row in rows:
            file.write(json.dumps(row, ensure_ascii=False) + "\n")


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    ensure_parent(path)
    fieldnames = [
        "question_id",
        "review_status",
        "question_type",
        "lexical_overlap",
        "review_flags",
        "auto_reject_reasons",
        "question",
        "gold_doc_ids",
        "gold_pages",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "question_id": row.get("question_id", ""),
                    "review_status": row.get("review_status", ""),
                    "question_type": row.get("question_type", ""),
                    "lexical_overlap": row.get("lexical_overlap", 0.0),
                    "review_flags": ";".join(row.get("review_flags", [])),
                    "auto_reject_reasons": ";".join(row.get("auto_reject_reasons", [])),
                    "question": row.get("question", ""),
                    "gold_doc_ids": ";".join(str(value) for value in row.get("gold_doc_ids", [])),
                    "gold_pages": ";".join(str(value) for value in row.get("gold_pages", [])),
                }
            )


def _report_markdown(rows: list[dict[str, Any]]) -> str:
    statuses = Counter(str(row.get("review_status", "unknown")) for row in rows)
    types = Counter(str(row.get("question_type", "unknown")) for row in rows)
    reject_reasons = Counter(
        reason for row in rows for reason in row.get("auto_reject_reasons", [])
    )
    flags = Counter(flag for row in rows for flag in row.get("review_flags", []))
    overlaps = [float(row.get("lexical_overlap") or 0.0) for row in rows]

    lines = [
        "# Full Golden Set Auto Review",
        "",
        "This report applies deterministic quality checks to the full unstructured-data Golden Set.",
        "Only high-confidence defects are auto-rejected; softer concerns remain as review flags.",
        "",
        "## Summary",
        "",
        f"- Questions reviewed: {len(rows)}",
        f"- Approved: {statuses.get('approved', 0)}",
        f"- Rejected: {statuses.get('rejected', 0)}",
        f"- Lexical overlap mean: {mean(overlaps):.4f}" if overlaps else "- Lexical overlap mean: 0.0000",
        f"- Lexical overlap median: {median(overlaps):.4f}" if overlaps else "- Lexical overlap median: 0.0000",
        "",
        "## Question type distribution",
        "",
    ]
    for question_type, count in sorted(types.items()):
        lines.append(f"- {question_type}: {count}")
    lines.extend(["", "## Auto-reject reasons", ""])
    if reject_reasons:
        for reason, count in reject_reasons.most_common():
            lines.append(f"- {reason}: {count}")
    else:
        lines.append("- None")
    lines.extend(["", "## Manual-review flags", ""])
    if flags:
        for flag, count in flags.most_common():
            lines.append(f"- {flag}: {count}")
    else:
        lines.append("- None")
    lines.extend(
        [
            "",
            "## Recommended use",
            "",
            "- Use the reviewed JSONL for portfolio-facing retrieval metrics.",
            "- Manually inspect rows with `review_flags` before calling the benchmark final.",
            "- Keep the original candidate JSONL as a reproducible generation artifact.",
            "",
        ]
    )
    return "\n".join(lines)


@app.command()
def run(
    input_jsonl: Path,
    output_jsonl: Path,
    review_csv: Path,
    report_md: Path,
    min_evidence_chars: int = 80,
    min_answer_chars: int = 2,
    low_overlap_threshold: float = 0.05,
) -> None:
    """Create a reviewed Golden Set JSONL plus human-readable review artifacts."""
    seen_questions: set[str] = set()
    reviewed = [
        review_row(
            row,
            seen_questions,
            min_evidence_chars=min_evidence_chars,
            min_answer_chars=min_answer_chars,
            low_overlap_threshold=low_overlap_threshold,
        )
        for row in read_jsonl(input_jsonl)
    ]
    _write_jsonl(output_jsonl, reviewed)
    _write_csv(review_csv, reviewed)
    ensure_parent(report_md)
    report_md.write_text(_report_markdown(reviewed), encoding="utf-8")

    statuses = Counter(str(row.get("review_status", "unknown")) for row in reviewed)
    typer.echo(
        "Reviewed "
        f"{len(reviewed)} questions: "
        f"approved={statuses.get('approved', 0)}, "
        f"rejected={statuses.get('rejected', 0)}"
    )


def main() -> None:
    app()
