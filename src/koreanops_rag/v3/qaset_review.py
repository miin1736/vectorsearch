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


def _question_key(question: str) -> str:
    return " ".join(question.strip().lower().split())


def _mojibake_score(text: str) -> float:
    if not text:
        return 0.0
    suspicious = sum(text.count(char) for char in ["�", "媛", "쒕", "뿉", "???"])
    question_marks = text.count("?")
    return min((suspicious + question_marks) / max(len(text), 1), 1.0)


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value in (None, ""):
        return []
    return [value]


def review_qaset_row(
    row: dict[str, Any],
    seen_questions: set[str] | None = None,
    *,
    min_evidence_chars: int = 240,
    low_overlap_threshold: float = 0.15,
    high_overlap_threshold: float = 0.55,
    min_hard_negatives: int = 5,
    mojibake_threshold: float = 0.08,
) -> dict[str, Any]:
    """Review one V3 QASET row with conservative auto-reject rules."""
    seen_questions = seen_questions if seen_questions is not None else set()
    reviewed = dict(row)
    flags = set(str(flag) for flag in _as_list(row.get("review_flags")))
    reject_reasons: list[str] = []

    question = str(row.get("question") or "").strip()
    evidence = str(row.get("evidence_text") or "").strip()
    answer = str(row.get("reference_answer") or "").strip()
    gold_doc_ids = _as_list(row.get("gold_doc_ids"))
    gold_pages = _as_list(row.get("gold_pages"))
    hard_negatives = _as_list(row.get("hard_negative_doc_ids"))
    lexical_overlap = float(row.get("lexical_overlap") or 0.0)

    if not question:
        reject_reasons.append("missing_question")
    if not evidence:
        reject_reasons.append("missing_evidence")
    if not answer:
        reject_reasons.append("missing_reference_answer")
    if not gold_doc_ids:
        reject_reasons.append("missing_gold_doc_ids")
    if not gold_pages:
        reject_reasons.append("missing_gold_pages")
    if evidence and len(evidence) < min_evidence_chars:
        reject_reasons.append("too_short_evidence")

    key = _question_key(question)
    if key and key in seen_questions:
        reject_reasons.append("duplicate_question")
    elif key:
        seen_questions.add(key)

    if lexical_overlap < low_overlap_threshold:
        flags.add("low_lexical_overlap")
    if lexical_overlap > high_overlap_threshold:
        flags.add("high_lexical_overlap")
    if len(hard_negatives) < min_hard_negatives:
        flags.add("few_hard_negatives")
    if _mojibake_score(question) > mojibake_threshold or _mojibake_score(evidence) > mojibake_threshold:
        flags.add("encoding_noise")
    if str(row.get("gold_section") or "") == "abstract":
        flags.add("abstract_based")

    reviewed["review_flags"] = sorted(flags)
    reviewed["auto_reject_reasons"] = reject_reasons
    if reject_reasons:
        reviewed["review_status"] = "rejected"
    elif flags:
        reviewed["review_status"] = "manual_review"
    else:
        reviewed["review_status"] = "approved_auto_review"
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
        "difficulty",
        "lexical_overlap",
        "review_flags",
        "auto_reject_reasons",
        "hard_negative_count",
        "gold_section",
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
                    "difficulty": row.get("difficulty", ""),
                    "lexical_overlap": row.get("lexical_overlap", 0.0),
                    "review_flags": ";".join(row.get("review_flags", [])),
                    "auto_reject_reasons": ";".join(row.get("auto_reject_reasons", [])),
                    "hard_negative_count": len(_as_list(row.get("hard_negative_doc_ids"))),
                    "gold_section": row.get("gold_section", ""),
                    "question": row.get("question", ""),
                    "gold_doc_ids": ";".join(str(value) for value in _as_list(row.get("gold_doc_ids"))),
                    "gold_pages": ";".join(str(value) for value in _as_list(row.get("gold_pages"))),
                }
            )


