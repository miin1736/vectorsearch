from __future__ import annotations

import json
import re
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any, Iterator

import typer

from koreanops_rag.io import ensure_parent, read_jsonl
from koreanops_rag.office.common import normalize_line
from koreanops_rag.schemas import PageBlock

app = typer.Typer(add_completion=False)

PAGE_NUMBER_RE = re.compile(r"^\s*[-–—]?\s*\d{1,4}\s*[-–—]?\s*$")


def _span_font_size(block: dict[str, Any]) -> float:
    sizes = [
        float(span.get("size", 0.0))
        for line in block.get("lines", [])
        for span in line.get("spans", [])
        if str(span.get("text", "")).strip()
    ]
    return max(sizes, default=0.0)


def _block_text(block: dict[str, Any]) -> str:
    lines = []
    for line in block.get("lines", []):
        text = "".join(str(span.get("text", "")) for span in line.get("spans", []))
        text = normalize_line(text)
        if text:
            lines.append(text)
    return "\n".join(lines)


def _reading_order(blocks: list[dict[str, Any]], page_width: float) -> list[dict[str, Any]]:
    full_width = []
    left = []
    right = []
    center = page_width / 2
    for block in blocks:
        x0, _, x1, _ = block["bbox"]
        if x0 < center < x1 or (x1 - x0) >= page_width * 0.65:
            full_width.append(block)
        elif x1 <= center:
            left.append(block)
        else:
            right.append(block)
    if left and right:
        first_column_y = min([block["bbox"][1] for block in left + right])
        headers = [block for block in full_width if block["bbox"][1] <= first_column_y]
        footers = [block for block in full_width if block not in headers]
        return (
            sorted(headers, key=lambda item: (item["bbox"][1], item["bbox"][0]))
            + sorted(left, key=lambda item: (item["bbox"][1], item["bbox"][0]))
            + sorted(right, key=lambda item: (item["bbox"][1], item["bbox"][0]))
            + sorted(footers, key=lambda item: (item["bbox"][1], item["bbox"][0]))
        )
    return sorted(blocks, key=lambda item: (item["bbox"][1], item["bbox"][0]))


def extract_pdf(pdf_bytes: bytes) -> tuple[list[dict[str, Any]], str, int]:
    import fitz

    document = fitz.open(stream=pdf_bytes, filetype="pdf")
    pages: list[dict[str, Any]] = []
    title_candidates: list[tuple[float, int, str]] = []
    for page_index, page in enumerate(document):
        raw = page.get_text("dict")
        text_blocks = []
        for block in raw.get("blocks", []):
            if block.get("type") != 0:
                continue
            text = _block_text(block)
            if not text:
                continue
            font_size = _span_font_size(block)
            item = {
                "bbox": tuple(float(value) for value in block["bbox"]),
                "text": text,
                "font_size": font_size,
            }
            text_blocks.append(item)
            if page_index < 2 and len(text) <= 200:
                title_candidates.append((font_size, -page_index, text))
        ordered = _reading_order(text_blocks, float(page.rect.width))
        pages.append(
            {
                "page_num": page_index + 1,
                "width": float(page.rect.width),
                "height": float(page.rect.height),
                "blocks": ordered,
                "raw_text": "\n".join(block["text"] for block in ordered),
            }
        )
    document.close()
    title = max(title_candidates, default=(0.0, 0, ""))[2]
    text_layer_pages = sum(bool(page["raw_text"].strip()) for page in pages)
    return pages, title, text_layer_pages


def _repeated_edge_texts(pages: list[dict[str, Any]]) -> set[str]:
    candidates: Counter[str] = Counter()
    for page in pages:
        blocks = page["blocks"]
        if not blocks:
            continue
        height = float(page["height"])
        for block in blocks:
            _, y0, _, y1 = block["bbox"]
            if y1 <= height * 0.12 or y0 >= height * 0.88:
                normalized = normalize_line(block["text"])
                if normalized and not PAGE_NUMBER_RE.match(normalized):
                    candidates[normalized] += 1
    threshold = max(2, round(len(pages) * 0.5))
    return {text for text, count in candidates.items() if count >= threshold}


