from __future__ import annotations

import csv
import re
from collections import defaultdict
from os import getenv
from pathlib import Path
from statistics import mean
from typing import Any, Iterator, Literal

import typer

from koreanops_rag.io import ensure_parent, read_jsonl, write_jsonl

app = typer.Typer(add_completion=False)
Strategy = Literal["fixed", "tokenizer_fixed", "page_subchunk", "section", "sentence", "passage"]
REGEX_TOKEN_RE = re.compile(r"\w+|[^\w\s]", re.UNICODE)
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def default_data_root() -> Path:
    return Path(getenv("DATA_ROOT", r"C:\vectorsearch-data")) / "ko-dense-technical"


def default_smoke_processed_path(name: str) -> Path:
    return default_data_root() / "processed" / "smoke_100" / name


def default_smoke_eval_path(name: str) -> Path:
    return default_data_root() / "eval" / "smoke_100" / name


class TokenCounter:
    def __init__(self, model_name: str) -> None:
        from transformers import AutoTokenizer

        self.model_name = model_name
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)

    def ids(self, text: str) -> list[int]:
        return self.tokenizer.encode(text, add_special_tokens=False)

    def count(self, text: str) -> int:
        return len(self.ids(text))

    def decode(self, token_ids: list[int]) -> str:
        return self.tokenizer.decode(
            token_ids,
            skip_special_tokens=True,
            clean_up_tokenization_spaces=True,
        ).strip()

    def decode_with_budget(self, token_ids: list[int], token_budget: int) -> str:
        current_ids = token_ids[:token_budget]
        while current_ids:
            text = self.decode(current_ids)
            if self.count(text) <= token_budget:
                return text
            current_ids = current_ids[:-1]
        return ""


def group_by_doc(path: Path) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in read_jsonl(path):
        grouped[str(row["doc_id"])].append(row)
    return grouped


def token_windows(
    text: str,
    token_counter: TokenCounter,
    token_budget: int,
    overlap: int,
) -> Iterator[tuple[str, int, int]]:
    token_ids = token_counter.ids(text)
    if not token_ids:
        return
    start = 0
    while start < len(token_ids):
        end = min(start + token_budget, len(token_ids))
        chunk = token_counter.decode_with_budget(token_ids[start:end], token_budget)
        if chunk:
            yield chunk, start, end
        if end == len(token_ids):
            break
        start = max(start + 1, end - overlap)


def regex_token_windows(text: str, token_budget: int, overlap: int) -> Iterator[tuple[str, int, int]]:
    matches = list(REGEX_TOKEN_RE.finditer(text))
    if not matches:
        return
    start = 0
    while start < len(matches):
        end = min(start + token_budget, len(matches))
        chunk = text[matches[start].start() : matches[end - 1].end()].strip()
        if chunk:
            yield chunk, start, end
        if end == len(matches):
            break
        start = max(start + 1, end - overlap)


def split_sentences(text: str) -> list[str]:
    sentences = [part.strip() for part in SENTENCE_SPLIT_RE.split(text) if part.strip()]
    return sentences or [text.strip()] if text.strip() else []


def split_passages(text: str) -> list[str]:
    passages = [part.strip() for part in re.split(r"\n\s*\n+", text) if part.strip()]
    if len(passages) > 1:
        return passages
    return split_sentences(text)


def merge_text_units(
    units: list[str],
    token_counter: TokenCounter,
    *,
    token_budget: int,
    min_tokens: int,
    overlap_units: int = 0,
) -> Iterator[tuple[str, int, int, int]]:
    index = 0
    while index < len(units):
        current: list[str] = []
        current_tokens = 0
        end = index
        while end < len(units):
            unit = units[end]
            unit_tokens = token_counter.count(unit)
            if not current and unit_tokens > token_budget:
                for chunk, token_start, token_end in token_windows(
                    unit,
                    token_counter,
                    token_budget,
                    overlap=0,
                ):
                    yield chunk, token_start, token_end, token_counter.count(chunk)
                end += 1
                break
            if current and current_tokens + unit_tokens > token_budget:
                break
            current.append(unit)
            current_tokens += unit_tokens
            end += 1
            if current_tokens >= min_tokens:
                break
        if current:
            text = normalize_unit_text(current)
            yield text, index, end, token_counter.count(text)
        if end >= len(units):
            break
        index = max(index + 1, end - overlap_units)


