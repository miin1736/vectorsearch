from koreanops_rag.retrieval.fusion import reciprocal_rank_fusion
from koreanops_rag.schemas import SearchResult


def result(doc_id: str, score: float, rank: int) -> SearchResult:
    return SearchResult(doc_id=doc_id, score=score, rank=rank)


def test_reciprocal_rank_fusion_merges_by_doc_id():
    fused = reciprocal_rank_fusion(
        {
            "bm25": [result("a", 10.0, 1), result("b", 5.0, 2)],
            "vector": [result("b", 0.9, 1), result("c", 0.8, 2)],
        },
        top_k=3,
        rrf_k=60,
    )

    assert [item.doc_id for item in fused] == ["b", "a", "c"]
    assert fused[0].rank == 1
    assert fused[0].source_scores == {"bm25": 5.0, "vector": 0.9}


def test_reciprocal_rank_fusion_applies_source_weights():
    fused = reciprocal_rank_fusion(
        {
            "bm25": [result("a", 10.0, 1)],
            "vector": [result("b", 0.9, 1)],
        },
        top_k=2,
        rrf_k=60,
        weights={"bm25": 2.0, "vector": 1.0},
    )

    assert [item.doc_id for item in fused] == ["a", "b"]
