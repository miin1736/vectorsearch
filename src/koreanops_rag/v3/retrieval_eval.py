from __future__ import annotations

import csv
import random
import time
from collections import Counter, defaultdict
from os import getenv
from pathlib import Path
from statistics import mean
from typing import Any, Iterable

import typer

from koreanops_rag.config import load_config
from koreanops_rag.evaluation.metrics import ndcg_at_k, reciprocal_rank
from koreanops_rag.evaluation.run_weighted_hybrid_eval import WeightedHybridEvalRetriever
from koreanops_rag.io import ensure_parent, read_jsonl, write_jsonl
from koreanops_rag.retrieval.bm25_opensearch import OpenSearchBM25Retriever
from koreanops_rag.retrieval.hybrid import HybridRetriever
from koreanops_rag.retrieval.vector_qdrant import QdrantVectorRetriever, SentenceTransformerEmbedder

app = typer.Typer(add_completion=False)

DEFAULT_CASE_CONFIGS = [
    Path("experiments/ko_dense_technical_v3/configs/baseline_fixed_512.yaml"),
    Path("experiments/ko_dense_technical_v3/configs/baseline_page_subchunk.yaml"),
    Path("experiments/ko_dense_technical_v3/configs/baseline_section.yaml"),
    Path("experiments/ko_dense_technical_v3/configs/tokenizer_aware_fixed_512.yaml"),
]

SECTION_QUESTION_LABELS = {
    "abstract": "abstract",
    "introduction": "introduction",
    "related_work": "related work",
    "method": "method",
    "experiment": "experiment",
    "result": "result",
    "conclusion": "conclusion",
    "body": "body",
}
STOPWORDS = {
    "this",
    "that",
    "with",
    "from",
    "were",
    "there",
    "their",
    "which",
    "paper",
    "study",
    "analysis",
    "using",
    "based",
    "abstract",
}


def default_data_root() -> Path:
    return Path(getenv("DATA_ROOT", r"C:\vectorsearch-data")) / "ko-dense-technical"


def default_smoke_processed_path(name: str) -> Path:
    return default_data_root() / "processed" / "smoke_100" / name


def default_smoke_eval_path(name: str) -> Path:
    return default_data_root() / "eval" / "smoke_100" / name


def normalize_space(text: str) -> str:
    return " ".join(text.split())


def parent_id(result: Any) -> str:
    return str(result.metadata.get("parent_doc_id") or result.doc_id)


def dedupe_parent_results(results: Iterable[Any]) -> list[Any]:
    seen: set[str] = set()
    deduped = []
    for result in results:
        doc_id = parent_id(result)
        if doc_id in seen:
            continue
        seen.add(doc_id)
        deduped.append(result)
    return deduped


def lexical_overlap(question: str, evidence: str) -> float:
    question_terms = {term for term in question.split() if len(term) > 1}
    evidence_terms = {term for term in evidence.split() if len(term) > 1}
    if not question_terms or not evidence_terms:
        return 0.0
    return len(question_terms & evidence_terms) / len(question_terms)


def topic_phrase_from_evidence(evidence: str, fallback: str) -> str:
    words = []
    for raw in evidence.replace("(", " ").replace(")", " ").replace(",", " ").split():
        word = "".join(char for char in raw if char.isalnum() or char in {"-", "_"})
        if len(word) < 4 or word.lower() in STOPWORDS:
            continue
        if word.lower() not in {item.lower() for item in words}:
            words.append(word)
        if len(words) >= 6:
            break
    if words:
        return " ".join(words)
    return normalize_space(fallback)[:80] or "?대떦 ?쇰Ц"