def normalize_unit_text(units: list[str]) -> str:
    return "\n".join(unit.strip() for unit in units if unit.strip()).strip()


def preferred_text(row: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = str(row.get(key) or "")
        if value.strip():
            return value
    return ""


def chunk_row(
    doc: dict[str, Any],
    text: str,
    *,
    strategy: str,
    chunk_index: int,
    token_count: int,
    page_start: int = 0,
    page_end: int = 0,
    section_id: str = "",
    section_type: str = "",
    section_title: str = "",
    token_start: int = 0,
    token_end: int = 0,
) -> dict[str, Any]:
    metadata = dict(doc.get("metadata", {}))
    metadata.update(
        {
            "parent_doc_id": doc["doc_id"],
            "chunking_strategy": strategy,
            "chunk_index": chunk_index,
            "page_start": page_start,
            "page_end": page_end,
            "section_id": section_id,
            "section_type": section_type,
            "section_title": section_title,
            "token_count": token_count,
            "token_start": token_start,
            "token_end": token_end,
        }
    )
    preserved_text = "\n".join(
        str(item.get("text") or item.get("raw_line") or "")
        for item in doc.get("preserved_elements", [])[:40]
        if isinstance(item, dict)
    )
    bm25_text = "\n".join(part for part in [text, preserved_text] if part).strip()
    display_text = str(doc.get("display_text") or text)
    return {
        "doc_id": f"{doc['doc_id']}__{strategy}_{chunk_index:05d}",
        "source_type": "academic_paper",
        "title": doc.get("title", ""),
        "content": text,
        "bm25_text": bm25_text,
        "embedding_text": text,
        "display_text": display_text,
        "preserved_elements": doc.get("preserved_elements", []),
        "alignment_map": doc.get("alignment_map", []),
        "metadata": metadata,
    }


def iter_fixed_chunks(
    documents_jsonl: Path,
    token_counter: TokenCounter,
    *,
    strategy: str,
    token_budget: int,
    overlap: int,
) -> Iterator[dict[str, Any]]:
    for doc in read_jsonl(documents_jsonl):
        content = preferred_text(doc, "embedding_text", "content")
        windows = (
            regex_token_windows(content, token_budget, overlap)
            if strategy == "fixed"
            else token_windows(content, token_counter, token_budget, overlap)
        )
        for index, (text, token_start, token_end) in enumerate(windows):
            count = (
                len(REGEX_TOKEN_RE.findall(text))
                if strategy == "fixed"
                else token_counter.count(text)
            )
            yield chunk_row(
                doc,
                text,
                strategy=strategy,
                chunk_index=index,
                token_count=count,
                token_start=token_start,
                token_end=token_end,
            )


def iter_page_subchunks(
    documents_jsonl: Path,
    pages_jsonl: Path,
    token_counter: TokenCounter,
    *,
    token_budget: int,
    overlap: int,
) -> Iterator[dict[str, Any]]:
    pages_by_doc = group_by_doc(pages_jsonl)
    docs = {str(doc["doc_id"]): doc for doc in read_jsonl(documents_jsonl)}
    for doc_id, pages in pages_by_doc.items():
        doc = docs.get(doc_id)
        if doc is None:
            continue
        chunk_index = 0
        for page in sorted(pages, key=lambda row: int(row["page_num"])):
            text = preferred_text(page, "embedding_text", "clean_text", "raw_text")
            for chunk, token_start, token_end in token_windows(
                text, token_counter, token_budget, overlap
            ):
                page_num = int(page["page_num"])
                yield chunk_row(
                    doc,
                    chunk,
                    strategy="page_subchunk",
                    chunk_index=chunk_index,
                    token_count=token_counter.count(chunk),
                    page_start=page_num,
                    page_end=page_num,
                    token_start=token_start,
                    token_end=token_end,
                )
                chunk_index += 1


def iter_section_chunks(
    documents_jsonl: Path,
    sections_jsonl: Path,
    token_counter: TokenCounter,
    *,
    token_budget: int,
    overlap: int,
) -> Iterator[dict[str, Any]]:
    sections_by_doc = group_by_doc(sections_jsonl)
    docs = {str(doc["doc_id"]): doc for doc in read_jsonl(documents_jsonl)}
    for doc_id, sections in sections_by_doc.items():
        doc = docs.get(doc_id)
        if doc is None:
            continue
        chunk_index = 0
        for section in sorted(sections, key=lambda row: int(row["section_index"])):
            text = preferred_text(section, "embedding_text", "text")
            for chunk, token_start, token_end in token_windows(
                text, token_counter, token_budget, overlap
            ):
                yield chunk_row(
                    doc,
                    chunk,
                    strategy="section",
                    chunk_index=chunk_index,
                    token_count=token_counter.count(chunk),
                    page_start=int(section.get("page_start") or 0),
                    page_end=int(section.get("page_end") or 0),
                    section_id=str(section.get("section_id") or ""),
                    section_type=str(section.get("section_type") or ""),
                    section_title=str(section.get("section_title") or ""),
                    token_start=token_start,
                    token_end=token_end,
                )
                chunk_index += 1


def iter_sentence_chunks(
    documents_jsonl: Path,
    sections_jsonl: Path,
    token_counter: TokenCounter,
    *,
    token_budget: int,
    min_tokens: int = 96,
    overlap_units: int = 1,
) -> Iterator[dict[str, Any]]:
    sections_by_doc = group_by_doc(sections_jsonl)
    docs = {str(doc["doc_id"]): doc for doc in read_jsonl(documents_jsonl)}
    for doc_id, sections in sections_by_doc.items():
        doc = docs.get(doc_id)
        if doc is None:
            continue
        chunk_index = 0
        for section in sorted(sections, key=lambda row: int(row["section_index"])):
            sentences = split_sentences(preferred_text(section, "embedding_text", "text"))
            for chunk, unit_start, unit_end, token_count in merge_text_units(
                sentences,
                token_counter,
                token_budget=token_budget,
                min_tokens=min_tokens,
                overlap_units=overlap_units,
            ):
                yield chunk_row(
                    doc,
                    chunk,
                    strategy="sentence",
                    chunk_index=chunk_index,
                    token_count=token_count,
                    page_start=int(section.get("page_start") or 0),
                    page_end=int(section.get("page_end") or 0),
                    section_id=str(section.get("section_id") or ""),
                    section_type=str(section.get("section_type") or ""),
                    section_title=str(section.get("section_title") or ""),
                    token_start=unit_start,
                    token_end=unit_end,
                )
                chunk_index += 1


def iter_passage_chunks(
    documents_jsonl: Path,
    sections_jsonl: Path,
    token_counter: TokenCounter,
    *,
    token_budget: int,
    min_tokens: int = 320,
    overlap_units: int = 1,
) -> Iterator[dict[str, Any]]:
    sections_by_doc = group_by_doc(sections_jsonl)
    docs = {str(doc["doc_id"]): doc for doc in read_jsonl(documents_jsonl)}
    for doc_id, sections in sections_by_doc.items():
        doc = docs.get(doc_id)
        if doc is None:
            continue
        chunk_index = 0
        for section in sorted(sections, key=lambda row: int(row["section_index"])):
            passages = split_passages(preferred_text(section, "embedding_text", "text"))
            for chunk, unit_start, unit_end, token_count in merge_text_units(
                passages,
                token_counter,
                token_budget=token_budget,
                min_tokens=min_tokens,
                overlap_units=overlap_units,
            ):
                yield chunk_row(
                    doc,
                    chunk,
                    strategy="passage",
                    chunk_index=chunk_index,
                    token_count=token_count,
                    page_start=int(section.get("page_start") or 0),
                    page_end=int(section.get("page_end") or 0),
                    section_id=str(section.get("section_id") or ""),
                    section_type=str(section.get("section_type") or ""),
                    section_title=str(section.get("section_title") or ""),
                    token_start=unit_start,
                    token_end=unit_end,
                )
                chunk_index += 1


def audit_token_lengths(
    documents_jsonl: Path,
    pages_jsonl: Path,
    sections_jsonl: Path,
    token_counter: TokenCounter,
    output_csv: Path,
    *,
    max_length: int = 512,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for unit, path, text_key in [
        ("document", documents_jsonl, "content"),
        ("page", pages_jsonl, "clean_text"),
        ("section", sections_jsonl, "text"),
    ]:
        lengths = [token_counter.count(str(row.get(text_key) or "")) for row in read_jsonl(path)]
        if not lengths:
            continue
        sorted_lengths = sorted(lengths)
        rows.append(
            {
                "unit": unit,
                "count": len(lengths),
                "min_tokens": min(lengths),
                "mean_tokens": round(mean(lengths), 3),
                "p50_tokens": sorted_lengths[len(sorted_lengths) // 2],
                "p95_tokens": sorted_lengths[int((len(sorted_lengths) - 1) * 0.95)],
                "max_tokens": max(lengths),
                "over_max_count": sum(1 for value in lengths if value > max_length),
                "over_max_ratio": round(
                    sum(1 for value in lengths if value > max_length) / len(lengths),
                    6,
                ),
                "max_length": max_length,
                "tokenizer": token_counter.model_name,
            }
        )
    ensure_parent(output_csv)
    with output_csv.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]) if rows else [])
        if rows:
            writer.writeheader()
            writer.writerows(rows)
    return rows


