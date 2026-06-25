from __future__ import annotations

import json
import random
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import typer

from koreanops_rag.io import read_jsonl, write_jsonl
from koreanops_rag.rag.llm_provider import OllamaProvider
from koreanops_rag.schemas import GoldenQuestion

app = typer.Typer(add_completion=False)
WORD_RE = re.compile(r"[0-9A-Za-z가-힣]+")
QUESTION_TYPES = ["fact", "procedure", "comparison", "numeric", "condition", "summary"]


def lexical_overlap(question: str, evidence: str) -> float:
    question_terms = set(WORD_RE.findall(question.lower()))
    evidence_terms = set(WORD_RE.findall(evidence.lower()))
    return len(question_terms & evidence_terms) / max(len(question_terms), 1)


def _ollama_candidate(
    provider: OllamaProvider,
    title: str,
    evidence: str,
    question_type: str,
) -> tuple[str, str]:
    prompt = f"""다음 문서 근거만 사용하여 검색 평가용 한국어 질문 1개와 간결한 정답을 만드세요.
질문 유형: {question_type}
문서 제목이나 근거 문장을 그대로 복사하지 말고 자연스럽게 바꾸세요.
출력은 JSON 객체 하나만 사용하세요: {{"question":"...", "answer":"..."}}

문서 제목: {title}
근거:
{evidence}
"""
    response = provider.generate(prompt)
    match = re.search(r"\{.*\}", response, re.DOTALL)
    if not match:
        raise ValueError("Ollama response did not contain a JSON object")
    payload = json.loads(match.group(0))
    return str(payload["question"]).strip(), str(payload["answer"]).strip()


def _fallback_candidate(title: str, evidence: str, question_type: str) -> tuple[str, str]:
    prompts = {
        "fact": "이 문서에서 설명하는 주요 사실은 무엇인가요?",
        "procedure": "이 문서가 제시하는 처리 절차나 방법은 무엇인가요?",
        "comparison": "이 문서에서 비교하거나 구분하는 핵심 내용은 무엇인가요?",
        "numeric": "이 문서에 제시된 주요 수치와 그 의미는 무엇인가요?",
        "condition": "이 문서에서 제시하는 적용 조건이나 요건은 무엇인가요?",
        "summary": "이 문서의 핵심 내용을 요약하면 무엇인가요?",
    }
    question = prompts[question_type]
    answer = evidence[:500].strip()
    return question, answer


def _evidence_segment(page_content: str) -> str:
    paragraphs = [
        value.strip()
        for value in re.split(r"\n{1,}|\[\#{1,4}\]|\[@\]|\[!\]", page_content)
        if len(value.strip()) >= 80
    ]
    candidates = [value for value in paragraphs if len(value) <= 900]
    if candidates:
        return max(candidates, key=len)
    if paragraphs:
        return max(paragraphs, key=len)[:900].strip()
    return page_content[:900].strip()


def _select_documents(
    documents: list[dict[str, Any]],
    sample_size: int,
    seed: int,
) -> list[dict[str, Any]]:
    random.seed(seed)
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for document in documents:
        if document.get("metadata", {}).get("split") == "validation":
            groups[document.get("metadata", {}).get("document_type", "unknown")].append(document)
    selected = []
    while len(selected) < sample_size and any(groups.values()):
        for document_type in sorted(groups):
            if not groups[document_type] or len(selected) >= sample_size:
                continue
            index = random.randrange(len(groups[document_type]))
            selected.append(groups[document_type].pop(index))
    return selected


@app.command()
def run(
    oracle_documents_jsonl: Path,
    oracle_pages_jsonl: Path,
    output_jsonl: Path,
    sample_size: int = 300,
    seed: int = 42,
    use_ollama: bool = False,
    ollama_base_url: str = "http://localhost:11434",
    ollama_model: str = "llama3.1:8b-instruct-q4_K_M",
) -> None:
    """Generate review-pending Golden Set candidates from validation Oracle evidence."""
    documents = list(read_jsonl(oracle_documents_jsonl))
    pages: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for page in read_jsonl(oracle_pages_jsonl):
        if str(page.get("content", "")).strip():
            pages[page["doc_id"]].append(page)
    selected = _select_documents(documents, sample_size, seed)
    provider = (
        OllamaProvider(ollama_base_url, ollama_model, timeout=300) if use_ollama else None
    )
    titles_by_group: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for document in documents:
        metadata = document.get("metadata", {})
        key = (metadata.get("document_type", ""), metadata.get("publisher", ""))
        titles_by_group[key].append(document)

    rows = []
    type_counts: Counter[str] = Counter()
    for index, document in enumerate(selected):
        doc_pages = sorted(pages.get(document["doc_id"], []), key=lambda row: row["page_num"])
        if not doc_pages:
            continue
        page = max(doc_pages, key=lambda row: len(str(row.get("content", ""))))
        evidence = _evidence_segment(str(page["content"]).strip())
        question_type = QUESTION_TYPES[index % len(QUESTION_TYPES)]
        if provider:
            try:
                question, answer = _ollama_candidate(
                    provider, document.get("title", ""), evidence, question_type
                )
            except Exception as exc:
                typer.echo(
                    f"Question {index + 1}: Ollama generation failed, using fallback: {exc}",
                    err=True,
                )
                question, answer = _fallback_candidate(
                    document.get("title", ""), evidence, question_type
                )
        else:
            question, answer = _fallback_candidate(
                document.get("title", ""), evidence, question_type
            )
        metadata = document.get("metadata", {})
        group = titles_by_group[
            (metadata.get("document_type", ""), metadata.get("publisher", ""))
        ]
        negatives = [
            candidate["doc_id"]
            for candidate in group
            if candidate["doc_id"] != document["doc_id"]
        ][:3]
        row = GoldenQuestion(
            question_id=f"office_q_{index + 1:04d}",
            question=question,
            reference_answer=answer,
            gold_doc_ids=[document["doc_id"]],
            gold_pages=[int(page["page_num"])],
            evidence_text=evidence,
            question_type=question_type,
            lexical_overlap=lexical_overlap(question, evidence),
            hard_negative_doc_ids=negatives,
        )
        rows.append(row)
        type_counts[question_type] += 1
    count = write_jsonl(output_jsonl, rows)
    typer.echo(f"Wrote {count} review-pending Golden Set candidates: {dict(type_counts)}")


def main() -> None:
    app()
