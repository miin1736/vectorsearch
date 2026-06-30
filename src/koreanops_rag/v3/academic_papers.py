from __future__ import annotations

import re
import zipfile
from collections import Counter
from os import getenv
from pathlib import Path
from typing import Iterator

import fitz
import typer

from koreanops_rag.io import ensure_parent, read_jsonl, write_jsonl

inventory_app = typer.Typer(add_completion=False)
parse_app = typer.Typer(add_completion=False)

PDF_SUFFIX = ".pdf"
PPTX_SUFFIX = ".pptx"
SECTION_PATTERNS = [
    ("abstract", re.compile(r"^(abstract|초록|요약)\b", re.IGNORECASE)),
    ("introduction", re.compile(r"^(\d+\.?\s*)?(서론|introduction)\b", re.IGNORECASE)),
    ("related_work", re.compile(r"^(\d+\.?\s*)?(관련\s*연구|related work)\b", re.IGNORECASE)),
    ("method", re.compile(r"^(\d+\.?\s*)?(방법|방법론|제안\s*방법|method|methodology|approach)\b", re.IGNORECASE)),
    ("experiment", re.compile(r"^(\d+\.?\s*)?(실험|experiment|evaluation)\b", re.IGNORECASE)),
    ("result", re.compile(r"^(\d+\.?\s*)?(결과|result|discussion)\b", re.IGNORECASE)),
    ("conclusion", re.compile(r"^(\d+\.?\s*)?(결론|conclusion)\b", re.IGNORECASE)),
    ("references", re.compile(r"^(참고문헌|references)\b", re.IGNORECASE)),
]


def default_data_root() -> Path:
    return Path(getenv("DATA_ROOT", r"C:\vectorsearch-data")) / "ko-dense-technical"


def default_raw_dir() -> Path:
    return default_data_root() / "raw" / "aihub_academic_papers"


def default_processed_path(name: str) -> Path:
    return default_data_root() / "processed" / name


def default_eval_path(name: str) -> Path:
    return default_data_root() / "eval" / name


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def discover_academic_files(raw_dir: Path) -> Iterator[dict]:
    for path in sorted(raw_dir.rglob("*")):
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        if suffix == ".zip":
            yield from discover_zip_entries(raw_dir, path)
            continue
        if suffix not in {PDF_SUFFIX, PPTX_SUFFIX}:
            continue
        relative = path.relative_to(raw_dir)
        row = {
            "doc_id": stable_doc_id(relative),
            "source_path": str(path),
            "relative_path": str(relative),
            "file_name": path.name,
            "file_type": suffix.removeprefix("."),
            "size_bytes": path.stat().st_size,
            "research_field": infer_research_field(relative),
            "paper_topic": infer_topic(path),
            "publication_year": infer_year(path.name),
            "parse_status": "pending" if suffix == PDF_SUFFIX else "unsupported_pptx",
        }
        yield row


def discover_zip_entries(raw_dir: Path, zip_path: Path) -> Iterator[dict]:
    with zipfile.ZipFile(zip_path) as archive:
        for entry in sorted(archive.infolist(), key=lambda value: value.filename):
            if entry.is_dir():
                continue
            suffix = Path(entry.filename).suffix.lower()
            if suffix not in {PDF_SUFFIX, PPTX_SUFFIX}:
                continue
            relative_zip = zip_path.relative_to(raw_dir)
            entry_path = entry.filename.lstrip("/")
            logical_relative = relative_zip.parent / Path(entry_path)
            field_source = relative_zip / Path(entry_path)
            yield {
                "doc_id": stable_doc_id(logical_relative),
                "source_path": str(zip_path),
                "zip_entry": entry.filename,
                "relative_path": str(logical_relative),
                "file_name": Path(entry.filename).name,
                "file_type": suffix.removeprefix("."),
                "size_bytes": entry.file_size,
                "compressed_size_bytes": entry.compress_size,
                "research_field": infer_research_field(field_source),
                "paper_topic": infer_topic(Path(entry.filename)),
                "publication_year": infer_year(entry.filename),
                "parse_status": "pending" if suffix == PDF_SUFFIX else "unsupported_pptx",
            }


def stable_doc_id(relative_path: Path) -> str:
    slug = re.sub(r"[^0-9A-Za-z가-힣]+", "_", str(relative_path.with_suffix("")))
    return f"paper_{slug.strip('_')[:140]}"


