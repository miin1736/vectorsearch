from __future__ import annotations

from typing import Any

from koreanops_rag.schemas import SearchResult


class OpenSearchBM25Retriever:
    def __init__(
        self,
        url: str,
        index: str,
        username: str = "admin",
        password: str = "admin",
        search_field: str = "content",
    ):
        from opensearchpy import OpenSearch

        self.index = index
        self.search_field = search_field
        self.client = OpenSearch(
            hosts=[url],
            http_auth=(username, password),
            use_ssl=url.startswith("https"),
            verify_certs=False,
            ssl_show_warn=False,
        )

    def search(
        self,
        query: str,
        top_k: int = 10,
        filters: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        must: list[dict[str, Any]] = [{"match": {self.search_field: query}}]
        filter_clauses = []
        for key, value in (filters or {}).items():
            filter_clauses.append({"term": {f"metadata.{key}.keyword": value}})
        body = {
            "size": top_k,
            "query": {"bool": {"must": must, "filter": filter_clauses}},
        }
        response = self.client.search(index=self.index, body=body)
        results = []
        for idx, hit in enumerate(response["hits"]["hits"], start=1):
            source = hit["_source"]
            results.append(
                SearchResult(
                    doc_id=source["doc_id"],
                    score=float(hit["_score"]),
                    rank=idx,
                    title=source.get("title", ""),
                    content=source.get("content", ""),
                    metadata=source.get("metadata", {}),
                    source_scores={"bm25": float(hit["_score"])},
                )
            )
        return results