def question_for_section(
    doc: dict[str, Any],
    section: dict[str, Any],
    evidence: str,
) -> tuple[str, str]:
    section_type = str(section.get("section_type") or "body")
    label = SECTION_QUESTION_LABELS.get(section_type, "蹂몃Ц")
    fallback = str(doc.get("title") or doc.get("metadata", {}).get("paper_topic") or "")
    topic = topic_phrase_from_evidence(evidence, fallback)
    if section_type == "method":
        return f"{topic}? 愿?⑦븯?????쇰Ц?먯꽌 ?ъ슜??二쇱슂 諛⑸쾿濡좎? 臾댁뾿?멸???", "method"
    if section_type in {"experiment", "result"}:
        return f"{topic}? 愿?⑦븯?????쇰Ц???ㅽ뿕 ?먮뒗 寃곌낵?먯꽌 ?듭떖 ?댁슜? 臾댁뾿?멸???", "result"
    if section_type == "conclusion":
        return f"{topic}? 愿?⑦븯?????쇰Ц??寃곕줎? 臾댁뾿?멸???", "conclusion"
    if section_type == "introduction":
        return f"{topic}? 愿?⑦븯?????쇰Ц???ㅻ（???곌뎄 紐⑹쟻?대굹 諛곌꼍? 臾댁뾿?멸???", "purpose"
    if section_type == "abstract":
        return f"{topic}? 愿?⑦븯?????쇰Ц??珥덈줉? ?대뼡 ?댁슜???붿빟?섎굹??", "summary"
    return f"{topic}? 愿?⑦븯?????쇰Ц??{label} 遺遺꾩뿉???ㅻ챸?섎뒗 ?듭떖 ?댁슜? 臾댁뾿?멸???", "section"


def build_hard_negatives(doc: dict[str, Any], docs: list[dict[str, Any]], limit: int = 3) -> list[str]:
    metadata = doc.get("metadata", {})
    field = metadata.get("research_field")
    topic = set(str(metadata.get("paper_topic", "")).split())
    candidates: list[tuple[int, str]] = []
    for other in docs:
        if other.get("doc_id") == doc.get("doc_id"):
            continue
        other_metadata = other.get("metadata", {})
        score = 0
        if field and other_metadata.get("research_field") == field:
            score += 3
        score += len(topic & set(str(other_metadata.get("paper_topic", "")).split()))
        if score:
            candidates.append((score, str(other["doc_id"])))
    return [doc_id for _, doc_id in sorted(candidates, reverse=True)[:limit]]


def build_golden_questions_legacy(
    documents_jsonl: Path,
    sections_jsonl: Path,
    output_jsonl: Path,
    *,
    limit: int = 50,
    seed: int = 42,
    min_evidence_chars: int = 240,
) -> list[dict[str, Any]]:
    docs = list(read_jsonl(documents_jsonl))
    docs_by_id = {str(doc["doc_id"]): doc for doc in docs}
    sections_by_doc: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for section in read_jsonl(sections_jsonl):
        text = normalize_space(str(section.get("text") or ""))
        if len(text) >= min_evidence_chars:
            sections_by_doc[str(section["doc_id"])].append(section)

    rng = random.Random(seed)
    doc_ids = sorted(sections_by_doc)
    rng.shuffle(doc_ids)
    rows: list[dict[str, Any]] = []
    preferred = ["abstract", "introduction", "method", "experiment", "result", "conclusion", "body"]
    for doc_id in doc_ids:
        doc = docs_by_id.get(doc_id)
        if doc is None:
            continue
        sections = sorted(
            sections_by_doc[doc_id],
            key=lambda row: (
                preferred.index(str(row.get("section_type") or "body"))
                if str(row.get("section_type") or "body") in preferred
                else len(preferred),
                int(row.get("section_index") or 0),
            ),
        )
        if not sections:
            continue
        section = sections[0]
        evidence = normalize_space(str(section.get("text") or ""))[:800]
        question, question_type = question_for_section(doc, section, evidence)
        rows.append(
            {
                "question_id": f"v3_smoke_{len(rows) + 1:04d}",
                "question": question,
                "reference_answer": evidence[:360],
                "gold_doc_ids": [doc_id],
                "gold_pages": list(
                    range(
                        int(section.get("page_start") or 0),
                        int(section.get("page_end") or section.get("page_start") or 0) + 1,
                    )
                ),
                "gold_section": section.get("section_type", "body"),
                "evidence_text": evidence,
                "evidence_position": {
                    "section_id": section.get("section_id", ""),
                    "section_index": section.get("section_index", 0),
                    "page_start": section.get("page_start", 0),
                    "page_end": section.get("page_end", 0),
                },
                "question_type": question_type,
                "lexical_overlap": round(lexical_overlap(question, evidence), 6),
                "hard_negative_doc_ids": build_hard_negatives(doc, docs),
                "review_status": "approved_auto_smoke",
            }
        )
        if len(rows) >= limit:
            break
    write_jsonl(output_jsonl, rows)
    return rows


