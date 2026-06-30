from __future__ import annotations

import csv
import json
import random
from collections import Counter, defaultdict
from dataclasses import dataclass
from os import getenv
from pathlib import Path
from statistics import mean, median
from typing import Any

import typer

from koreanops_rag.io import ensure_parent, read_jsonl, write_jsonl
from koreanops_rag.v3.retrieval_eval import (
    _build_balanced_row,
    _candidate_sort_key,
    _clean_evidence,
    _difficulty,
    _review_flags,
    lexical_overlap,
)

app = typer.Typer(add_completion=False)

PROTOCOL_IDS = (
    "qaset_balanced",
    "qaset_hard_negative",
    "qaset_low_lexical_overlap",
    "qaset_late_evidence",
    "qaset_section_balanced",
)


@dataclass(frozen=True)
class QasetProtocol:
    protocol_id: str
    description: str
    selection_goal: str


QASET_PROTOCOLS = {
    "qaset_balanced": QasetProtocol(
        "qaset_balanced",
        "Question-type balanced baseline.",
        "Keep summary, purpose, method, result, conclusion, and section questions balanced.",
    ),
    "qaset_hard_negative": QasetProtocol(
        "qaset_hard_negative",
        "Hard-negative stress set.",
        "Prefer rows whose gold paper has many same-field or same-topic negative papers.",
    ),
    "qaset_low_lexical_overlap": QasetProtocol(
        "qaset_low_lexical_overlap",
        "Paraphrase stress set.",
        "Lower surface word overlap between question and evidence while keeping gold evidence fixed.",
    ),
    "qaset_late_evidence": QasetProtocol(
        "qaset_late_evidence",
        "Late-document evidence stress set.",
        "Prefer evidence from the middle or later pages of long papers.",
    ),
    "qaset_section_balanced": QasetProtocol(
        "qaset_section_balanced",
        "Paper-section balanced set.",
        "Balance gold sections and reduce abstract-only questions.",
    ),
}


def default_data_root() -> Path:
    return Path(getenv("DATA_ROOT", r"C:\vectorsearch-data")) / "ko-dense-technical"


def default_pilot_processed_path(name: str) -> Path:
    return default_data_root() / "processed" / "pilot_1000" / name


def default_pilot_eval_path(name: str) -> Path:
    return default_data_root() / "eval" / "pilot_1000" / name


def _page_count(doc: dict[str, Any]) -> int:
    metadata = doc.get("metadata", {})
    try:
        return max(int(metadata.get("page_count") or 0), 1)
    except (TypeError, ValueError):
        return 1


def _page_ratio(section: dict[str, Any], doc: dict[str, Any]) -> float:
    try:
        page_start = int(section.get("page_start") or 1)
    except (TypeError, ValueError):
        page_start = 1
    return min(max(page_start / _page_count(doc), 0.0), 1.0)


def _question_for_low_overlap(row: dict[str, Any], index: int) -> str:
    question_type = str(row.get("question_type") or "section")
    pages = row.get("gold_pages") or []
    page_hint = f"pages {min(pages)}-{max(pages)}" if pages else "the cited pages"
    prompts = {
        "summary": "What overall research issue and contribution are supported by the cited evidence?",
        "purpose": "What motivation or background claim is supported by the cited evidence?",
        "method": "What approach, data, model, or procedure is supported by the cited evidence?",
        "result": "What measurement, experiment, condition, or finding is supported by the cited evidence?",
        "conclusion": "What implication, limitation, or final claim is supported by the cited evidence?",
        "section": "What specific point is supported by the cited evidence?",
    }
    return f"{prompts.get(question_type, prompts['section'])} Use {page_hint}. Item {index}."


def _refresh_row_quality(row: dict[str, Any]) -> dict[str, Any]:
    refreshed = dict(row)
    question = str(refreshed.get("question") or "")
    evidence = str(refreshed.get("evidence_text") or "")
    hard_negatives = refreshed.get("hard_negative_doc_ids") or []
    section_type = str(refreshed.get("gold_section") or "body")
    refreshed["lexical_overlap"] = round(lexical_overlap(question, evidence), 6)
    refreshed["difficulty"] = _difficulty(question, evidence, len(hard_negatives))
    refreshed["review_flags"] = _review_flags(
        question=question,
        evidence=evidence,
        hard_negative_count=len(hard_negatives),
        section_type=section_type,
    )
    return refreshed


