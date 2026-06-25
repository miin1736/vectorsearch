from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence

from koreanops_rag.schemas import SearchResult


def reciprocal_rank_fusion(
    result_sets: dict[str, Sequence[SearchResult]],
    top_k: int = 10,
    rrf_k: int = 60,
    weights: dict[str, float] | None = None,
) -> list[SearchResult]:
    """Fuse ranked result lists using Reciprocal Rank Fusion."""
    fused_scores: dict[str, float] = defaultdict(float)
    source_scores: dict[str, dict[str, float]] = defaultdict(dict)
    best_result: dict[str, SearchResult] = {}

    for source_name, results in result_sets.items():
        weight = (weights or {}).get(source_name, 1.0)
        for zero_based_rank, result in enumerate(results):
            rank = zero_based_rank + 1
            fused_scores[result.doc_id] += weight / (rrf_k + rank)
            source_scores[result.doc_id][source_name] = result.score
            if result.doc_id not in best_result or result.score > best_result[result.doc_id].score:
                best_result[result.doc_id] = result

    fused = []
    for doc_id, score in fused_scores.items():
        base = best_result[doc_id].model_copy(deep=True)
        base.score = score
        base.source_scores = source_scores[doc_id]
        fused.append(base)

    fused.sort(key=lambda item: item.score, reverse=True)
    for idx, result in enumerate(fused[:top_k], start=1):
        result.rank = idx
    return fused[:top_k]
