from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path
from typing import Iterator, Literal

import typer

from koreanops_rag.io import read_jsonl, write_jsonl

app = typer.Typer(add_completion=False)
Strategy = Literal["fixed", "page", "structure", "contextual", "oracle"]
TOKEN_RE = re.compile(r"\w+|[^\w\s]", re.UNICODE)


def token_count(text: str) -> int:
    return len(TOKEN_RE.findall(text))


def split_fixed(text: str, size: int = 512, overlap: int = 64) -> list[str]:
    return [chunk for chunk, _, _ in split_fixed_spans(text, size, overlap)]


def split_fixed_spans(
    text: str, size: int = 512, overlap: int = 64
) -> list[tuple[str, int, int]]:
    matches = list(TOKEN_RE.finditer(text))
    if not matches:
        return []
    chunks: list[tuple[str, int, int]] = []
    start = 0
    while start < len(matches):
        end = min(start + size, len(matches))
        char_start = matches[start].start()
        char_end = matches[end - 1].end()
        chunks.append((text[char_start:char_end].strip(), char_start, char_end))
        if end == len(matches):
            break
        start = max(start + 1, end - overlap)
    return chunks


def _chunk_row(
    doc: dict,
    content: str,
    index: int,
    strategy: str,
    page_start: int,
    page_end: int,
    section_path: str = "",
) -> dict:
    context = ""
    if strategy == "contextual":
        metadata = doc.get("metadata", {})
        context = (
            f"문서명: {doc.get('title', '')}\n"
            f"문서유형: {metadata.get('document_type', '')}\n"
            f"발행처: {metadata.get('publisher', '')}\n"
            f"섹션: {section_path}\n"
        )
    text = f"{context}{content}".strip()
    return {
        "doc_id": f"{doc['doc_id']}__{strategy}_{index:04d}",
        "source_type": "office_document",
        "title": doc.get("title", ""),
        "content": text,
        "embedding_text": text,
        "metadata": {
            **dict(doc.get("metadata", {})),
            "parent_doc_id": doc["doc_id"],
            "page_start": page_start,
            "page_end": page_end,
            "section_path": section_path,
            "chunk_index": index,
            "chunking_strategy": strategy,
        },
    }


def _group_rows(path: Path | None) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    if path is None:
        return grouped
    for row in read_jsonl(path):
        grouped[row["doc_id"]].append(row)
    return grouped


def _pack_sections(blocks: list[dict], min_tokens: int, max_tokens: int) -> list[dict]:
    raw_sections = []
    current_texts: list[str] = []
    current_pages: list[int] = []
    current_heading = ""
    for block in sorted(
        blocks, key=lambda row: (row["page_num"], row.get("reading_order", 0))
    ):
        text = str(block.get("text") or "").strip()
        if not text:
            continue
        if block.get("is_heading") and current_texts:
            raw_sections.append(
                {
                    "text": "\n\n".join(current_texts),
                    "pages": current_pages,
                    "heading": current_heading,
                }
            )
            current_texts = []
            current_pages = []
            current_heading = text
        elif block.get("is_heading"):
            current_heading = text
        candidate = "\n\n".join([*current_texts, text])
        if current_texts and token_count(candidate) > max_tokens:
            raw_sections.append(
                {
                    "text": "\n\n".join(current_texts),
                    "pages": current_pages,
                    "heading": current_heading,
                }
            )
            current_texts = [text]
            current_pages = [int(block["page_num"])]
        else:
            current_texts.append(text)
            current_pages.append(int(block["page_num"]))
    if current_texts:
        raw_sections.append(
            {
                "text": "\n\n".join(current_texts),
                "pages": current_pages,
                "heading": current_heading,
            }
        )
    sections = []
    current: dict | None = None
    for section in raw_sections:
        if current is None:
            current = section
            continue
        combined = f"{current['text']}\n\n{section['text']}"
        if token_count(current["text"]) < min_tokens and token_count(combined) <= max_tokens:
            current = {
                "text": combined,
                "pages": [*current["pages"], *section["pages"]],
                "heading": " > ".join(
                    value for value in [current["heading"], section["heading"]] if value
                ),
            }
        else:
            sections.append(current)
            current = section
    if current is not None:
        if (
            sections
            and token_count(current["text"]) < min_tokens
            and token_count(f"{sections[-1]['text']}\n\n{current['text']}") <= max_tokens
        ):
            previous = sections.pop()
            current = {
                "text": f"{previous['text']}\n\n{current['text']}",
                "pages": [*previous["pages"], *current["pages"]],
                "heading": " > ".join(
                    value for value in [previous["heading"], current["heading"]] if value
                ),
            }
        sections.append(current)
    return sections