BALANCED_QUESTION_QUOTAS = {
    "summary": 0.20,
    "purpose": 0.20,
    "method": 0.20,
    "result": 0.20,
    "conclusion": 0.10,
    "section": 0.10,
}
QUESTION_TYPE_BY_SECTION = {
    "abstract": "summary",
    "introduction": "purpose",
    "method": "method",
    "experiment": "result",
    "result": "result",
    "conclusion": "conclusion",
    "body": "section",
}
NOISY_EVIDENCE_MARKERS = ("download by ip", "[provider:", "references")
BALANCED_STOPWORDS = STOPWORDS | {
    "purpose",
    "purposes",
    "method",
    "methods",
    "result",
    "results",
    "conclusion",
    "conclusions",
    "http",
    "https",
    "earticle",
    "download",
    "provider",
}


def _clean_evidence(text: str, max_chars: int = 800) -> str:
    lines = []
    for raw_line in str(text).splitlines():
        line = normalize_space(raw_line)
        lower = line.lower()
        if not line:
            continue
        if lower.startswith(("www.", "http://", "https://", "[provider:", "download by ip")):
            continue
        lines.append(line)
    return normalize_space(" ".join(lines))[:max_chars]


def _balanced_question_type(section_type: str) -> str:
    return QUESTION_TYPE_BY_SECTION.get(section_type, "section")


def _topic_hint(evidence: str, fallback: str) -> str:
    terms = []
    seen = set()
    for raw in evidence.replace("(", " ").replace(")", " ").replace(",", " ").split():
        term = "".join(char for char in raw if char.isalnum() or char in {"-", "_"})
        key = term.lower()
        if len(term) < 4 or key in BALANCED_STOPWORDS or key in seen:
            continue
        terms.append(term)
        seen.add(key)
        if len(terms) >= 3:
            break
    return " ".join(terms) if terms else normalize_space(fallback)[:80] or "the selected paper"


def _balanced_question(doc: dict[str, Any], section: dict[str, Any], evidence: str) -> tuple[str, str]:
    section_type = str(section.get("section_type") or "body")
    question_type = _balanced_question_type(section_type)
    fallback = str(doc.get("title") or doc.get("metadata", {}).get("paper_topic") or "")
    topic = _topic_hint(evidence, fallback)
    if question_type == "summary":
        return f"For {topic}, what problem, method, and finding does the paper summarize?", question_type
    if question_type == "purpose":
        return f"For {topic}, what research purpose or background does the paper describe?", question_type
    if question_type == "method":
        return f"For {topic}, what method, model, data, or procedure does the paper use?", question_type
    if question_type == "result":
        return f"For {topic}, what experiment, condition, measurement, or result is reported?", question_type
    if question_type == "conclusion":
        return f"For {topic}, what conclusion, implication, or limitation does the paper present?", question_type
    return f"For {topic}, what key point is explained in this section of the paper?", question_type