def _load_base_rows(
    documents_jsonl: Path,
    sections_jsonl: Path,
    *,
    seed: int,
    min_evidence_chars: int,
) -> list[tuple[dict[str, Any], dict[str, Any], dict[str, Any]]]:
    docs = list(read_jsonl(documents_jsonl))
    docs_by_id = {str(doc["doc_id"]): doc for doc in docs}
    rows: list[tuple[dict[str, Any], dict[str, Any], dict[str, Any]]] = []
    for section in read_jsonl(sections_jsonl):
        section_type = str(section.get("section_type") or "body")
        if section_type in {"references", "unknown"}:
            continue
        evidence = _clean_evidence(str(section.get("text") or ""))
        if len(evidence) < min_evidence_chars:
            continue
        doc = docs_by_id.get(str(section.get("doc_id")))
        if doc is None:
            continue
        row = _build_balanced_row(
            index=len(rows) + 1,
            id_prefix="v3_protocol",
            qaset_version="v3_protocol_candidate",
            doc=doc,
            section=section,
            docs=docs,
        )
        rows.append((row, doc, section))

    rng = random.Random(seed)
    rows.sort(key=lambda item: (str(item[0]["gold_doc_ids"][0]), _candidate_sort_key(item[2])))
    rng.shuffle(rows)
    return rows