def iter_chunks(
    documents_jsonl: Path,
    strategy: Strategy,
    blocks_jsonl: Path | None = None,
    pages_jsonl: Path | None = None,
    fixed_tokens: int = 512,
    overlap_tokens: int = 64,
    min_tokens: int = 350,
    max_tokens: int = 700,
) -> Iterator[dict]:
    blocks = _group_rows(blocks_jsonl)
    pages = _group_rows(pages_jsonl)
    for doc in read_jsonl(documents_jsonl):
        if strategy == "fixed":
            page_rows = sorted(pages.get(doc["doc_id"], []), key=lambda row: row["page_num"])
            page_ranges = []
            if page_rows:
                parts = []
                cursor = 0
                for page in page_rows:
                    page_text = str(page.get("clean_text") or page.get("raw_text") or "")
                    parts.append(page_text)
                    page_ranges.append(
                        (cursor, cursor + len(page_text), int(page["page_num"]))
                    )
                    cursor += len(page_text) + 2
                content = "\n\n".join(parts)
            else:
                content = str(doc.get("content", ""))
            for index, (text, start, end) in enumerate(
                split_fixed_spans(content, fixed_tokens, overlap_tokens)
            ):
                covered_pages = [
                    page_num
                    for page_start, page_end, page_num in page_ranges
                    if page_end > start and page_start < end
                ]
                yield _chunk_row(
                    doc,
                    text,
                    index,
                    strategy,
                    min(covered_pages, default=0),
                    max(covered_pages, default=0),
                )
            continue
        if strategy in {"page", "oracle"}:
            page_rows = sorted(pages.get(doc["doc_id"], []), key=lambda row: row["page_num"])
            for index, page in enumerate(page_rows):
                content = str(page.get("content") or page.get("clean_text") or page.get("raw_text") or "")
                if content.strip():
                    yield _chunk_row(
                        doc,
                        content,
                        index,
                        strategy,
                        int(page["page_num"]),
                        int(page["page_num"]),
                    )
            continue
        sections = _pack_sections(blocks.get(doc["doc_id"], []), min_tokens, max_tokens)
        for index, section in enumerate(sections):
            page_numbers = section["pages"] or [0]
            yield _chunk_row(
                doc,
                section["text"],
                index,
                strategy,
                min(page_numbers),
                max(page_numbers),
                section["heading"],
            )


@app.command()
def run(
    documents_jsonl: Path,
    output_jsonl: Path,
    strategy: Strategy,
    blocks_jsonl: Path | None = None,
    pages_jsonl: Path | None = None,
    fixed_tokens: int = 512,
    overlap_tokens: int = 64,
    min_tokens: int = 350,
    max_tokens: int = 700,
) -> None:
    """Create fixed, page, structure, contextual, or Oracle chunks."""
    if strategy in {"structure", "contextual"} and blocks_jsonl is None:
        raise typer.BadParameter("--blocks-jsonl is required for structure/contextual")
    if strategy in {"page", "oracle"} and pages_jsonl is None:
        raise typer.BadParameter("--pages-jsonl is required for page/oracle")
    count = write_jsonl(
        output_jsonl,
        iter_chunks(
            documents_jsonl,
            strategy,
            blocks_jsonl,
            pages_jsonl,
            fixed_tokens,
            overlap_tokens,
            min_tokens,
            max_tokens,
        ),
    )
    typer.echo(f"Wrote {count} {strategy} chunks to {output_jsonl}")


def main() -> None:
    app()
