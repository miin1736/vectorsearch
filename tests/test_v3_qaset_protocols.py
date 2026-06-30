from __future__ import annotations

from pathlib import Path

from koreanops_rag.io import write_jsonl
from koreanops_rag.v3.qaset_protocols import (
    PROTOCOL_IDS,
    build_all_protocols,
    build_protocol_rows,
    finalize_canonical_qaset,
    summarize_qaset,
    summarize_retrieval_summary,
)


def _doc(doc_id: str, title: str, page_count: int = 10, field: str = "ai") -> dict:
    return {
        "doc_id": doc_id,
        "source_type": "academic_paper",
        "title": title,
        "content": title * 100,
        "embedding_text": title * 100,
        "metadata": {
            "page_count": page_count,
            "research_field": field,
            "paper_topic": title,
        },
    }


def _section(
    doc_id: str,
    section_type: str,
    page_start: int,
    text: str,
    index: int,
) -> dict:
    return {
        "doc_id": doc_id,
        "section_id": f"{doc_id}_{section_type}_{index}",
        "section_index": index,
        "section_type": section_type,
        "section_title": section_type,
        "page_start": page_start,
        "page_end": page_start,
        "text": text,
        "char_count": len(text),
    }


def _write_fixture(tmp_path: Path) -> tuple[Path, Path]:
    docs = tmp_path / "documents.jsonl"
    sections = tmp_path / "sections.jsonl"
    write_jsonl(
        docs,
        [
            _doc("paper_a", "neural retrieval ranking"),
            _doc("paper_b", "neural retrieval reranking"),
            _doc("paper_c", "dense retrieval ranking"),
            _doc("paper_d", "hybrid retrieval ranking"),
        ],
    )
    rows = []
    for index, doc_id in enumerate(["paper_a", "paper_b", "paper_c", "paper_d"], start=1):
        rows.extend(
            [
                _section(doc_id, "abstract", 1, "abstract evidence " * 40, index * 10),
                _section(doc_id, "method", 6, "method evidence retrieval ranking " * 40, index * 10 + 1),
                _section(doc_id, "result", 9, "result evidence latency recall " * 40, index * 10 + 2),
            ]
        )
    write_jsonl(sections, rows)
    return docs, sections


def test_build_protocol_rows_adds_protocol_metadata(tmp_path: Path) -> None:
    docs, sections = _write_fixture(tmp_path)

    rows = build_protocol_rows(
        "qaset_low_lexical_overlap",
        docs,
        sections,
        limit=3,
        min_evidence_chars=20,
    )

    assert len(rows) == 3
    assert rows[0]["qaset_protocol"] == "qaset_low_lexical_overlap"
    assert rows[0]["question_id"].startswith("qaset_low_lexical_overlap_")
    assert "page_position_ratio" in rows[0]
    assert rows[0]["lexical_overlap"] < 0.55


def test_build_all_protocols_writes_each_protocol(tmp_path: Path) -> None:
    docs, sections = _write_fixture(tmp_path)
    output_dir = tmp_path / "qaset_protocols"

    outputs = build_all_protocols(
        docs,
        sections,
        output_dir,
        protocols=list(PROTOCOL_IDS[:2]),
        limit=2,
        min_evidence_chars=20,
    )

    assert [path.name for path in outputs] == ["qaset_balanced.jsonl", "qaset_hard_negative.jsonl"]
    assert all(path.exists() for path in outputs)


def test_summarize_qaset_reports_quality_fields(tmp_path: Path) -> None:
    docs, sections = _write_fixture(tmp_path)
    rows = build_protocol_rows("qaset_late_evidence", docs, sections, limit=3, min_evidence_chars=20)
    output = tmp_path / "late.jsonl"
    write_jsonl(output, rows)

    summary = summarize_qaset(output)

    assert summary["qaset_protocol"] == "qaset_late_evidence"
    assert summary["questions"] == 3
    assert summary["avg_hard_negatives"] >= 1
    assert summary["late_evidence_ratio"] > 0


def test_summarize_retrieval_summary_reports_spread(tmp_path: Path) -> None:
    path = tmp_path / "qaset_demo.summary.csv"
    path.write_text(
        "\n".join(
            [
                "case_id,method,group,questions,recall_at_5,recall_at_10,mrr,ndcg_at_10,context_precision_at_10,p50_latency_ms,p95_latency_ms",
                "fixed,bm25,overall,2,1,1.0,0.9,0.95,0.1,10,20",
                "fixed,vector,overall,2,0,0.5,0.3,0.4,0.1,12,22",
                "section,bm25,method,2,1,1.0,0.9,0.95,0.1,10,20",
            ]
        ),
        encoding="utf-8",
    )

    summary = summarize_retrieval_summary(path)

    assert summary["qaset_protocol"] == "qaset_demo"
    assert summary["overall_rows"] == 2
    assert summary["spread_recall_at_10"] == 0.5
    assert summary["bm25_vector_gap"] == 0.5


def test_finalize_canonical_qaset_promotes_non_rejected_rows(tmp_path: Path) -> None:
    input_jsonl = tmp_path / "candidate.jsonl"
    output_jsonl = tmp_path / "reviewed.jsonl"
    report_md = tmp_path / "report.md"
    write_jsonl(
        input_jsonl,
        [
            {
                "question_id": "q1",
                "review_status": "approved_auto_review",
                "review_flags": [],
                "question_type": "method",
                "difficulty": "hard",
            },
            {
                "question_id": "q2",
                "review_status": "manual_review",
                "review_flags": ["low_lexical_overlap"],
                "question_type": "purpose",
                "difficulty": "adversarial",
            },
            {
                "question_id": "q3",
                "review_status": "rejected",
                "review_flags": [],
            },
        ],
    )

    rows = finalize_canonical_qaset(input_jsonl, output_jsonl, report_md)

    assert [row["question_id"] for row in rows] == ["q1", "q2"]
    assert rows[0]["review_status"] == "approved_auto_review"
    assert rows[1]["review_status"] == "approved_provisional_review"
    assert rows[1]["requires_human_review"] is True
    assert report_md.exists()