def _hard_negative_details(
    doc: dict[str, Any],
    docs: list[dict[str, Any]],
    limit: int = 10,
) -> list[dict[str, Any]]:
    metadata = doc.get("metadata", {})
    field = metadata.get("research_field")
    topic_terms = set(str(metadata.get("paper_topic", "")).split())
    candidates: list[tuple[int, str, list[str]]] = []
    for other in docs:
        if other.get("doc_id") == doc.get("doc_id"):
            continue
        other_metadata = other.get("metadata", {})
        score = 0
        reasons = []
        if field and other_metadata.get("research_field") == field:
            score += 3
            reasons.append("same_research_field")
        overlap = len(topic_terms & set(str(other_metadata.get("paper_topic", "")).split()))
        if overlap:
            score += overlap
            reasons.append("shared_topic_terms")
        if score:
            candidates.append((score, str(other["doc_id"]), reasons))
    return [
        {"doc_id": doc_id, "score": score, "reasons": reasons}
        for score, doc_id, reasons in sorted(candidates, reverse=True)[:limit]
    ]


def _difficulty(question: str, evidence: str, hard_negative_count: int) -> str:
    overlap = lexical_overlap(question, evidence)
    if overlap < 0.2 and hard_negative_count >= 5:
        return "adversarial"
    if overlap < 0.35 or hard_negative_count >= 8:
        return "hard"
    if overlap < 0.55:
        return "medium"
    return "easy"


def _review_flags(
    *,
    question: str,
    evidence: str,
    hard_negative_count: int,
    section_type: str,
) -> list[str]:
    flags = []
    overlap = lexical_overlap(question, evidence)
    lower_evidence = evidence.lower()
    if len(evidence) < 240:
        flags.append("too_short_evidence")
    if overlap >= 0.55:
        flags.append("high_lexical_overlap")
    if overlap < 0.15:
        flags.append("low_lexical_overlap")
    if hard_negative_count < 5:
        flags.append("few_hard_negatives")
    if section_type == "abstract":
        flags.append("abstract_based")
    if any(marker in lower_evidence for marker in NOISY_EVIDENCE_MARKERS):
        flags.append("source_noise")
    if not question.strip():
        flags.append("empty_question")
    return flags


def _target_counts(limit: int) -> dict[str, int]:
    counts = {
        question_type: int(limit * ratio)
        for question_type, ratio in BALANCED_QUESTION_QUOTAS.items()
    }
    while sum(counts.values()) < limit:
        for question_type in BALANCED_QUESTION_QUOTAS:
            counts[question_type] += 1
            if sum(counts.values()) == limit:
                break
    return counts


def _candidate_sort_key(section: dict[str, Any]) -> tuple[int, int]:
    priority = {
        "method": 0,
        "result": 1,
        "experiment": 2,
        "introduction": 3,
        "conclusion": 4,
        "body": 5,
        "abstract": 6,
    }
    section_type = str(section.get("section_type") or "body")
    return priority.get(section_type, 99), int(section.get("section_index") or 0)


def _build_balanced_row(
    *,
    index: int,
    id_prefix: str,
    qaset_version: str,
    doc: dict[str, Any],
    section: dict[str, Any],
    docs: list[dict[str, Any]],
) -> dict[str, Any]:
    section_type = str(section.get("section_type") or "body")
    evidence = _clean_evidence(str(section.get("text") or ""))
    question, question_type = _balanced_question(doc, section, evidence)
    hard_negatives = _hard_negative_details(doc, docs)
    hard_negative_doc_ids = [item["doc_id"] for item in hard_negatives]
    return {
        "question_id": f"{id_prefix}_{index:04d}",
        "qaset_version": qaset_version,
        "question": question,
        "reference_answer": evidence[:360],
        "gold_doc_ids": [str(doc["doc_id"])],
        "gold_pages": list(
            range(
                int(section.get("page_start") or 0),
                int(section.get("page_end") or section.get("page_start") or 0) + 1,
            )
        ),
        "gold_section": section_type,
        "evidence_text": evidence,
        "evidence_position": {
            "section_id": section.get("section_id", ""),
            "section_index": section.get("section_index", 0),
            "page_start": section.get("page_start", 0),
            "page_end": section.get("page_end", 0),
        },
        "question_type": question_type,
        "lexical_overlap": round(lexical_overlap(question, evidence), 6),
        "difficulty": _difficulty(question, evidence, len(hard_negative_doc_ids)),
        "hard_negative_doc_ids": hard_negative_doc_ids,
        "negative_reason": hard_negatives,
        "review_status": "candidate",
        "review_flags": _review_flags(
            question=question,
            evidence=evidence,
            hard_negative_count=len(hard_negative_doc_ids),
            section_type=section_type,
        ),
    }