@app.command("build")
def build_chunks(
    documents_jsonl: Path | None = None,
    output_jsonl: Path | None = None,
    strategy: Strategy = "tokenizer_fixed",
    pages_jsonl: Path | None = None,
    sections_jsonl: Path | None = None,
    model_name: str = "intfloat/multilingual-e5-small",
    token_budget: int = 512,
    overlap: int = 64,
) -> None:
    """Build V3 academic-paper chunks for one smoke strategy."""
    documents_jsonl = documents_jsonl or default_smoke_processed_path("documents_normalized.jsonl")
    output_jsonl = output_jsonl or default_smoke_processed_path("chunks.jsonl")
    pages_jsonl = pages_jsonl or default_smoke_processed_path("pages.jsonl")
    sections_jsonl = sections_jsonl or default_smoke_processed_path("sections.jsonl")
    token_counter = TokenCounter(model_name)
    if strategy in {"fixed", "tokenizer_fixed"}:
        rows = iter_fixed_chunks(
            documents_jsonl,
            token_counter,
            strategy=strategy,
            token_budget=token_budget,
            overlap=overlap,
        )
    elif strategy == "page_subchunk":
        rows = iter_page_subchunks(
            documents_jsonl,
            pages_jsonl,
            token_counter,
            token_budget=token_budget,
            overlap=overlap,
        )
    elif strategy == "section":
        rows = iter_section_chunks(
            documents_jsonl,
            sections_jsonl,
            token_counter,
            token_budget=token_budget,
            overlap=overlap,
        )
    elif strategy == "sentence":
        rows = iter_sentence_chunks(
            documents_jsonl,
            sections_jsonl,
            token_counter,
            token_budget=token_budget,
            min_tokens=max(1, token_budget // 2),
            overlap_units=1 if overlap else 0,
        )
    else:
        rows = iter_passage_chunks(
            documents_jsonl,
            sections_jsonl,
            token_counter,
            token_budget=token_budget,
            min_tokens=max(1, int(token_budget * 0.8)),
            overlap_units=1 if overlap else 0,
        )
    count = write_jsonl(output_jsonl, rows)
    typer.echo(f"Wrote {count} {strategy} chunks to {output_jsonl}")


@app.command("audit")
def audit(
    documents_jsonl: Path | None = None,
    pages_jsonl: Path | None = None,
    sections_jsonl: Path | None = None,
    output_csv: Path | None = None,
    model_name: str = "intfloat/multilingual-e5-small",
    max_length: int = 512,
) -> None:
    """Audit E5 tokenizer lengths for documents, pages, and sections."""
    documents_jsonl = documents_jsonl or default_smoke_processed_path("documents_normalized.jsonl")
    pages_jsonl = pages_jsonl or default_smoke_processed_path("pages.jsonl")
    sections_jsonl = sections_jsonl or default_smoke_processed_path("sections.jsonl")
    output_csv = output_csv or default_smoke_eval_path("truncation_audit_e5.csv")
    rows = audit_token_lengths(
        documents_jsonl,
        pages_jsonl,
        sections_jsonl,
        TokenCounter(model_name),
        output_csv,
        max_length=max_length,
    )
    typer.echo(f"Wrote {len(rows)} tokenizer audit rows to {output_csv}")


def main() -> None:
    app()