def clean_pages(doc_id: str, pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    repeated = _repeated_edge_texts(pages)
    cleaned_pages = []
    for page in pages:
        kept = []
        font_sizes = [float(block["font_size"]) for block in page["blocks"]]
        median_size = sorted(font_sizes)[len(font_sizes) // 2] if font_sizes else 0.0
        for block_index, block in enumerate(page["blocks"]):
            text = normalize_line(block["text"])
            if not text or text in repeated or PAGE_NUMBER_RE.match(text):
                continue
            kept.append(
                PageBlock(
                    block_id=f"{doc_id}_p{page['page_num']:03d}_b{block_index:03d}",
                    page_num=int(page["page_num"]),
                    bbox=block["bbox"],
                    text=text,
                    raw_text=block["text"],
                    font_size=float(block["font_size"]),
                    is_heading=bool(
                        median_size and float(block["font_size"]) >= median_size * 1.25
                    ),
                    reading_order=len(kept),
                ).model_dump(mode="json")
            )
        cleaned_pages.append({**page, "blocks": kept, "clean_text": "\n\n".join(
            block["text"] for block in kept
        )})
    return cleaned_pages


def iter_manifest(manifest_jsonl: Path, offset: int, limit: int | None) -> Iterator[dict]:
    for index, row in enumerate(read_jsonl(manifest_jsonl)):
        if index < offset:
            continue
        if limit is not None and index >= offset + limit:
            return
        yield row


@app.command()
def run(
    dataset_root: Path,
    manifest_jsonl: Path,
    pages_output: Path,
    blocks_output: Path,
    documents_output: Path,
    limit: int | None = typer.Option(None, min=1),
    offset: int = typer.Option(0, min=0),
) -> None:
    """Parse office PDFs without consulting label JSON files."""
    for path in (pages_output, blocks_output, documents_output):
        ensure_parent(path)
    archive_cache: dict[str, zipfile.ZipFile] = {}
    processed = 0
    try:
        with (
            pages_output.open("w", encoding="utf-8", newline="\n") as pages_file,
            blocks_output.open("w", encoding="utf-8", newline="\n") as blocks_file,
            documents_output.open("w", encoding="utf-8", newline="\n") as documents_file,
        ):
            for row in iter_manifest(manifest_jsonl, offset=offset, limit=limit):
                archive_name = row["source_archive"]
                archive = archive_cache.get(archive_name)
                if archive is None:
                    archive = zipfile.ZipFile(dataset_root / archive_name)
                    archive_cache[archive_name] = archive
                error = ""
                try:
                    pdf_bytes = archive.read(row["source_member"])
                    pages, title, text_layer_pages = extract_pdf(pdf_bytes)
                    cleaned_pages = clean_pages(row["doc_id"], pages)
                except Exception as exc:  # keep batch processing restartable
                    pages, cleaned_pages, title, text_layer_pages = [], [], "", 0
                    error = f"{type(exc).__name__}: {exc}"
                for raw_page, cleaned_page in zip(pages, cleaned_pages, strict=True):
                    pages_file.write(json.dumps(
                        {
                            "doc_id": row["doc_id"],
                            "page_num": raw_page["page_num"],
                            "width": raw_page["width"],
                            "height": raw_page["height"],
                            "raw_text": raw_page["raw_text"],
                            "clean_text": cleaned_page["clean_text"],
                        },
                        ensure_ascii=False,
                    ) + "\n")
                    for block in cleaned_page["blocks"]:
                        blocks_file.write(json.dumps(
                            {"doc_id": row["doc_id"], **block}, ensure_ascii=False
                        ) + "\n")
                content = "\n\n".join(page["clean_text"] for page in cleaned_pages)
                documents_file.write(json.dumps(
                    {
                        "doc_id": row["doc_id"],
                        "source_type": "office_document",
                        "title": title or row["doc_id"],
                        "content": content,
                        "embedding_text": content,
                        "metadata": {
                            "split": row["split"],
                            "document_type": row["document_type"],
                            "publisher": "",
                            "page_count": len(pages),
                            "text_layer_pages": text_layer_pages,
                            "source_archive": archive_name,
                            "source_member": row["source_member"],
                            "parse_error": error,
                        },
                    },
                    ensure_ascii=False,
                ) + "\n")
                processed += 1
                if processed % 100 == 0:
                    typer.echo(f"Parsed {processed} PDFs...")
    finally:
        for archive in archive_cache.values():
            archive.close()
    typer.echo(f"Parsed {processed} PDFs into {documents_output}")


def main() -> None:
    app()
