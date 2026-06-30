from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from koreanops_rag.schemas import SearchResult


def ensure_model_cache_env() -> None:
    """Keep local model downloads under DATA_ROOT when the shell env is not loaded."""
    data_root = Path(os.environ.get("DATA_ROOT", r"C:\vectorsearch-data"))
    defaults = {
        "HF_HOME": data_root / "models" / "huggingface",
        "SENTENCE_TRANSFORMERS_HOME": data_root / "models" / "huggingface" / "sentence-transformers",
        "TORCH_HOME": data_root / "cache" / "torch",
    }
    for name, path in defaults.items():
        os.environ.setdefault(name, str(path))
        Path(os.environ[name]).mkdir(parents=True, exist_ok=True)


class SentenceTransformerEmbedder:
    def __init__(
        self,
        model_name: str,
        device: str = "cpu",
        document_prefix: str = "",
        query_prefix: str = "",
    ):
        ensure_model_cache_env()
        from sentence_transformers import SentenceTransformer

        self.model = SentenceTransformer(model_name, device=device)
        self.document_prefix = document_prefix
        self.query_prefix = query_prefix

    def encode(
        self,
        texts: list[str],
        batch_size: int = 64,
        text_kind: str = "raw",
    ) -> list[list[float]]:
        prefix = ""
        if text_kind == "document":
            prefix = self.document_prefix
        elif text_kind == "query":
            prefix = self.query_prefix
        encoded_texts = [f"{prefix}{text}" for text in texts] if prefix else texts
        vectors = self.model.encode(
            encoded_texts,
            batch_size=batch_size,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return vectors.tolist()


class QdrantVectorRetriever:
    def __init__(self, url: str, collection: str, embedder: SentenceTransformerEmbedder):
        from qdrant_client import QdrantClient

        self.collection = collection
        self.embedder = embedder
        self.client = QdrantClient(url=url)

    def search(
        self,
        query: str,
        top_k: int = 10,
        filters: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        from qdrant_client import models

        query_vector = self.embedder.encode([query], text_kind="query")[0]
        qdrant_filter = None
        if filters:
            qdrant_filter = models.Filter(
                must=[
                    models.FieldCondition(key=f"metadata.{key}", match=models.MatchValue(value=value))
                    for key, value in filters.items()
                ]
            )
        response = self.client.query_points(
            collection_name=self.collection,
            query=query_vector,
            query_filter=qdrant_filter,
            limit=top_k,
            with_payload=True,
        )
        results = []
        for idx, point in enumerate(response.points, start=1):
            payload = point.payload or {}
            results.append(
                SearchResult(
                    doc_id=str(payload.get("doc_id", point.id)),
                    score=float(point.score),
                    rank=idx,
                    title=str(payload.get("title", "")),
                    content=str(payload.get("content", "")),
                    metadata=dict(payload.get("metadata", {})),
                    source_scores={"vector": float(point.score)},
                )
            )
        return results
