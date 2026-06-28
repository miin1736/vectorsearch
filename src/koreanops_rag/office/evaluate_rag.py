from __future__ import annotations

import csv
import re
import time
from pathlib import Path
from statistics import mean
from typing import Literal

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
RagMethod = Literal["vector", "hybrid_rrf"]
UNSUPPORTED_MARKERS = (
    "확인할 수 없습니다",
    "확인할 수는 없습니다",
    "근거가 부족",
    "?뺤씤?????놁뒿?덈떎",
)


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


def _parent_id(result) -> str:
    return str(result.metadata.get("parent_doc_id") or result.doc_id)


def _page_overlap(result, gold_pages: set[int]) -> bool:
    if not gold_pages:
        return True
    start = int(result.metadata.get("page_start", 0))
    end = int(result.metadata.get("page_end", start))
    return bool(set(range(start, end + 1)) & gold_pages)


def gold_in_context(contexts, question: dict) -> float:
    gold_ids = set(question.get("gold_doc_ids", []))
    gold_pages = set(int(page) for page in question.get("gold_pages", []))
    return float(
        any(_parent_id(context) in gold_ids and _page_overlap(context, gold_pages) for context in contexts)
    )


def cites_context(answer: str, contexts) -> float:
    return float(
        any(
            context.doc_id in answer
            or str(context.metadata.get("parent_doc_id") or context.doc_id) in answer
            for context in contexts
        )
    )


def _read_existing_question_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    with path.open("r", encoding="utf-8", newline="") as file:
        return {row["question_id"] for row in csv.DictReader(file)}


def _summarize_csv(path: Path) -> dict[str, float]:
    if not path.exists():
        rows = []
    else:
        with path.open("r", encoding="utf-8", newline="") as file:
            rows = list(csv.DictReader(file))
    if not rows:
        return {
            "questions": 0.0,
            "token_f1": 0.0,
            "gold_in_context": 0.0,
            "cites_context": 0.0,
            "unsupported_answer": 0.0,
            "p50_latency_ms": 0.0,
            "p95_latency_ms": 0.0,
        }
    latencies = sorted(float(row["latency_ms"]) for row in rows)
    return {
        "questions": float(len(rows)),
        "token_f1": mean(float(row["token_f1"]) for row in rows),
        "gold_in_context": mean(float(row["gold_in_context"]) for row in rows),
        "cites_context": mean(float(row["cites_context"]) for row in rows),
        "unsupported_answer": mean(float(row["unsupported_answer"]) for row in rows),
        "p50_latency_ms": latencies[len(latencies) // 2],
        "p95_latency_ms": latencies[min(round(len(latencies) * 0.95), len(latencies) - 1)],
    }


def _write_summary(path: Path, summary: dict[str, float]) -> None:
    ensure_parent(path)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(summary))
        writer.writeheader()
        writer.writerow(summary)


@app.command()
def run(
    questions_jsonl: Path,
    output_csv: Path,
    config_path: Path,
    summary_csv: Path | None = None,
    sample_size: int = 200,
    top_k: int = 5,
    candidate_k: int = 50,
    method: RagMethod = "vector",
    resume: bool = False,
    llm_timeout: int = 600,
) -> None:
    """Run grounded local-Ollama RAG evaluation over approved/revised questions."""
    config = load_config(config_path)
    questions = [
        row
        for row in read_jsonl(questions_jsonl)
        if row.get("review_status") in {"approved", "revised"}
    ][:sample_size]
    embedder = SentenceTransformerEmbedder(
        config.embedding.model_name,
        config.embedding.device,
        config.embedding.document_prefix,
        config.embedding.query_prefix,
    )
    vector = QdrantVectorRetriever(config.qdrant.url, config.qdrant.collection, embedder)
    if method == "vector":
        retriever = vector
    else:
        bm25 = OpenSearchBM25Retriever(
            config.opensearch.url,
            config.opensearch.index,
            config.opensearch.username,
            config.opensearch.password,
        )
        retriever = HybridRetriever(bm25, vector, rrf_k=config.retrieval.rrf_k)
    generator = AnswerGenerator(
        OllamaProvider(config.rag.ollama_base_url, config.rag.ollama_model, timeout=llm_timeout)
    )

    ensure_parent(output_csv)
    existing_ids = _read_existing_question_ids(output_csv) if resume else set()
    mode = "a" if resume and output_csv.exists() else "w"
    fieldnames = [
        "question_id",
        "method",
        "answer",
        "token_f1",
        "gold_in_context",
        "cites_context",
        "unsupported_answer",
        "latency_ms",
    ]
    with output_csv.open(mode, encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        if mode == "w":
            writer.writeheader()
        completed = len(existing_ids)
        for index, question in enumerate(questions, start=1):
            if question["question_id"] in existing_ids:
                continue
            started = time.perf_counter()
            if method == "vector":
                contexts = retriever.search(question["question"], top_k=top_k)
            else:
                contexts = retriever.search(
                    question["question"], top_k=top_k, candidate_k=candidate_k
                )
            generation_error = ""
            try:
                answer = generator.answer(question["question"], contexts)
            except Exception as exc:
                generation_error = f"__GENERATION_ERROR__: {type(exc).__name__}: {exc}"
                answer = generation_error
            writer.writerow(
                {
                    "question_id": question["question_id"],
                    "method": method,
                    "answer": answer,
                    "token_f1": 0.0
                    if generation_error
                    else token_f1(answer, question.get("reference_answer", "")),
                    "gold_in_context": gold_in_context(contexts, question),
                    "cites_context": cites_context(answer, contexts),
                    "unsupported_answer": float(
                        bool(generation_error)
                        or any(marker in answer for marker in UNSUPPORTED_MARKERS)
                    ),
                    "latency_ms": (time.perf_counter() - started) * 1000,
                }
            )
            file.flush()
            completed += 1
            if completed % 10 == 0 or index == len(questions):
                typer.echo(f"Evaluated {completed}/{len(questions)} RAG questions...")

    summary = _summarize_csv(output_csv)
    if summary_csv:
        _write_summary(summary_csv, summary)
    typer.echo(f"Wrote {int(summary['questions'])} RAG evaluation rows to {output_csv}")


def main() -> None:
    app()