def _take_balanced_by_question_type(
    candidates: list[tuple[dict[str, Any], dict[str, Any], dict[str, Any]]],
    limit: int,
) -> list[tuple[dict[str, Any], dict[str, Any], dict[str, Any]]]:
    grouped: dict[str, list[tuple[dict[str, Any], dict[str, Any], dict[str, Any]]]] = defaultdict(list)
    for item in candidates:
        grouped[str(item[0].get("question_type") or "section")].append(item)
    target_types = ["summary", "purpose", "method", "result", "conclusion", "section"]
    per_type = max(limit // len(target_types), 1)
    selected = []
    used_doc_ids: set[str] = set()
    for question_type in target_types:
        for item in grouped.get(question_type, []):
            doc_id = str(item[0]["gold_doc_ids"][0])
            if doc_id in used_doc_ids:
                continue
            selected.append(item)
            used_doc_ids.add(doc_id)
            if len([row for row, _, _ in selected if row.get("question_type") == question_type]) >= per_type:
                break
            if len(selected) >= limit:
                break
    if len(selected) < limit:
        for item in candidates:
            doc_id = str(item[0]["gold_doc_ids"][0])
            if doc_id in used_doc_ids:
                continue
            selected.append(item)
            used_doc_ids.add(doc_id)
            if len(selected) >= limit:
                break
    return selected[:limit]


def _take_balanced_by_section(
    candidates: list[tuple[dict[str, Any], dict[str, Any], dict[str, Any]]],
    limit: int,
) -> list[tuple[dict[str, Any], dict[str, Any], dict[str, Any]]]:
    grouped: dict[str, list[tuple[dict[str, Any], dict[str, Any], dict[str, Any]]]] = defaultdict(list)
    for item in candidates:
        grouped[str(item[0].get("gold_section") or "body")].append(item)
    section_order = ["introduction", "method", "experiment", "result", "conclusion", "body", "abstract"]
    per_section = max(limit // len(section_order), 1)
    selected = []
    used_doc_ids: set[str] = set()
    for section_type in section_order:
        for item in grouped.get(section_type, []):
            doc_id = str(item[0]["gold_doc_ids"][0])
            if doc_id in used_doc_ids:
                continue
            selected.append(item)
            used_doc_ids.add(doc_id)
            if len([row for row, _, _ in selected if row.get("gold_section") == section_type]) >= per_section:
                break
            if len(selected) >= limit:
                break
    if len(selected) < limit:
        for item in candidates:
            doc_id = str(item[0]["gold_doc_ids"][0])
            if doc_id in used_doc_ids:
                continue
            selected.append(item)
            used_doc_ids.add(doc_id)
            if len(selected) >= limit:
                break
    return selected[:limit]


def _select_protocol_rows(
    protocol_id: str,
    candidates: list[tuple[dict[str, Any], dict[str, Any], dict[str, Any]]],
    limit: int,
) -> list[tuple[dict[str, Any], dict[str, Any], dict[str, Any]]]:
    if protocol_id == "qaset_hard_negative":
        ranked = sorted(
            candidates,
            key=lambda item: (
                len(item[0].get("hard_negative_doc_ids") or []),
                item[0].get("difficulty") in {"hard", "adversarial"},
                -float(item[0].get("lexical_overlap") or 0.0),
            ),
            reverse=True,
        )
        return _take_balanced_by_question_type(ranked, limit)
    if protocol_id == "qaset_low_lexical_overlap":
        ranked = sorted(candidates, key=lambda item: float(item[0].get("lexical_overlap") or 0.0))
        return _take_balanced_by_question_type(ranked, limit)
    if protocol_id == "qaset_late_evidence":
        ranked = sorted(candidates, key=lambda item: _page_ratio(item[2], item[1]), reverse=True)
        return _take_balanced_by_question_type(ranked, limit)
    if protocol_id == "qaset_section_balanced":
        non_abstract_first = sorted(
            candidates,
            key=lambda item: (str(item[0].get("gold_section") or "") == "abstract", str(item[0].get("gold_section") or "")),
        )
        return _take_balanced_by_section(non_abstract_first, limit)
    return _take_balanced_by_question_type(candidates, limit)


def build_protocol_rows(
    protocol_id: str,
    documents_jsonl: Path,
    sections_jsonl: Path,
    *,
    limit: int = 120,
    seed: int = 42,
    min_evidence_chars: int = 240,
) -> list[dict[str, Any]]:
    if protocol_id not in QASET_PROTOCOLS:
        raise ValueError(f"Unknown QASET protocol: {protocol_id}")
    candidates = _load_base_rows(
        documents_jsonl,
        sections_jsonl,
        seed=seed,
        min_evidence_chars=min_evidence_chars,
    )
    selected = _select_protocol_rows(protocol_id, candidates, limit)
    rows = []
    for index, (row, doc, section) in enumerate(selected, start=1):
        updated = dict(row)
        updated["question_id"] = f"{protocol_id}_{index:04d}"
        updated["qaset_version"] = protocol_id
        updated["qaset_protocol"] = protocol_id
        updated["qaset_protocol_description"] = QASET_PROTOCOLS[protocol_id].description
        updated["page_position_ratio"] = round(_page_ratio(section, doc), 6)
        updated["document_page_count"] = _page_count(doc)
        if protocol_id == "qaset_low_lexical_overlap":
            updated["question"] = _question_for_low_overlap(updated, index)
        rows.append(_refresh_row_quality(updated))
    distribution = Counter(str(row.get("question_type") or "unknown") for row in rows)
    for row in rows:
        row["qaset_distribution"] = dict(distribution)
    return rows


def build_all_protocols(
    documents_jsonl: Path,
    sections_jsonl: Path,
    output_dir: Path,
    *,
    protocols: list[str] | None = None,
    limit: int = 120,
    seed: int = 42,
    min_evidence_chars: int = 240,
) -> list[Path]:
    selected_protocols = protocols or list(PROTOCOL_IDS)
    outputs = []
    for protocol_id in selected_protocols:
        rows = build_protocol_rows(
            protocol_id,
            documents_jsonl,
            sections_jsonl,
            limit=limit,
            seed=seed,
            min_evidence_chars=min_evidence_chars,
        )
        output = output_dir / f"{protocol_id}.jsonl"
        write_jsonl(output, rows)
        outputs.append(output)
    return outputs


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value in (None, ""):
        return []
    return [value]


def summarize_qaset(path: Path) -> dict[str, Any]:
    rows = list(read_jsonl(path))
    overlaps = [float(row.get("lexical_overlap") or 0.0) for row in rows]
    hard_negative_counts = [len(_as_list(row.get("hard_negative_doc_ids"))) for row in rows]
    page_ratios = [float(row.get("page_position_ratio") or 0.0) for row in rows]
    difficulties = Counter(str(row.get("difficulty") or "unknown") for row in rows)
    sections = Counter(str(row.get("gold_section") or "unknown") for row in rows)
    statuses = Counter(str(row.get("review_status") or "unknown") for row in rows)
    challenging = difficulties.get("hard", 0) + difficulties.get("adversarial", 0)
    protocol_id = str(rows[0].get("qaset_protocol") or rows[0].get("qaset_version") or path.stem) if rows else path.stem
    return {
        "qaset_protocol": protocol_id,
        "path": str(path),
        "questions": len(rows),
        "avg_lexical_overlap": round(mean(overlaps), 6) if overlaps else 0.0,
        "median_lexical_overlap": round(median(overlaps), 6) if overlaps else 0.0,
        "low_overlap_ratio": round(sum(1 for value in overlaps if value < 0.2) / len(rows), 6) if rows else 0.0,
        "high_overlap_ratio": round(sum(1 for value in overlaps if value >= 0.55) / len(rows), 6) if rows else 0.0,
        "avg_hard_negatives": round(mean(hard_negative_counts), 6) if hard_negative_counts else 0.0,
        "min_hard_negatives": min(hard_negative_counts) if hard_negative_counts else 0,
        "hard_or_adversarial_ratio": round(challenging / len(rows), 6) if rows else 0.0,
        "late_evidence_ratio": round(sum(1 for value in page_ratios if value >= 0.5) / len(rows), 6) if rows else 0.0,
        "abstract_ratio": round(sections.get("abstract", 0) / len(rows), 6) if rows else 0.0,
        "manual_review_ratio": round(statuses.get("manual_review", 0) / len(rows), 6) if rows else 0.0,
        "rejected_ratio": round(statuses.get("rejected", 0) / len(rows), 6) if rows else 0.0,
        "difficulty_distribution": json.dumps(dict(sorted(difficulties.items())), ensure_ascii=False),
        "section_distribution": json.dumps(dict(sorted(sections.items())), ensure_ascii=False),
    }


def write_summary_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    ensure_parent(path)
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]) if rows else [])
        if rows:
            writer.writeheader()
            writer.writerows(rows)