def build_golden_questions(
    documents_jsonl: Path,
    sections_jsonl: Path,
    output_jsonl: Path,
    *,
    limit: int = 50,
    seed: int = 42,
    min_evidence_chars: int = 240,
    qaset_version: str = "v3_balanced_auto",
    id_prefix: str = "v3_balanced",
) -> list[dict[str, Any]]:
    """Build a difficulty-aware, section-balanced QASET candidate file."""
    docs = list(read_jsonl(documents_jsonl))
    docs_by_id = {str(doc["doc_id"]): doc for doc in docs}
    candidates_by_type: dict[str, list[tuple[dict[str, Any], dict[str, Any]]]] = defaultdict(list)
    for section in read_jsonl(sections_jsonl):
        section_type = str(section.get("section_type") or "body")
        if section_type in {"references", "unknown"}:
            continue
        evidence = _clean_evidence(str(section.get("text") or ""))
        if len(evidence) < min_evidence_chars:
            continue
        doc = docs_by_id.get(str(section["doc_id"]))
        if doc is None:
            continue
        question_type = _balanced_question_type(section_type)
        candidates_by_type[question_type].append((doc, section))

    rng = random.Random(seed)
    for question_type, candidates in candidates_by_type.items():
        candidates.sort(key=lambda item: (str(item[0]["doc_id"]), _candidate_sort_key(item[1])))
        rng.shuffle(candidates)

    targets = _target_counts(limit)
    rows: list[dict[str, Any]] = []
    used_docs: set[str] = set()
    for question_type, target in targets.items():
        for doc, section in candidates_by_type.get(question_type, []):
            if len([row for row in rows if row["question_type"] == question_type]) >= target:
                break
            doc_id = str(doc["doc_id"])
            if doc_id in used_docs:
                continue
            rows.append(
                _build_balanced_row(
                    index=len(rows) + 1,
                    id_prefix=id_prefix,
                    qaset_version=qaset_version,
                    doc=doc,
                    section=section,
                    docs=docs,
                )
            )
            used_docs.add(doc_id)
            if len(rows) >= limit:
                break
        if len(rows) >= limit:
            break

    for question_type, candidates in candidates_by_type.items():
        if len(rows) >= limit:
            break
        for doc, section in candidates:
            doc_id = str(doc["doc_id"])
            if doc_id in used_docs:
                continue
            rows.append(
                _build_balanced_row(
                    index=len(rows) + 1,
                    id_prefix=id_prefix,
                    qaset_version=qaset_version,
                    doc=doc,
                    section=section,
                    docs=docs,
                )
            )
            used_docs.add(doc_id)
            if len(rows) >= limit:
                break

    type_counts = Counter(row["question_type"] for row in rows)
    for row in rows:
        row["qaset_distribution"] = dict(type_counts)
    write_jsonl(output_jsonl, rows)
    return rows




def compact_snippet(text: str, limit: int = 180) -> str:
    value = normalize_space(text)
    return value[:limit]


def result_page(result: Any) -> str:
    metadata = getattr(result, "metadata", {}) or {}
    start = metadata.get("page_start", "")
    end = metadata.get("page_end", "")
    if start == end or not end:
        return str(start)
    return f"{start}-{end}"


def evidence_in_results(question: dict[str, Any], results: list[Any]) -> float:
    evidence_terms = {
        term.lower()
        for term in normalize_space(str(question.get("evidence_text") or "")).split()
        if len(term) > 1
    }
    if not evidence_terms:
        return 0.0
    context = " ".join(str(getattr(result, "content", "")) for result in results).lower()
    matched = sum(1 for term in evidence_terms if term in context)
    return round(matched / len(evidence_terms), 6)

