from __future__ import annotations

import csv
import random
import time
from collections import defaultdict
from pathlib import Path
from statistics import mean

import typer

from koreanops_rag.config import load_config
from koreanops_rag.evaluation.metrics import ndcg_at_k, reciprocal_rank
from koreanops_rag.evaluation.run_weighted_hybrid_eval import WeightedHybridEvalRetriever
from koreanops_rag.io import ensure_parent, read_jsonl
from koreanops_rag.retrieval.bm25_opensearch import OpenSearchBM25Retriever
from koreanops_rag.retrieval.hybrid import HybridRetriever
from koreanops_rag.retrieval.vector_qdrant import (
    QdrantVectorRetriever,
    SentenceTransformerEmbedder,
)

app = typer.Typer(add_completion=False)


class HybridAdapter:
    def __init__(self, retriever: HybridRetriever, candidate_k: int):
        self.retriever = retriever
        self.candidate_k = candidate_k

    def search(self, query: str, top_k: int):
        return self.retriever.search(query, top_k=top_k, candidate_k=self.candidate_k)


def _parent_id(result) -> str:
    return str(result.metadata.get("parent_doc_id") or result.doc_id)


def _dedupe_parents(results) -> list:
    seen = set()
    output = []
    for result in results:
        parent = _parent_id(result)
        if parent not in seen:
            seen.add(parent)
            output.append(result)
    return output


def _page_overlap(result, gold_pages: set[int]) -> bool:
    if not gold_pages:
        return True
    start = int(result.metadata.get("page_start", 0))
    end = int(result.metadata.get("page_end", start))
    return bool(set(range(start, end + 1)) & gold_pages)


def _bootstrap_ci(values: list[float], seed: int = 42, samples: int = 1000) -> tuple[float, float]:
    if not values:
        return 0.0, 0.0
    random.seed(seed)
    estimates = sorted(
        mean(random.choice(values) for _ in values) for _ in range(samples)
    )
    return estimates[int(samples * 0.025)], estimates[int(samples * 0.975)]


def evaluate_method(method: str, retriever, questions: list[dict], top_k: int) -> list[dict]:
    rows = []
    for question in questions:
        started = time.perf_counter()
        results = _dedupe_parents(retriever.search(question["question"], top_k=top_k * 5))
        latency_ms = (time.perf_counter() - started) * 1000
        results = results[:top_k]
        retrieved = [_parent_id(result) for result in results]
        gold_docs = set(question.get("gold_doc_ids", []))
        gold_pages = set(int(page) for page in question.get("gold_pages", []))
        relevant = [
            result
            for result in results
            if _parent_id(result) in gold_docs and _page_overlap(result, gold_pages)
        ]
        rank = next(
            (index for index, doc_id in enumerate(retrieved, start=1) if doc_id in gold_docs),
            0,
        )
        rows.append(
            {
                "question_id": question.get("question_id", ""),
                "question_type": question.get("question_type", "unknown"),
                "method": method,
                "rank": rank,
                "recall_at_5": float(any(doc_id in gold_docs for doc_id in retrieved[:5])),
                "recall_at_10": float(any(doc_id in gold_docs for doc_id in retrieved[:10])),
                "reciprocal_rank": reciprocal_rank(retrieved, gold_docs),
                "ndcg_at_10": ndcg_at_k(retrieved, gold_docs, 10),
                "context_precision_at_10": len(relevant) / max(len(results), 1),
                "context_recall_at_10": float(bool(relevant)),
                "latency_ms": latency_ms,
            }
        )
    return rows


def _summaries(rows: list[dict]) -> list[dict]:
    grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in rows:
        grouped[(row["method"], "overall")].append(row)
        grouped[(row["method"], row["question_type"])].append(row)
    summaries = []
    for (method, group), values in sorted(grouped.items()):
        recall_values = [float(row["recall_at_10"]) for row in values]
        ci_low, ci_high = _bootstrap_ci(recall_values)
        latencies = sorted(float(row["latency_ms"]) for row in values)
        summaries.append(
            {
                "method": method,
                "group": group,
                "questions": len(values),
                "recall_at_5": mean(float(row["recall_at_5"]) for row in values),
                "recall_at_10": mean(recall_values),
                "recall_at_10_ci_low": ci_low,
                "recall_at_10_ci_high": ci_high,
                "mrr": mean(float(row["reciprocal_rank"]) for row in values),
                "ndcg_at_10": mean(float(row["ndcg_at_10"]) for row in values),
                "context_precision_at_10": mean(
                    float(row["context_precision_at_10"]) for row in values
                ),
                "context_recall_at_10": mean(
                    float(row["context_recall_at_10"]) for row in values
                ),
                "p50_latency_ms": latencies[len(latencies) // 2],
                "p95_latency_ms": latencies[min(round(len(latencies) * 0.95), len(latencies) - 1)],
            }
        )
    return summaries


def _write_csv(path: Path, rows: list[dict]) -> None:
    ensure_parent(path)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]) if rows else [])
        if rows:
            writer.writeheader()
            writer.writerows(rows)


@app.command()
def run(
    questions_jsonl: Path,
    summary_csv: Path,
    details_csv: Path,
    config_path: Path,
    top_k: int = 10,
    candidate_k: int = 50,
    bm25_weight: float = 2.0,
    vector_weight: float = 1.0,
) -> None:
    """Evaluate BM25, vector, RRF, and weighted Hybrid with parent/page awareness."""
    config = load_config(config_path)
    questions = [
        row for row in read_jsonl(questions_jsonl) if row.get("review_status") != "rejected"
    ]
    bm25 = OpenSearchBM25Retriever(
        config.opensearch.url,
        config.opensearch.index,
        config.opensearch.username,
        config.opensearch.password,
    )
    embedder = SentenceTransformerEmbedder(
        config.embedding.model_name,
        config.embedding.device,
        config.embedding.document_prefix,
        config.embedding.query_prefix,
    )
    vector = QdrantVectorRetriever(config.qdrant.url, config.qdrant.collection, embedder)
    methods = {
        "bm25": bm25,
        "vector": vector,
        "hybrid_rrf": HybridAdapter(
            HybridRetriever(bm25, vector, rrf_k=config.retrieval.rrf_k), candidate_k
        ),
        "hybrid_weighted": WeightedHybridEvalRetriever(
            bm25,
            vector,
            bm25_weight,
            vector_weight,
            config.retrieval.rrf_k,
            candidate_k,
        ),
    }
    details = []
    for method, retriever in methods.items():
        details.extend(evaluate_method(method, retriever, questions, top_k))
    summaries = _summaries(details)
    _write_csv(details_csv, details)
    _write_csv(summary_csv, summaries)
    typer.echo(f"Wrote {len(summaries)} retrieval summary rows to {summary_csv}")


def main() -> None:
    app()
