from koreanops_rag.evaluation.metrics import ndcg_at_k, percentile, recall_at_k, reciprocal_rank


def test_retrieval_metrics():
    retrieved = ["d3", "d1", "d2"]
    gold = {"d1", "d2"}

    assert recall_at_k(retrieved, gold, 1) == 0.0
    assert recall_at_k(retrieved, gold, 3) == 1.0
    assert reciprocal_rank(retrieved, gold) == 0.5
    assert 0.0 < ndcg_at_k(retrieved, gold, 3) <= 1.0


def test_percentile_interpolates():
    assert percentile([10, 20, 30], 50) == 20
    assert percentile([10, 20], 95) == 19.5
