from __future__ import annotations

import csv
import re
import time
from pathlib import Path

import typer

from koreanops_rag.config import load_config
from koreanops_rag.io import ensure_parent, read_jsonl
from koreanops_rag.rag.answer_generator import AnswerGenerator
from koreanops_rag.rag.llm_provider import OllamaProvider
from koreanops_rag.retrieval.bm25_opensearch import OpenSearchBM25Retriever
from koreanops_rag.retrieval.hybrid import HybridRetriever
from koreanops_rag.retrieval.vector_qdrant import (
    QdrantVectorRetriever,
    SentenceTransformerEmbedder,
)

app = typer.Typer(add_completion=False)
TOKEN_RE = re.compile(r"[0-9A-Za-z가-힣]+")


def _metric_tokens(text: str) -> list[str]:
    output = []
    for token in TOKEN_RE.findall(text.lower()):
        if re.fullmatch(r"[가-힣]+", token) and len(token) >= 2:
            output.extend(token[index : index + 2] for index in range(len(token) - 1))
        else:
            output.append(token)
    return output


def token_f1(answer: str, reference: str) -> float:
    answer_tokens = _metric_tokens(answer)
    reference_tokens = _metric_tokens(reference)
    if not answer_tokens or not reference_tokens:
        return 0.0
    common = 0
    remaining = list(reference_tokens)
    for token in answer_tokens:
        if token in remaining:
            common += 1
            remaining.remove(token)
    precision = common / len(answer_tokens)
    recall = common / len(reference_tokens)
    return 2 * precision * recall / max(precision + recall, 1e-12)


@app.command()
def run(
    questions_jsonl: Path,
    output_csv: Path,
    config_path: Path,
    sample_size: int = 200,
    top_k: int = 5,
    candidate_k: int = 50,
) -> None:
    """Run grounded local-Ollama RAG evaluation over approved/revised questions."""
    config = load_config(config_path)
    questions = [
        row
        for row in read_jsonl(questions_jsonl)
        if row.get("review_status") in {"approved", "revised"}
    ][:sample_size]
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
    retriever = HybridRetriever(bm25, vector, rrf_k=config.retrieval.rrf_k)
    generator = AnswerGenerator(
        OllamaProvider(config.rag.ollama_base_url, config.rag.ollama_model, timeout=300)
    )
    rows = []
    for question in questions:
        started = time.perf_counter()
        contexts = retriever.search(
            question["question"], top_k=top_k, candidate_k=candidate_k
        )
        answer = generator.answer(question["question"], contexts)
        context_ids = [
            str(context.metadata.get("parent_doc_id") or context.doc_id)
            for context in contexts
        ]
        gold_ids = set(question.get("gold_doc_ids", []))
        unsupported = "확인할 수 없습니다" in answer
        rows.append(
            {
                "question_id": question["question_id"],
                "answer": answer,
                "token_f1": token_f1(answer, question.get("reference_answer", "")),
                "gold_in_context": float(bool(set(context_ids) & gold_ids)),
                "cites_context": float(any(context.doc_id in answer for context in contexts)),
                "unsupported_answer": float(unsupported),
                "latency_ms": (time.perf_counter() - started) * 1000,
            }
        )
    ensure_parent(output_csv)
    with output_csv.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]) if rows else [])
        if rows:
            writer.writeheader()
            writer.writerows(rows)
    typer.echo(f"Wrote {len(rows)} RAG evaluation rows to {output_csv}")


def main() -> None:
    app()
