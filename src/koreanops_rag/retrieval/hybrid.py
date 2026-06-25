from __future__ import annotations

from typing import Any, Protocol

from koreanops_rag.retrieval.fusion import reciprocal_rank_fusion
from koreanops_rag.schemas import SearchResult


class Retriever(Protocol):
    def search(
        self,
        query: str,
        top_k: int = 10,
        filters: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        ...


class HybridRetriever:
    def __init__(self, bm25: Retriever, vector: Retriever, rrf_k: int = 60):
        self.bm25 = bm25
        self.vector = vector
        self.rrf_k = rrf_k

    def search(
        self,
        query: str,
        top_k: int = 10,
        candidate_k: int = 50,
        filters: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        bm25_results = self.bm25.search(query, top_k=candidate_k, filters=filters)
        vector_results = self.vector.search(query, top_k=candidate_k, filters=filters)
        return reciprocal_rank_fusion(
            {"bm25": bm25_results, "vector": vector_results},
            top_k=top_k,
            rrf_k=self.rrf_k,
        )
