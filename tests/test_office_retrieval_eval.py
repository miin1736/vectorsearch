from koreanops_rag.office.evaluate_retrieval import _bootstrap_ci, _dedupe_parents
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
