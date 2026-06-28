from koreanops_rag.office.evaluate_retrieval import (
    _bootstrap_ci,
    _dedupe_parents,
    evaluate_method,
)
from koreanops_rag.schemas import SearchResult


def test_dedupe_parents_keeps_best_ranked_chunk():
    results = [
        SearchResult(
            doc_id="a_1", score=1.0, rank=1, metadata={"parent_doc_id": "a"}
        ),
        SearchResult(
            doc_id="a_2", score=0.9, rank=2, metadata={"parent_doc_id": "a"}
        ),
        SearchResult(
            doc_id="b_1", score=0.8, rank=3, metadata={"parent_doc_id": "b"}
        ),
    ]

    deduped = _dedupe_parents(results)

    assert [item.doc_id for item in deduped] == ["a_1", "b_1"]


def test_bootstrap_ci_is_bounded():
    low, high = _bootstrap_ci([0.0, 1.0, 1.0, 1.0], samples=100)

    assert 0.0 <= low <= high <= 1.0


class StubRetriever:
    def __init__(self, results):
        self.results = results

    def search(self, query: str, top_k: int):
        return self.results[:top_k]


def test_evaluate_method_requires_gold_page_overlap():
    retriever = StubRetriever(
        [
            SearchResult(
                doc_id="wrong_page",
                score=1.0,
                rank=1,
                metadata={"parent_doc_id": "parent", "page_start": 1, "page_end": 1},
            ),
            SearchResult(
                doc_id="gold_page",
                score=0.9,
                rank=2,
                metadata={"parent_doc_id": "parent", "page_start": 3, "page_end": 3},
            ),
        ]
    )

    rows = evaluate_method(
        "vector",
        retriever,
        [
            {
                "question_id": "q1",
                "question": "질문",
                "gold_doc_ids": ["parent"],
                "gold_pages": [3],
            }
        ],
        top_k=10,
    )

    assert rows[0]["rank"] == 0
    assert rows[0]["recall_at_10"] == 0.0
