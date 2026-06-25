from __future__ import annotations

import csv
import json
import re
from collections import defaultdict
from pathlib import Path

import typer

from koreanops_rag.config import load_config
from koreanops_rag.io import read_jsonl
from koreanops_rag.retrieval.bm25_opensearch import OpenSearchBM25Retriever
from koreanops_rag.retrieval.hybrid import HybridRetriever
from koreanops_rag.retrieval.vector_qdrant import QdrantVectorRetriever, SentenceTransformerEmbedder

app = typer.Typer(add_completion=False)

PRIORITY_RE = re.compile(r"\b(low|medium|high|critical)\b", re.IGNORECASE)
TICKET_TYPE_RE = re.compile(r"\b(incident|request|problem|question)\b", re.IGNORECASE)
ENTITY_RE = re.compile(
    r"\b([A-Z][A-Za-z0-9+.-]{2,}(?:\s+[A-Z][A-Za-z0-9+.-]{2,}){0,3}|[A-Za-z]+(?:\d{2,4}))\b"
)
RESOLUTION_RE = re.compile(r"\b(resolution|resolve|resolved|fix|repair|assist|support)\b", re.IGNORECASE)
SYMPTOM_RE = re.compile(
    r"\b(issue|problem|error|failed|failure|crash|halted|timeout|loss|leakage|inaccuracies)\b",
    re.IGNORECASE,
)


def rank(doc_ids: list[str], gold_doc_id: str) -> int | None:
    try:
        return doc_ids.index(gold_doc_id) + 1
    except ValueError:
        return None


def recall_at(ranks: list[int | None], k: int) -> float:
    if not ranks:
        return 0.0
    return sum(item is not None and item <= k for item in ranks) / len(ranks)


def mrr(ranks: list[int | None]) -> float:
    if not ranks:
        return 0.0
    return sum(1 / item if item else 0.0 for item in ranks) / len(ranks)


def classify_question(question: dict) -> dict[str, bool | str]:
    text = str(question["question"])
    source_type = str(question.get("source_type", "unknown"))
    flags = {
        "source_type": source_type,
        "has_metadata_terms": bool(PRIORITY_RE.search(text) or TICKET_TYPE_RE.search(text)),
        "has_resolution_terms": bool("Resolution:" in text or RESOLUTION_RE.search(text)),
        "has_symptom_terms": bool("Description:" in text or SYMPTOM_RE.search(text)),
        "has_entity_terms": bool(ENTITY_RE.search(text)),
    }
    if source_type == "log":
        primary = "log_pattern_severity"
    elif flags["has_resolution_terms"]:
        primary = "resolution_action"
    elif flags["has_symptom_terms"]:
        primary = "issue_symptom"
    elif flags["has_metadata_terms"]:
        primary = "metadata_like"
    elif flags["has_entity_terms"]:
        primary = "exact_entity_product"
    else:
        primary = "general_semantic"
    flags["primary_type"] = primary
    return flags


def summarize(rows: list[dict], group_key: str) -> list[dict]:
    grouped = defaultdict(list)
    for row in rows:
        grouped[str(row[group_key])].append(row)

    summary = []
    for group, items in sorted(grouped.items()):
        bm25_ranks = [item["bm25_rank"] for item in items]
        vector_ranks = [item["vector_rank"] for item in items]
        hybrid_ranks = [item["hybrid_rank"] for item in items]
        summary.append(
            {
                "group_key": group_key,
                "group": group,
                "questions": len(items),
                "bm25_recall@10": recall_at(bm25_ranks, 10),
                "bm25_mrr": mrr(bm25_ranks),
                "vector_recall@10": recall_at(vector_ranks, 10),
                "vector_mrr": mrr(vector_ranks),
                "hybrid_recall@10": recall_at(hybrid_ranks, 10),
                "hybrid_mrr": mrr(hybrid_ranks),
                "vector_miss@10": sum(item is None or item > 10 for item in vector_ranks),
            }
        )
    return summary


@app.command()
def run(
    questions_jsonl: Path,
    output_dir: Path,
    config_path: Path = Path("configs/default.yaml"),
    top_k: int = 50,
    candidate_k: int = 50,
) -> None:
    """Evaluate retrieval quality by heuristic query type buckets."""
    config = load_config(config_path)
    output_dir.mkdir(parents=True, exist_ok=True)

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

    detail_rows = []
    for idx, question in enumerate(read_jsonl(questions_jsonl), start=1):
        gold_doc_id = question["gold_doc_ids"][0]
        flags = classify_question(question)
        bm25_results = bm25.search(question["question"], top_k=top_k)
        vector_results = vector.search(question["question"], top_k=top_k)
        hybrid_results = hybrid.search(question["question"], top_k=10, candidate_k=candidate_k)
        detail_rows.append(
            {
                "question_id": idx,
                "gold_doc_id": gold_doc_id,
                **flags,
                "bm25_rank": rank([result.doc_id for result in bm25_results], gold_doc_id),
                "vector_rank": rank([result.doc_id for result in vector_results], gold_doc_id),
                "hybrid_rank": rank([result.doc_id for result in hybrid_results], gold_doc_id),
                "question": question["question"],
            }
        )
        if idx % 50 == 0:
            typer.echo(f"Analyzed {idx} questions")

    detail_path = output_dir / "query_type_details.csv"
    with detail_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(detail_rows[0]))
        writer.writeheader()
        writer.writerows(detail_rows)

    summary = []
    for group_key in [
        "primary_type",
        "source_type",
        "has_metadata_terms",
        "has_resolution_terms",
        "has_symptom_terms",
        "has_entity_terms",
    ]:
        summary.extend(summarize(detail_rows, group_key))

    with (output_dir / "query_type_summary.json").open("w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    typer.echo(f"Wrote query type diagnostics to {output_dir}")


def main() -> None:
    app()
