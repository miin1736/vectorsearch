from __future__ import annotations

import csv
import random
import time
from pathlib import Path

import typer

from koreanops_rag.config import load_config
from koreanops_rag.io import read_jsonl
from koreanops_rag.rag.answer_generator import AnswerGenerator
from koreanops_rag.rag.llm_provider import OllamaProvider
from koreanops_rag.retrieval.bm25_opensearch import OpenSearchBM25Retriever
from koreanops_rag.retrieval.hybrid import HybridRetriever
from koreanops_rag.retrieval.vector_qdrant import QdrantVectorRetriever, SentenceTransformerEmbedder

app = typer.Typer(add_completion=False)


@app.command()
def run(
    questions_jsonl: Path,
    output_csv: Path,
    config_path: Path = Path("configs/default.yaml"),
    sample_size: int = 30,
    top_k: int = 5,
    candidate_k: int = 50,
    seed: int = 42,
) -> None:
    """Run a small local-LLM RAG quality proxy evaluation over hybrid retrieval."""
    config = load_config(config_path)
    rows = list(read_jsonl(questions_jsonl))
    random.seed(seed)
    sampled = random.sample(rows, min(sample_size, len(rows)))

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
    retriever = HybridRetriever(bm25, vector, rrf_k=config.retrieval.rrf_k)
    generator = AnswerGenerator(
        OllamaProvider(config.rag.ollama_base_url, config.rag.ollama_model, timeout=300)
    )

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "question_id",
                "source_type",
                "gold_doc_id",
                "gold_in_context",
                "answer_nonempty",
                "cites_any_context_doc",
                "cites_gold_doc",
                "latency_ms",
                "answer_chars",
            ],
        )
        writer.writeheader()
        for idx, row in enumerate(sampled, start=1):
            started = time.perf_counter()
            contexts = retriever.search(row["question"], top_k=top_k, candidate_k=candidate_k)
            answer = generator.answer(row["question"], contexts)
            latency_ms = (time.perf_counter() - started) * 1000
            context_ids = [context.doc_id for context in contexts]
            gold_ids = row.get("gold_doc_ids", [])
            gold_doc_id = gold_ids[0] if gold_ids else ""
            writer.writerow(
                {
                    "question_id": idx,
                    "source_type": row.get("source_type", ""),
                    "gold_doc_id": gold_doc_id,
                    "gold_in_context": gold_doc_id in context_ids,
                    "answer_nonempty": bool(answer.strip()),
                    "cites_any_context_doc": any(doc_id in answer for doc_id in context_ids),
                    "cites_gold_doc": bool(gold_doc_id and gold_doc_id in answer),
                    "latency_ms": latency_ms,
                    "answer_chars": len(answer),
                }
            )
            typer.echo(f"Evaluated RAG sample {idx}/{len(sampled)}")


def main() -> None:
    app()
