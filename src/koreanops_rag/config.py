from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class EmbeddingConfig(BaseModel):
    model_name: str = "intfloat/multilingual-e5-small"
    batch_size: int = 64
    device: str = "cpu"
    document_prefix: str = ""
    query_prefix: str = ""


class RetrievalConfig(BaseModel):
    top_k: int = 10
    candidate_k: int = 50
    rrf_k: int = 60


class QdrantConfig(BaseModel):
    url: str = "http://localhost:6333"
    collection: str = "koreanops_documents"


class OpenSearchConfig(BaseModel):
    url: str = "http://localhost:9200"
    index: str = "koreanops_documents"
    username: str = "admin"
    password: str = "admin"
    search_field: str = "content"


class RagConfig(BaseModel):
    provider: str = "ollama"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1:8b-instruct-q4_K_M"


class EvaluationConfig(BaseModel):
    ragas_sample_size: int = 200
    latency_percentiles: list[int] = Field(default_factory=lambda: [50, 95])


class AppConfig(BaseModel):
    data_root: Path = Path(r"C:\vectorsearch-data")
    embedding: EmbeddingConfig = Field(default_factory=EmbeddingConfig)
    retrieval: RetrievalConfig = Field(default_factory=RetrievalConfig)
    qdrant: QdrantConfig = Field(default_factory=QdrantConfig)
    opensearch: OpenSearchConfig = Field(default_factory=OpenSearchConfig)
    rag: RagConfig = Field(default_factory=RagConfig)
    evaluation: EvaluationConfig = Field(default_factory=EvaluationConfig)

    @property
    def raw_dir(self) -> Path:
        return self.data_root / "raw"

    @property
    def processed_dir(self) -> Path:
        return self.data_root / "processed"

    @property
    def eval_dir(self) -> Path:
        return self.data_root / "eval"


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_config(path: str | Path = "configs/default.yaml") -> AppConfig:
    raw = _load_yaml(Path(path))
    config = AppConfig.model_validate(raw)
    if data_root := os.getenv("DATA_ROOT"):
        if "data_root" not in raw:
            config.data_root = Path(data_root)
    if model := os.getenv("EMBEDDING_MODEL"):
        config.embedding.model_name = model
    if batch_size := os.getenv("EMBEDDING_BATCH_SIZE"):
        config.embedding.batch_size = int(batch_size)
    if document_prefix := os.getenv("EMBEDDING_DOCUMENT_PREFIX"):
        config.embedding.document_prefix = document_prefix
    if query_prefix := os.getenv("EMBEDDING_QUERY_PREFIX"):
        config.embedding.query_prefix = query_prefix
    if qdrant_url := os.getenv("QDRANT_URL"):
        config.qdrant.url = qdrant_url
    if opensearch_url := os.getenv("OPENSEARCH_URL"):
        config.opensearch.url = opensearch_url
    if provider := os.getenv("LLM_PROVIDER"):
        config.rag.provider = provider
    if ollama_model := os.getenv("OLLAMA_MODEL"):
        config.rag.ollama_model = ollama_model
    return config