def review_report(rows: list[dict[str, Any]], source: Path, output_jsonl: Path) -> str:
    statuses = Counter(str(row.get("review_status", "unknown")) for row in rows)
    types = Counter(str(row.get("question_type", "unknown")) for row in rows)
    difficulties = Counter(str(row.get("difficulty", "unknown")) for row in rows)
    flags = Counter(flag for row in rows for flag in row.get("review_flags", []))
    rejects = Counter(reason for row in rows for reason in row.get("auto_reject_reasons", []))
    overlaps = [float(row.get("lexical_overlap") or 0.0) for row in rows]
    hard_negative_counts = [len(_as_list(row.get("hard_negative_doc_ids"))) for row in rows]

    lines = [
        "# V3 Pilot QASET Review",
        "",
        f"- Source: `{source}`",
        f"- Reviewed JSONL: `{output_jsonl}`",
        f"- Questions reviewed: {len(rows)}",
        f"- Approved automatically: {statuses.get('approved_auto_review', 0)}",
        f"- Manual review queue: {statuses.get('manual_review', 0)}",
        f"- Rejected: {statuses.get('rejected', 0)}",
        f"- Lexical overlap mean: {mean(overlaps):.4f}" if overlaps else "- Lexical overlap mean: 0.0000",
        f"- Lexical overlap median: {median(overlaps):.4f}" if overlaps else "- Lexical overlap median: 0.0000",
        f"- Avg hard negatives: {mean(hard_negative_counts):.2f}"
        if hard_negative_counts
        else "- Avg hard negatives: 0.00",
        "",
        "## Status Distribution",
        "",
    ]
    for status, count in sorted(statuses.items()):
        lines.append(f"- {status}: {count}")
    lines.extend(["", "## Question Type Distribution", ""])
    for question_type, count in sorted(types.items()):
        lines.append(f"- {question_type}: {count}")
    lines.extend(["", "## Difficulty Distribution", ""])
    for difficulty, count in sorted(difficulties.items()):
        lines.append(f"- {difficulty}: {count}")
    lines.extend(["", "## Manual Review Flags", ""])
    if flags:
        for flag, count in flags.most_common():
            lines.append(f"- {flag}: {count}")
    else:
        lines.append("- None")
    lines.extend(["", "## Auto Reject Reasons", ""])
    if rejects:
        for reason, count in rejects.most_common():
            lines.append(f"- {reason}: {count}")
    else:
        lines.append("- None")
    lines.extend(
        [
            "",
            "## Recommended Use",
            "",
            "- Use rows marked `approved_auto_review` and `manual_review` for pilot analysis.",
            "- Do not call this a final benchmark until `manual_review` rows are inspected.",
            "- Low lexical overlap is a review flag, not an automatic defect.",
            "- Encoding noise should be revised or rejected during manual review.",
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
    min_evidence_chars: int = 240,
    low_overlap_threshold: float = 0.15,
    high_overlap_threshold: float = 0.55,
    min_hard_negatives: int = 5,
    mojibake_threshold: float = 0.08,
) -> None:
    """Review a V3 QASET candidate file and create review artifacts."""
    seen_questions: set[str] = set()
    reviewed = [
        review_qaset_row(
            row,
            seen_questions,
            min_evidence_chars=min_evidence_chars,
            low_overlap_threshold=low_overlap_threshold,
            high_overlap_threshold=high_overlap_threshold,
            min_hard_negatives=min_hard_negatives,
            mojibake_threshold=mojibake_threshold,
        )
        for row in read_jsonl(input_jsonl)
    ]
    _write_jsonl(output_jsonl, reviewed)
    _write_csv(review_csv, reviewed)
    ensure_parent(report_md)
    report_md.write_text(review_report(reviewed, input_jsonl, output_jsonl), encoding="utf-8")

    statuses = Counter(str(row.get("review_status", "unknown")) for row in reviewed)
    typer.echo(
        "Reviewed "
        f"{len(reviewed)} questions: "
        f"approved_auto_review={statuses.get('approved_auto_review', 0)}, "
        f"manual_review={statuses.get('manual_review', 0)}, "
        f"rejected={statuses.get('rejected', 0)}"
    )


def main() -> None:
    app()
