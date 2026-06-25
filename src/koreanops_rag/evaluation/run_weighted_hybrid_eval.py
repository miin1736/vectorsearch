from __future__ import annotations

import csv
from pathlib import Path

import typer

from koreanops_rag.config import load_config
from koreanops_rag.evaluation.run_retrieval_eval import evaluate_rows
from koreanops_rag.retrieval.bm25_opensearch import OpenSearchBM25Retriever
from koreanops_rag.retrieval.fusion import reciprocal_rank_fusion
from koreanops_rag.retrieval.vector_qdrant import QdrantVectorRetriever, SentenceTransformerEmbedder

app = typer.Typer(add_completion=False)


class WeightedHybridEvalRetriever:
    def __init__(
        self,
        bm25: OpenSearchBM25Retriever,
        vector: QdrantVectorRetriever,
        bm25_weight: float,
        vector_weight: float,
        rrf_k: int,
        candidate_k: int,
    ):
        self.bm25 = bm25
        self.vector = vector
        self.bm25_weight = bm25_weight
        self.vector_weight = vector_weight
        self.rrf_k = rrf_k
        self.candidate_k = candidate_k

    def search(self, query: str, top_k: int):
        bm25_results = self.bm25.search(query, top_k=self.candidate_k)
        vector_results = self.vector.search(query, top_k=self.candidate_k)
        return reciprocal_rank_fusion(
            {"bm25": bm25_results, "vector": vector_results},
            top_k=top_k,
            rrf_k=self.rrf_k,
            weights={"bm25": self.bm25_weight, "vector": self.vector_weight},
        )


def write_rows(metrics_csv: Path, rows: list[dict]) -> None:
    metrics_csv.parent.mkdir(parents=True, exist_ok=True)
    with metrics_csv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


@app.command()
def run(
    questions_jsonl: Path,
    metrics_csv: Path,
    config_path: Path = Path("configs/default.yaml"),
    top_k: int = 10,
    candidate_k: int = 50,
    bm25_weights: str = "0.6,0.7,0.8,0.9",
    vector_weight: float = 1.0,
    match_parent: bool = False,
) -> None:
    """Evaluate BM25-heavy weighted RRF settings."""
    config = load_config(config_path)
    bm25 = OpenSearchBM25Retriever(
        config.opensearch.url,
        config.opensearch.index,
        config.opensearch.username,
        config.opensearch.password,
    )
    embedder = SentenceTransformerEmbedder(
        config.embedding.model_name,
        config.embedding.device,
        document_prefix=config.embedding.document_prefix,
        query_prefix=config.embedding.query_prefix,
    )
    vector = QdrantVectorRetriever(config.qdrant.url, config.qdrant.collection, embedder)

    rows = []
    for bm25_weight in [float(item.strip()) for item in bm25_weights.split(",") if item.strip()]:
        retriever = WeightedHybridEvalRetriever(
            bm25,
            vector,
            bm25_weight=bm25_weight,
            vector_weight=vector_weight,
            rrf_k=config.retrieval.rrf_k,
            candidate_k=candidate_k,
        )
        metrics = evaluate_rows(
            retriever,
            questions_jsonl,
            top_k=top_k,
            match_parent=match_parent,
        )
        row = {
            "method": "weighted_hybrid",
            "bm25_weight": bm25_weight,
            "vector_weight": vector_weight,
            "candidate_k": candidate_k,
            **metrics,
        }
        rows.append(row)
        typer.echo(f"bm25_weight={bm25_weight}, vector_weight={vector_weight}: {metrics}")
    write_rows(metrics_csv, rows)


def main() -> None:
    app()
