from __future__ import annotations

from pathlib import Path

from koreanops_rag.io import read_jsonl, write_jsonl
from koreanops_rag.schemas import SearchResult
from koreanops_rag.v3.retrieval_eval import (
    HybridRrfEvalRetriever,
    build_golden_questions,
    evaluate_method,
    summarize,
)


class StubRetriever:
    def __init__(self, results: list[SearchResult]) -> None:
        self.results = results

    def search(self, query: str, top_k: int) -> list[SearchResult]:
        return self.results[:top_k]


class StubHybridRetriever:
    def __init__(self) -> None:
        self.calls = []

    def search(self, query: str, top_k: int, candidate_k: int):
        self.calls.append((query, top_k, candidate_k))
        return []


def _doc(doc_id: str, title: str, field: str = "science") -> dict:
    return {
        "doc_id": doc_id,
        "title": title,
        "content": "content",
        "metadata": {
            "research_field": field,
            "paper_topic": title,
        },
    }


def test_v3_build_golden_questions_from_sections(tmp_path: Path) -> None:
    docs = tmp_path / "documents.jsonl"
    sections = tmp_path / "sections.jsonl"
    output = tmp_path / "golden.jsonl"
    write_jsonl(docs, [_doc("paper_a", "Dense Retrieval Study"), _doc("paper_b", "Retrieval Study")])
    write_jsonl(
        sections,
        [
            {
                "doc_id": "paper_a",
                "section_id": "paper_a__section_0001",
                "section_index": 1,
                "section_type": "method",
                "page_start": 2,
                "page_end": 3,
                "text": "method evidence " * 40,
            }
        ],
    )

    rows = build_golden_questions(docs, sections, output, limit=10, min_evidence_chars=20)

    assert len(rows) == 1
    assert rows[0]["gold_doc_ids"] == ["paper_a"]
    assert rows[0]["gold_pages"] == [2, 3]
    assert rows[0]["question_type"] == "method"
    assert rows[0]["review_status"] == "candidate"
    assert rows[0]["hard_negative_doc_ids"] == ["paper_b"]
    assert rows[0]["difficulty"] in {"easy", "medium", "hard", "adversarial"}
    assert "review_flags" in rows[0]
    assert list(read_jsonl(output))[0]["question_id"] == "v3_balanced_0001"


def test_v3_evaluate_method_uses_parent_doc_ids() -> None:
    retriever = StubRetriever(
        [
            SearchResult(
                doc_id="paper_x__chunk_00001",
                score=1.0,
                rank=1,
                title="x",
                content="x",
                metadata={"parent_doc_id": "paper_x"},
            ),
            SearchResult(
                doc_id="paper_a__chunk_00001",
                score=0.9,
                rank=2,
                title="a",
                content="method evidence answer",
                metadata={"parent_doc_id": "paper_a", "page_start": 2, "page_end": 3, "section_id": "s1"},
            ),
        ]
    )
    questions = [
        {
            "question_id": "q1",
            "question": "method?",
            "gold_doc_ids": ["paper_a"],
            "question_type": "method",
            "evidence_text": "method evidence",
        }
    ]

    rows = evaluate_method(
        case_id="fixed_512",
        method="vector",
        retriever=retriever,
        questions=questions,
        top_k=10,
    )
    summary = summarize(rows)

    assert rows[0]["rank"] == 2
    assert rows[0]["recall_at_5"] == 1.0
    assert rows[0]["mrr"] == 0.5
    assert rows[0]["retrieved_chunk_ids"]
    assert "paper_a__chunk_00001" in rows[0]["retrieved_chunk_ids"]
    assert "2-3" in rows[0]["retrieved_pages"]
    assert rows[0]["gold_evidence_in_retrieved_context"] > 0
    assert "gold_evidence_in_retrieved_context" in summary[0]
    assert summary[0]["case_id"] == "fixed_512"


def test_v3_hybrid_rrf_eval_retriever_passes_candidate_k() -> None:
    hybrid = StubHybridRetriever()
    retriever = HybridRrfEvalRetriever(hybrid, candidate_k=75)  # type: ignore[arg-type]

    retriever.search("query", top_k=10)

    assert hybrid.calls == [("query", 10, 75)]