def evaluate_method(
    *,
    case_id: str,
    method: str,
    retriever: Any,
    questions: list[dict[str, Any]],
    top_k: int,
    candidate_multiplier: int = 5,
) -> list[dict[str, Any]]:
    rows = []
    for question in questions:
        start = time.perf_counter()
        results = retriever.search(question["question"], top_k=top_k * candidate_multiplier)
        latency_ms = (time.perf_counter() - start) * 1000
        results = dedupe_parent_results(results)[:top_k]
        gold_docs = set(question.get("gold_doc_ids", []))
        relevance = [parent_id(result) in gold_docs for result in results]
        metric_ids = [
            parent_id(result) if relevant else f"__nonrelevant_{index}"
            for index, (result, relevant) in enumerate(zip(results, relevance))
        ]
        rank = next((index for index, relevant in enumerate(relevance, start=1) if relevant), 0)
        metadata_rows = [getattr(result, "metadata", {}) or {} for result in results]
        rows.append(
            {
                "case_id": case_id,
                "method": method,
                "question_id": question.get("question_id", ""),
                "question_type": question.get("question_type", "unknown"),
                "difficulty": question.get("difficulty", ""),
                "rank": rank,
                "recall_at_5": float(any(relevance[:5])),
                "recall_at_10": float(any(relevance[:10])),
                "mrr": reciprocal_rank(metric_ids, gold_docs),
                "ndcg_at_10": ndcg_at_k(metric_ids, gold_docs, 10),
                "context_precision_at_10": sum(relevance[:10]) / max(len(results[:10]), 1),
                "gold_evidence_in_retrieved_context": evidence_in_results(question, results),
                "retrieved_doc_ids": "|".join(parent_id(result) for result in results),
                "retrieved_chunk_ids": "|".join(str(getattr(result, "doc_id", "")) for result in results),
                "retrieved_pages": "|".join(result_page(result) for result in results),
                "retrieved_section_ids": "|".join(str(metadata.get("section_id", "")) for metadata in metadata_rows),
                "retrieved_snippets": " || ".join(compact_snippet(getattr(result, "content", "")) for result in results),
                "latency_ms": latency_ms,
            }
        )
    return rows


class HybridRrfEvalRetriever:
    def __init__(self, retriever: HybridRetriever, candidate_k: int):
        self.retriever = retriever
        self.candidate_k = candidate_k

    def search(self, query: str, top_k: int) -> list[Any]:
        return self.retriever.search(query, top_k=top_k, candidate_k=self.candidate_k)


def summarize(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(row["case_id"], row["method"], "overall")].append(row)
        grouped[(row["case_id"], row["method"], row["question_type"])].append(row)
        if row.get("difficulty"):
            grouped[(row["case_id"], row["method"], f"difficulty:{row['difficulty']}")].append(row)
    summaries = []
    for (case_id, method, group), values in sorted(grouped.items()):
        latencies = sorted(float(row["latency_ms"]) for row in values)
        summaries.append(
            {
                "case_id": case_id,
                "method": method,
                "group": group,
                "questions": len(values),
                "recall_at_5": mean(float(row["recall_at_5"]) for row in values),
                "recall_at_10": mean(float(row["recall_at_10"]) for row in values),
                "mrr": mean(float(row["mrr"]) for row in values),
                "ndcg_at_10": mean(float(row["ndcg_at_10"]) for row in values),
                "context_precision_at_10": mean(
                    float(row["context_precision_at_10"]) for row in values
                ),
                "gold_evidence_in_retrieved_context": mean(
                    float(row.get("gold_evidence_in_retrieved_context") or 0) for row in values
                ),
                "p50_latency_ms": latencies[len(latencies) // 2],
                "p95_latency_ms": latencies[min(round(len(latencies) * 0.95), len(latencies) - 1)],
            }
        )
    return summaries


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    ensure_parent(path)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]) if rows else [])
        if rows:
            writer.writeheader()
            writer.writerows(rows)


