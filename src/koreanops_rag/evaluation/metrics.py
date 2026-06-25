from __future__ import annotations

import math
from collections.abc import Sequence


def recall_at_k(retrieved_doc_ids: Sequence[str], gold_doc_ids: set[str], k: int) -> float:
    if not gold_doc_ids:
        return 0.0
    retrieved = set(retrieved_doc_ids[:k])
    return len(retrieved & gold_doc_ids) / len(gold_doc_ids)


def reciprocal_rank(retrieved_doc_ids: Sequence[str], gold_doc_ids: set[str]) -> float:
    for idx, doc_id in enumerate(retrieved_doc_ids, start=1):
        if doc_id in gold_doc_ids:
            return 1.0 / idx
    return 0.0


def dcg_at_k(retrieved_doc_ids: Sequence[str], gold_doc_ids: set[str], k: int) -> float:
    score = 0.0
    for idx, doc_id in enumerate(retrieved_doc_ids[:k], start=1):
        relevance = 1.0 if doc_id in gold_doc_ids else 0.0
        score += relevance / math.log2(idx + 1)
    return score


def ndcg_at_k(retrieved_doc_ids: Sequence[str], gold_doc_ids: set[str], k: int) -> float:
    ideal_hits = min(len(gold_doc_ids), k)
    if ideal_hits == 0:
        return 0.0
    ideal = sum(1.0 / math.log2(idx + 1) for idx in range(1, ideal_hits + 1))
    return dcg_at_k(retrieved_doc_ids, gold_doc_ids, k) / ideal


def percentile(values: Sequence[float], pct: int) -> float:
    if not values:
        return 0.0
    sorted_values = sorted(values)
    index = (len(sorted_values) - 1) * pct / 100
    lower = math.floor(index)
    upper = math.ceil(index)
    if lower == upper:
        return sorted_values[int(index)]
    return sorted_values[lower] + (sorted_values[upper] - sorted_values[lower]) * (index - lower)
