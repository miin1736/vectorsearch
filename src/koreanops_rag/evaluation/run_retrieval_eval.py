from __future__ import annotations

import csv
import time
from pathlib import Path
from typing import Protocol

import typer

from koreanops_rag.config import load_config
from koreanops_rag.evaluation.metrics import ndcg_at_k, percentile, recall_at_k, reciprocal_rank
from koreanops_rag.io import read_jsonl
from koreanops_rag.retrieval.bm25_opensearch import OpenSearchBM25Retriever
from koreanops_rag.retrieval.hybrid import HybridRetriever
from koreanops_rag.retrieval.vector_qdrant import QdrantVectorRetriever, SentenceTransformerEmbedder

app = typer.Typer(add_completion=False)


class EvalRetriever(Protocol):
    def search(self, query: str, top_k: int): ...


def _match_id(result, match_parent: bool) -> str:
    if match_parent:
        return str(result.metadata.get("parent_doc_id") or result.doc_id)
    return result.doc_id


def _dedupe_ordered(doc_ids: list[str]) -> list[str]:
    seen = set()
    deduped = []
    for doc_id in doc_ids:
        if doc_id in seen:
            continue
        seen.add(doc_id)
        deduped.append(doc_id)
    return deduped


def evaluate_rows(
    retriever: EvalRetriever,
    questions_path: Path,
    top_k: int = 10,
    match_parent: bool = False,
) -> dict[str, float]:
    recalls_5: list[float] = []
    recalls_10: list[float] = []
    mrrs: list[float] = []
    ndcgs: list[float] = []
    latencies_ms: list[float] = []
    for row in read_jsonl(questions_path):
        search_k = top_k * 5 if match_parent else top_k
        start = time.perf_counter()
        results = retriever.search(row["question"], top_k=search_k)
        latencies_ms.append((time.perf_counter() - start) * 1000)
        retrieved = [_match_id(result, match_parent) for result in results]
        if match_parent:
            retrieved = _dedupe_ordered(retrieved)
        gold = set(row.get("gold_doc_ids", []))
        recalls_5.append(recall_at_k(retrieved, gold, 5))
        recalls_10.append(recall_at_k(retrieved, gold, 10))
        mrrs.append(reciprocal_rank(retrieved, gold))
        ndcgs.append(ndcg_at_k(retrieved, gold, 10))
    n = max(len(recalls_10), 1)
    return {
        "questions": float(n),
        "recall_at_5": sum(recalls_5) / n,
        "recall_at_10": sum(recalls_10) / n,
        "mrr": sum(mrrs) / n,
        "ndcg_at_10": sum(ndcgs) / n,
        "p50_latency_ms": percentile(latencies_ms, 50),
        "p95_latency_ms": percentile(latencies_ms, 95),
    }


def write_metrics(metrics_csv: Path, method: str, metrics: dict[str, float]) -> None:
    metrics_csv.parent.mkdir(parents=True, exist_ok=True)
    exists = metrics_csv.exists()
    with metrics_csv.open("a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["method", *metrics.keys()])
        if not exists:
            writer.writeheader()
        writer.writerow({"method": method, **metrics})


@app.command()
def run(
    questions_jsonl: Path,
    metrics_csv: Path,
    config_path: Path = Path("configs/default.yaml"),
    top_k: int = 10,
    candidate_k: int = 50,
    match_parent: bool = False,
) -> None:
    """Evaluate BM25, vector, and hybrid retrieval methods against gold doc ids."""
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
    hybrid = HybridRetriever(bm25, vector, rrf_k=config.retrieval.rrf_k)

    methods: dict[str, EvalRetriever] = {
        "bm25": bm25,
        "vector": vector,
        "hybrid": _HybridEvalAdapter(hybrid, candidate_k=candidate_k),
    }
    if metrics_csv.exists():
        metrics_csv.unlink()
    for method, retriever in methods.items():
        metrics = evaluate_rows(
            retriever,
            questions_jsonl,
            top_k=top_k,
            match_parent=match_parent,
        )
        write_metrics(metrics_csv, method, metrics)
        typer.echo(f"{method}: {metrics}")


class _HybridEvalAdapter:
    def __init__(self, retriever: HybridRetriever, candidate_k: int):
        self.retriever = retriever
        self.candidate_k = candidate_k

    def search(self, query: str, top_k: int):
        return self.retriever.search(query, top_k=top_k, candidate_k=self.candidate_k)


def main() -> None:
    app()