@app.command("build-golden")
def build_golden_command(
    documents_jsonl: Path | None = None,
    sections_jsonl: Path | None = None,
    output_jsonl: Path | None = None,
    limit: int = typer.Option(50, min=1),
    seed: int = 42,
) -> None:
    """Build an auto-approved smoke golden set from academic-paper sections."""
    documents_jsonl = documents_jsonl or default_smoke_processed_path("documents_normalized.jsonl")
    sections_jsonl = sections_jsonl or default_smoke_processed_path("sections.jsonl")
    output_jsonl = output_jsonl or default_smoke_eval_path("golden_questions_auto.jsonl")
    rows = build_golden_questions(documents_jsonl, sections_jsonl, output_jsonl, limit=limit, seed=seed)
    typer.echo(f"Wrote {len(rows)} V3 smoke golden questions to {output_jsonl}")


@app.command("eval-cases")
def eval_cases_command(
    questions_jsonl: Path | None = None,
    summary_csv: Path | None = None,
    details_csv: Path | None = None,
    config_path: list[Path] | None = typer.Option(None, "--config-path"),
    top_k: int = 10,
    candidate_k: int = 50,
    bm25_weight: float = 2.0,
    vector_weight: float = 1.0,
) -> None:
    """Evaluate V3 smoke retrieval for each case config."""
    questions_jsonl = questions_jsonl or default_smoke_eval_path("golden_questions_auto.jsonl")
    summary_csv = summary_csv or default_smoke_eval_path("retrieval_case_summary.csv")
    details_csv = details_csv or default_smoke_eval_path("retrieval_case_details.csv")
    config_paths = config_path or DEFAULT_CASE_CONFIGS
    questions = [
        row for row in read_jsonl(questions_jsonl) if row.get("review_status") != "rejected"
    ]

    all_details: list[dict[str, Any]] = []
    embedder_cache: dict[tuple[str, str, str, str], SentenceTransformerEmbedder] = {}
    for path in config_paths:
        config = load_config(path)
        case_id = config.qdrant.collection.replace("ko_dense_technical_v3_", "")
        bm25 = OpenSearchBM25Retriever(
            config.opensearch.url,
            config.opensearch.index,
            config.opensearch.username,
            config.opensearch.password,
            search_field=config.opensearch.search_field,
        )
        embedder_key = (
            config.embedding.model_name,
            config.embedding.device,
            config.embedding.document_prefix,
            config.embedding.query_prefix,
        )
        embedder = embedder_cache.get(embedder_key)
        if embedder is None:
            embedder = SentenceTransformerEmbedder(
                config.embedding.model_name,
                config.embedding.device,
                config.embedding.document_prefix,
                config.embedding.query_prefix,
            )
            embedder_cache[embedder_key] = embedder
        vector = QdrantVectorRetriever(config.qdrant.url, config.qdrant.collection, embedder)
        methods = {
            "bm25": bm25,
            "vector": vector,
            "hybrid_rrf": HybridRrfEvalRetriever(
                HybridRetriever(bm25, vector, rrf_k=config.retrieval.rrf_k),
                candidate_k,
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
        for method, retriever in methods.items():
            multiplier = max(1, candidate_k // max(top_k, 1)) if method.startswith("hybrid") else 5
            all_details.extend(
                evaluate_method(
                    case_id=case_id,
                    method=method,
                    retriever=retriever,
                    questions=questions,
                    top_k=top_k,
                    candidate_multiplier=multiplier,
                )
            )
        typer.echo(f"Evaluated {case_id} against {len(questions)} questions")

    write_csv(details_csv, all_details)
    summaries = summarize(all_details)
    write_csv(summary_csv, summaries)
    typer.echo(f"Wrote {len(summaries)} V3 retrieval summary rows to {summary_csv}")


def main() -> None:
    app()




