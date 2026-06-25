from __future__ import annotations

import csv
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median

import typer

from koreanops_rag.config import load_config
from koreanops_rag.io import read_jsonl
from koreanops_rag.retrieval.bm25_opensearch import OpenSearchBM25Retriever
from koreanops_rag.retrieval.fusion import reciprocal_rank_fusion
from koreanops_rag.retrieval.vector_qdrant import QdrantVectorRetriever, SentenceTransformerEmbedder

app = typer.Typer(add_completion=False)


def _rank(doc_ids: list[str], gold_doc_id: str) -> int | None:
    try:
        return doc_ids.index(gold_doc_id) + 1
    except ValueError:
        return None


def _bucket_length(length: int) -> str:
    if length < 250:
        return "<250"
    if length < 500:
        return "250-499"
    if length < 1000:
        return "500-999"
    if length < 2000:
        return "1000-1999"
    return ">=2000"


def _recall_at(ranks: list[int | None], k: int) -> float:
    if not ranks:
        return 0.0
    return sum(rank is not None and rank <= k for rank in ranks) / len(ranks)


def _mrr(ranks: list[int | None]) -> float:
    if not ranks:
        return 0.0
    return sum(1 / rank if rank else 0.0 for rank in ranks) / len(ranks)


def _summarize(grouped: dict[str, list[dict]]) -> list[dict]:
    rows = []
    for group, items in sorted(grouped.items()):
        bm25_ranks = [item["bm25_rank"] for item in items]
        vector_ranks = [item["vector_rank"] for item in items]
        hybrid_ranks = [item["hybrid_rank"] for item in items]
        lengths = [item["gold_content_len"] for item in items]
        rows.append(
            {
                "group": group,
                "questions": len(items),
                "median_gold_content_len": median(lengths) if lengths else 0,
                "bm25_recall@10": _recall_at(bm25_ranks, 10),
                "bm25_mrr": _mrr(bm25_ranks),
                "vector_recall@10": _recall_at(vector_ranks, 10),
                "vector_mrr": _mrr(vector_ranks),
                "hybrid_recall@10": _recall_at(hybrid_ranks, 10),
                "hybrid_mrr": _mrr(hybrid_ranks),
                "vector_miss@10": sum(rank is None or rank > 10 for rank in vector_ranks),
            }
        )
    return rows


class QueryPrefixVectorRetriever:
    def __init__(self, base: QdrantVectorRetriever, prefix: str):
        self.base = base
        self.prefix = prefix

    def search(self, query: str, top_k: int = 10, filters=None):
        return self.base.search(f"{self.prefix}{query}", top_k=top_k, filters=filters)


@app.command()
def run(
    documents_jsonl: Path,
    questions_jsonl: Path,
    output_dir: Path,
    config_path: Path = Path("configs/default.yaml"),
    top_k: int = 50,
) -> None:
    """Diagnose vector retrieval quality by model usage, document shape, and data groups."""
    config = load_config(config_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    docs = {doc["doc_id"]: doc for doc in read_jsonl(documents_jsonl)}
    questions = list(read_jsonl(questions_jsonl))

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
    prefixed_vector = QueryPrefixVectorRetriever(vector, "query: ")

    detail_rows = []
    for idx, question in enumerate(questions, start=1):
        gold_doc_id = question["gold_doc_ids"][0]
        gold = docs[gold_doc_id]
        bm25_results = bm25.search(question["question"], top_k=top_k)
        vector_results = vector.search(question["question"], top_k=top_k)
        prefixed_results = prefixed_vector.search(question["question"], top_k=top_k)
        hybrid_results = reciprocal_rank_fusion(
            {"bm25": bm25_results, "vector": vector_results}, top_k=top_k, rrf_k=60
        )
        row = {
            "question_id": idx,
            "source_type": question.get("source_type", gold["source_type"]),
            "gold_doc_id": gold_doc_id,
            "gold_content_len": len(gold["content"]),
            "gold_len_bucket": _bucket_length(len(gold["content"])),
            "bm25_rank": _rank([r.doc_id for r in bm25_results], gold_doc_id),
            "vector_rank": _rank([r.doc_id for r in vector_results], gold_doc_id),
            "vector_query_prefix_rank": _rank([r.doc_id for r in prefixed_results], gold_doc_id),
            "hybrid_rank": _rank([r.doc_id for r in hybrid_results], gold_doc_id),
            "question_len": len(question["question"]),
            "gold_title": gold.get("title", ""),
        }
        detail_rows.append(row)
        if idx % 50 == 0:
            typer.echo(f"Analyzed {idx}/{len(questions)} questions")

    detail_path = output_dir / "vector_quality_details.csv"
    with detail_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(detail_rows[0]))
        writer.writeheader()
        writer.writerows(detail_rows)

    by_source = defaultdict(list)
    by_length = defaultdict(list)
    for row in detail_rows:
        by_source[row["source_type"]].append(row)
        by_length[row["gold_len_bucket"]].append(row)

    model_rows = []
    for name in ["vector_rank", "vector_query_prefix_rank"]:
        ranks = [row[name] for row in detail_rows]
        model_rows.append(
            {
                "variant": name,
                "recall@5": _recall_at(ranks, 5),
                "recall@10": _recall_at(ranks, 10),
                "mrr": _mrr(ranks),
                "miss@10": sum(rank is None or rank > 10 for rank in ranks),
            }
        )

    source_rows = _summarize(by_source)
    length_rows = _summarize(by_length)
    with (output_dir / "vector_quality_summary.json").open("w", encoding="utf-8") as f:
        json.dump(
            {
                "documents": len(docs),
                "questions": len(questions),
                "model_variants": model_rows,
                "by_source_type": source_rows,
                "by_gold_length_bucket": length_rows,
                "vector_miss_examples": [
                    row
                    for row in detail_rows
                    if row["vector_rank"] is None or row["vector_rank"] > 10
                ][:20],
                "source_counts": Counter(row["source_type"] for row in detail_rows),
            },
            f,
            ensure_ascii=False,
            indent=2,
            default=lambda value: None if isinstance(value, float) and math.isnan(value) else value,
        )
    typer.echo(f"Wrote diagnostics to {output_dir}")


def main() -> None:
    app()