def infer_research_field(relative_path: Path) -> str:
    value = str(relative_path)
    if "과학기술" in value or "(ST)" in value or "_ST" in value:
        return "과학기술"
    if "사회과학" in value or "(SS)" in value or "_SS" in value:
        return "사회과학"
    if "인문학" in value or "예술체육학" in value or "(HA)" in value or "_HA" in value:
        return "인문학_예술체육학"
    return relative_path.parts[0] if len(relative_path.parts) > 1 else "unknown"


def infer_topic(path: Path) -> str:
    return normalize_text(path.stem.replace("_", " ").replace("-", " "))


def infer_year(value: str) -> str:
    match = re.search(r"(19|20)\d{2}", value)
    return match.group(0) if match else ""


def extract_pdf_rows(manifest_row: dict) -> tuple[list[dict], dict]:
    source_path = Path(str(manifest_row["source_path"]))
    pages: list[dict] = []
    metadata = dict(manifest_row)
    try:
        with open_pdf_from_manifest(source_path, manifest_row) as pdf:
            metadata["page_count"] = pdf.page_count
            for index, page in enumerate(pdf, start=1):
                raw_text = page.get_text("text")
                clean_text = normalize_text(raw_text)
                pages.append(
                    {
                        "doc_id": manifest_row["doc_id"],
                        "page_num": index,
                        "raw_text": raw_text,
                        "clean_text": clean_text,
                        "char_count": len(clean_text),
                    }
                )
        metadata["parse_status"] = "parsed"
        metadata["parsed_pages"] = len(pages)
        metadata["empty_pages"] = sum(1 for page in pages if not page["clean_text"])
    except Exception as exc:  # pragma: no cover - exact fitz exceptions vary by file
        metadata["parse_status"] = "failed"
        metadata["parse_error"] = f"{type(exc).__name__}: {exc}"
    return pages, metadata


def open_pdf_from_manifest(source_path: Path, manifest_row: dict):
    zip_entry = manifest_row.get("zip_entry")
    if zip_entry:
        with zipfile.ZipFile(source_path) as archive:
            entry_name = str(zip_entry)
            try:
                data = archive.read(entry_name)
            except KeyError:
                data = archive.read(entry_name.lstrip("/"))
        return fitz.open(stream=data, filetype="pdf")
    return fitz.open(source_path)


def detect_section_type(line: str) -> str:
    text = normalize_text(line)
    for section_type, pattern in SECTION_PATTERNS:
        if pattern.search(text):
            return section_type
    return ""


def iter_sections(doc: dict, pages: list[dict]) -> Iterator[dict]:
    current_type = "body"
    current_title = "body"
    current_texts: list[str] = []
    current_pages: list[int] = []
    section_index = 0

    def flush() -> dict | None:
        nonlocal section_index
        text = "\n".join(value for value in current_texts if value).strip()
        if not text:
            return None
        row = {
            "doc_id": doc["doc_id"],
            "section_id": f"{doc['doc_id']}__section_{section_index:04d}",
            "section_index": section_index,
            "section_type": current_type,
            "section_title": current_title,
            "page_start": min(current_pages, default=0),
            "page_end": max(current_pages, default=0),
            "text": text,
            "char_count": len(text),
        }
        section_index += 1
        return row

    for page in pages:
        page_num = int(page["page_num"])
        lines = [normalize_text(line) for line in str(page.get("raw_text", "")).splitlines()]
        for line in lines:
            if not line:
                continue
            section_type = detect_section_type(line)
            if section_type and current_texts:
                row = flush()
                if row:
                    yield row
                current_type = section_type
                current_title = line[:180]
                current_texts = [line]
                current_pages = [page_num]
                continue
            if section_type and not current_texts:
                current_type = section_type
                current_title = line[:180]
            current_texts.append(line)
            current_pages.append(page_num)
    row = flush()
    if row:
        yield row