def write_summary_report(path: Path, rows: list[dict[str, Any]]) -> None:
    ensure_parent(path)
    lines = [
        "# V3 QASET Protocol Comparison",
        "",
        "This report compares QASET generation protocols before selecting the canonical pilot/full evaluation set.",
        "",
        "| Protocol | Questions | Avg lexical overlap | Avg hard negatives | Hard/adversarial | Late evidence | Abstract | Manual review | Rejected |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            "| {qaset_protocol} | {questions} | {avg_lexical_overlap:.3f} | "
            "{avg_hard_negatives:.2f} | {hard_or_adversarial_ratio:.3f} | "
            "{late_evidence_ratio:.3f} | {abstract_ratio:.3f} | "
            "{manual_review_ratio:.3f} | {rejected_ratio:.3f} |".format(**row)
        )
    lines.extend(
        [
            "",
            "## Selection Rule",
            "",
            "- Do not select the protocol with the highest retrieval score.",
            "- Select the protocol that keeps gold evidence clear while exposing ranking differences.",
            "- Prefer sufficient hard negatives, lower lexical overlap, non-abstract evidence, and late-document evidence.",
            "- After deterministic review, freeze one protocol as `qaset_canonical_reviewed` for technique comparison.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def summarize_retrieval_summary(path: Path) -> dict[str, Any]:
    overall_rows = []
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        for row in csv.DictReader(file):
            if row.get("group") == "overall":
                overall_rows.append(row)
    recalls = [float(row["recall_at_10"]) for row in overall_rows]
    mrrs = [float(row["mrr"]) for row in overall_rows]
    ndcgs = [float(row["ndcg_at_10"]) for row in overall_rows]
    bm25_recalls = [float(row["recall_at_10"]) for row in overall_rows if row["method"] == "bm25"]
    vector_recalls = [
        float(row["recall_at_10"]) for row in overall_rows if row["method"] == "vector"
    ]
    protocol = path.name.replace(".summary.csv", "")
    return {
        "qaset_protocol": protocol,
        "summary_csv": str(path),
        "overall_rows": len(overall_rows),
        "max_recall_at_10": round(max(recalls), 6) if recalls else 0.0,
        "min_recall_at_10": round(min(recalls), 6) if recalls else 0.0,
        "spread_recall_at_10": round(max(recalls) - min(recalls), 6) if recalls else 0.0,
        "avg_recall_at_10": round(mean(recalls), 6) if recalls else 0.0,
        "avg_mrr": round(mean(mrrs), 6) if mrrs else 0.0,
        "avg_ndcg_at_10": round(mean(ndcgs), 6) if ndcgs else 0.0,
        "avg_bm25_recall_at_10": round(mean(bm25_recalls), 6) if bm25_recalls else 0.0,
        "avg_vector_recall_at_10": round(mean(vector_recalls), 6) if vector_recalls else 0.0,
        "bm25_vector_gap": round(mean(bm25_recalls) - mean(vector_recalls), 6)
        if bm25_recalls and vector_recalls
        else 0.0,
    }


def write_retrieval_protocol_report(path: Path, rows: list[dict[str, Any]]) -> None:
    ensure_parent(path)
    ranked = sorted(rows, key=lambda row: float(row["spread_recall_at_10"]), reverse=True)
    lines = [
        "# V3 QASET Protocol Retrieval Discrimination",
        "",
        "This report compares how strongly each QASET protocol separates the three pilot baseline chunking strategies.",
        "",
        "| Protocol | Spread R@10 | Avg R@10 | Avg BM25 R@10 | Avg Vector R@10 | BM25-Vector gap | Avg MRR | Avg nDCG@10 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in ranked:
        lines.append(
            "| {qaset_protocol} | {spread_recall_at_10:.3f} | {avg_recall_at_10:.3f} | "
            "{avg_bm25_recall_at_10:.3f} | {avg_vector_recall_at_10:.3f} | "
            "{bm25_vector_gap:.3f} | {avg_mrr:.3f} | {avg_ndcg_at_10:.3f} |".format(**row)
        )
    lines.extend(
        [
            "",
            "## Interpretation Rule",
            "",
            "- Very low average recall means the QASET may be too difficult or under-specified.",
            "- Very high average recall means the QASET may be too easy.",
            "- Higher spread helps reveal differences between chunking/retrieval choices.",
            "- A canonical QASET should balance spread, answerability, review burden, and hard-negative coverage.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def finalize_canonical_qaset(
    input_jsonl: Path,
    output_jsonl: Path,
    report_md: Path,
    *,
    canonical_version: str = "qaset_canonical_reviewed",
) -> list[dict[str, Any]]:
    """Promote a deterministic-reviewed QASET into the canonical pilot benchmark."""
    rows = []
    for row in read_jsonl(input_jsonl):
        if row.get("review_status") == "rejected":
            continue
        finalized = dict(row)
        previous_status = str(finalized.get("review_status") or "")
        finalized["previous_review_status"] = previous_status
        finalized["qaset_version"] = canonical_version
        finalized["qaset_protocol"] = canonical_version
        finalized["canonical_source"] = str(input_jsonl)
        if previous_status == "manual_review":
            finalized["review_status"] = "approved_provisional_review"
            finalized["requires_human_review"] = True
        else:
            finalized["review_status"] = "approved_auto_review"
            finalized["requires_human_review"] = False
        rows.append(finalized)
    write_jsonl(output_jsonl, rows)
    _write_canonical_report(report_md, rows, input_jsonl, output_jsonl)
    return rows


def _write_canonical_report(
    path: Path,
    rows: list[dict[str, Any]],
    input_jsonl: Path,
    output_jsonl: Path,
) -> None:
    ensure_parent(path)
    statuses = Counter(str(row.get("review_status") or "unknown") for row in rows)
    flags = Counter(flag for row in rows for flag in row.get("review_flags", []))
    types = Counter(str(row.get("question_type") or "unknown") for row in rows)
    difficulties = Counter(str(row.get("difficulty") or "unknown") for row in rows)
    lines = [
        "# V3 Canonical QASET Finalization",
        "",
        f"- Source: `{input_jsonl}`",
        f"- Output: `{output_jsonl}`",
        f"- Questions: {len(rows)}",
        f"- Auto-approved: {statuses.get('approved_auto_review', 0)}",
        f"- Provisional human-review rows: {statuses.get('approved_provisional_review', 0)}",
        "",
        "## Review Status",
        "",
    ]
    for status, count in sorted(statuses.items()):
        lines.append(f"- {status}: {count}")
    lines.extend(["", "## Question Types", ""])
    for question_type, count in sorted(types.items()):
        lines.append(f"- {question_type}: {count}")
    lines.extend(["", "## Difficulty", ""])
    for difficulty, count in sorted(difficulties.items()):
        lines.append(f"- {difficulty}: {count}")
    lines.extend(["", "## Preserved Review Flags", ""])
    if flags:
        for flag, count in flags.most_common():
            lines.append(f"- {flag}: {count}")
    else:
        lines.append("- None")
    lines.extend(
        [
            "",
            "## Use",
            "",
            "- Use this file for pilot technique comparison.",
            "- Rows with `requires_human_review=true` are valid for pilot comparison but should be inspected before a final public benchmark.",
            "- Do not regenerate the QASET while comparing chunking/retrieval/reranking techniques.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


@app.command("build")
def build_command(
    documents_jsonl: Path | None = None,
    sections_jsonl: Path | None = None,
    output_dir: Path | None = None,
    protocol: list[str] | None = typer.Option(None, "--protocol"),
    limit: int = typer.Option(120, min=1),
    seed: int = 42,
    min_evidence_chars: int = 240,
) -> None:
    """Build pilot QASET candidates for one or more QASET protocols."""
    documents_jsonl = documents_jsonl or default_pilot_processed_path("documents_normalized.jsonl")
    sections_jsonl = sections_jsonl or default_pilot_processed_path("sections.jsonl")
    output_dir = output_dir or default_pilot_eval_path("qaset_protocols")
    outputs = build_all_protocols(
        documents_jsonl,
        sections_jsonl,
        output_dir,
        protocols=protocol,
        limit=limit,
        seed=seed,
        min_evidence_chars=min_evidence_chars,
    )
    for output in outputs:
        typer.echo(f"Wrote {output}")


@app.command("summarize")
def summarize_command(
    input_jsonl: list[Path] | None = typer.Option(None, "--input-jsonl"),
    output_csv: Path | None = None,
    report_md: Path | None = None,
) -> None:
    """Summarize QASET protocol quality without running retrieval."""
    if input_jsonl:
        paths = input_jsonl
    else:
        paths = sorted(default_pilot_eval_path("qaset_protocols").glob("qaset_*.jsonl"))
    rows = [summarize_qaset(path) for path in paths]
    output_csv = output_csv or default_pilot_eval_path("qaset_protocol_summary.csv")
    report_md = report_md or Path("reports/ko_dense_technical_v3_qaset_protocol_comparison.md")
    write_summary_csv(output_csv, rows)
    write_summary_report(report_md, rows)
    typer.echo(f"Wrote {len(rows)} QASET protocol summary rows to {output_csv}")
    typer.echo(f"Wrote QASET protocol report to {report_md}")


@app.command("summarize-retrieval")
def summarize_retrieval_command(
    summary_csv: list[Path] | None = typer.Option(None, "--summary-csv"),
    output_csv: Path | None = None,
    report_md: Path | None = None,
) -> None:
    """Summarize retrieval discrimination across QASET protocol summary files."""
    if summary_csv:
        paths = summary_csv
    else:
        paths = sorted(default_pilot_eval_path("qaset_protocol_eval").glob("qaset_*.summary.csv"))
    rows = [summarize_retrieval_summary(path) for path in paths]
    output_csv = output_csv or default_pilot_eval_path("qaset_protocol_retrieval_summary.csv")
    report_md = report_md or Path(
        "reports/ko_dense_technical_v3_qaset_protocol_retrieval_comparison.md"
    )
    write_summary_csv(output_csv, rows)
    write_retrieval_protocol_report(report_md, rows)
    typer.echo(f"Wrote {len(rows)} retrieval protocol summary rows to {output_csv}")
    typer.echo(f"Wrote retrieval protocol report to {report_md}")


@app.command("finalize-canonical")
def finalize_canonical_command(
    input_jsonl: Path | None = None,
    output_jsonl: Path | None = None,
    report_md: Path | None = None,
    canonical_version: str = "qaset_canonical_reviewed",
) -> None:
    """Finalize the selected QASET protocol for pilot technique comparison."""
    input_jsonl = input_jsonl or default_pilot_eval_path("qaset_canonical_candidate.jsonl")
    output_jsonl = output_jsonl or default_pilot_eval_path("qaset_canonical_reviewed.jsonl")
    report_md = report_md or Path("reports/ko_dense_technical_v3_qaset_canonical_reviewed.md")
    rows = finalize_canonical_qaset(
        input_jsonl,
        output_jsonl,
        report_md,
        canonical_version=canonical_version,
    )
    statuses = Counter(str(row.get("review_status") or "unknown") for row in rows)
    typer.echo(
        f"Wrote {len(rows)} canonical QASET rows to {output_jsonl}: "
        f"auto={statuses.get('approved_auto_review', 0)}, "
        f"provisional={statuses.get('approved_provisional_review', 0)}"
    )


def main() -> None:
    app()