def build_document_row(manifest_row: dict, pages: list[dict], sections: list[dict]) -> dict:
    content = "\n\n".join(section["text"] for section in sections).strip()
    title = first_nonempty_title(manifest_row, sections)
    return {
        "doc_id": manifest_row["doc_id"],
        "source_type": "academic_paper",
        "title": title,
        "content": content,
        "embedding_text": content,
        "metadata": {
            "source_path": manifest_row["source_path"],
            "relative_path": manifest_row["relative_path"],
            "file_type": manifest_row["file_type"],
            "research_field": manifest_row.get("research_field", "unknown"),
            "paper_topic": manifest_row.get("paper_topic", ""),
            "publication_year": manifest_row.get("publication_year", ""),
            "page_count": manifest_row.get("page_count", len(pages)),
            "section_count": len(sections),
            "char_count": len(content),
            "section_types": sorted({section["section_type"] for section in sections}),
        },
    }


def first_nonempty_title(manifest_row: dict, sections: list[dict]) -> str:
    for section in sections:
        for line in section["text"].splitlines():
            line = normalize_text(line)
            if 8 <= len(line) <= 180:
                return line
    return str(manifest_row.get("paper_topic") or manifest_row.get("file_name") or "")


def parse_manifest(
    manifest_jsonl: Path,
    documents_output: Path,
    pages_output: Path,
    sections_output: Path,
    parse_report: Path,
    limit: int | None = None,
) -> dict:
    manifest_rows = [row for row in read_jsonl(manifest_jsonl) if row.get("file_type") == "pdf"]
    if limit is not None:
        manifest_rows = manifest_rows[:limit]

    all_pages: list[dict] = []
    all_sections: list[dict] = []
    documents: list[dict] = []
    parsed_manifest: list[dict] = []

    for row in manifest_rows:
        pages, parsed_row = extract_pdf_rows(row)
        parsed_manifest.append(parsed_row)
        if parsed_row.get("parse_status") != "parsed":
            continue
        sections = list(iter_sections(parsed_row, pages))
        all_pages.extend(pages)
        all_sections.extend(sections)
        documents.append(build_document_row(parsed_row, pages, sections))

    write_jsonl(pages_output, all_pages)
    write_jsonl(sections_output, all_sections)
    write_jsonl(documents_output, documents)

    status_counts = Counter(row.get("parse_status", "unknown") for row in parsed_manifest)
    report = {
        "input_documents": len(manifest_rows),
        "parsed_documents": status_counts.get("parsed", 0),
        "failed_documents": status_counts.get("failed", 0),
        "pages": len(all_pages),
        "sections": len(all_sections),
        "empty_pages": sum(1 for page in all_pages if not page["clean_text"]),
    }
    ensure_parent(parse_report)
    parse_report.write_text(str(report) + "\n", encoding="utf-8")
    return report


@inventory_app.command()
def inventory(
    raw_dir: Path | None = None,
    output_jsonl: Path | None = None,
    limit: int | None = typer.Option(None, min=1),
) -> None:
    """Inventory AIHub academic paper PDF/PPTX files."""
    raw_dir = raw_dir or default_raw_dir()
    output_jsonl = output_jsonl or default_processed_path("academic_manifest.jsonl")
    rows = list(discover_academic_files(raw_dir))
    if limit is not None:
        rows = rows[:limit]
    count = write_jsonl(output_jsonl, rows)
    typer.echo(f"Wrote {count} academic paper manifest rows to {output_jsonl}")


@parse_app.command()
def parse(
    manifest_jsonl: Path | None = None,
    documents_output: Path | None = None,
    pages_output: Path | None = None,
    sections_output: Path | None = None,
    parse_report: Path | None = None,
    limit: int | None = typer.Option(None, min=1),
) -> None:
    """Parse inventoried academic PDFs into normalized document/page/section JSONL."""
    manifest_jsonl = manifest_jsonl or default_processed_path("academic_manifest.jsonl")
    documents_output = documents_output or default_processed_path("documents_normalized.jsonl")
    pages_output = pages_output or default_processed_path("pages.jsonl")
    sections_output = sections_output or default_processed_path("sections.jsonl")
    parse_report = parse_report or default_eval_path("academic_parse_report.txt")
    report = parse_manifest(
        manifest_jsonl,
        documents_output,
        pages_output,
        sections_output,
        parse_report,
        limit,
    )
    typer.echo(f"Parsed {report['parsed_documents']} academic PDFs into {documents_output}")


def inventory_main() -> None:
    inventory_app()


def parse_main() -> None:
    parse_app()
