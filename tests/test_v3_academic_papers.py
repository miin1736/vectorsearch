from __future__ import annotations

import json
import zipfile
from pathlib import Path

import fitz

from koreanops_rag.io import read_jsonl
from koreanops_rag.v3.academic_papers import (
    detect_section_type,
    discover_academic_files,
    infer_research_field,
    parse_manifest,
)


def _write_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text(
        (72, 72),
        "\n".join(
            [
                "Korean Retrieval Quality Study",
                "Abstract",
                "This paper studies retrieval quality for long documents.",
                "1. Introduction",
                "Chunking strategy matters for long document retrieval.",
                "2. Method",
                "We combine paragraph chunks and section context.",
                "3. Conclusion",
                "The experiment shows hierarchical retrieval can help.",
            ]
        ),
    )
    doc.save(path)
    doc.close()


def test_v3_academic_inventory_discovers_pdf_and_pptx(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    field_dir = raw_dir / "computer_science"
    field_dir.mkdir(parents=True)
    pdf_path = field_dir / "paper_2024.pdf"
    pptx_path = field_dir / "slides_2023.pptx"
    _write_pdf(pdf_path)
    pptx_path.write_bytes(b"pptx")

    rows = list(discover_academic_files(raw_dir))

    assert [row["file_type"] for row in rows] == ["pdf", "pptx"]
    assert rows[0]["research_field"] == "computer_science"
    assert rows[0]["publication_year"] == "2024"
    assert rows[1]["parse_status"] == "unsupported_pptx"


def test_v3_academic_inventory_discovers_pdf_inside_zip(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    zip_path = raw_dir / "3.open" / "Training" / "01.source" / "TS_science.zip"
    pdf_path = tmp_path / "sample.pdf"
    zip_path.parent.mkdir(parents=True)
    _write_pdf(pdf_path)
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.write(pdf_path, "/ST_0001_2025.pdf")
        archive.writestr("/ST_0001_2025.pptx", b"pptx")

    rows = list(discover_academic_files(raw_dir))

    by_type = {row["file_type"]: row for row in rows}
    assert set(by_type) == {"pdf", "pptx"}
    assert by_type["pdf"]["zip_entry"].endswith("ST_0001_2025.pdf")
    assert by_type["pdf"]["source_path"] == str(zip_path)
    assert by_type["pdf"]["publication_year"] == "2025"


def test_v3_academic_section_detection() -> None:
    assert detect_section_type("Abstract") == "abstract"
    assert detect_section_type("1. Introduction") == "introduction"
    assert detect_section_type("2. Methodology") == "method"
    assert detect_section_type("References") == "references"


def test_v3_academic_research_field_infers_aihub_zip_domains() -> None:
    assert infer_research_field(Path("Training/01.source/TS_과학기술(ST).zip/ST_0001.pdf")) == "과학기술"
    assert infer_research_field(Path("Training/01.source/TS_사회과학(SS).zip/SS_0001.pdf")) == "사회과학"
    assert (
        infer_research_field(Path("Training/01.source/TS_인문학,예술체육학(HA).zip/HA_0001.pdf"))
        == "인문학_예술체육학"
    )


def test_v3_academic_parse_manifest_outputs_documents_pages_sections(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw" / "aihub_academic_papers" / "ai"
    raw_dir.mkdir(parents=True)
    pdf_path = raw_dir / "paper_2025.pdf"
    _write_pdf(pdf_path)
    manifest = tmp_path / "processed" / "academic_manifest.jsonl"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        json.dumps(
            {
                "doc_id": "paper_ai_2025",
                "source_path": str(pdf_path),
                "relative_path": "ai/paper_2025.pdf",
                "file_name": "paper_2025.pdf",
                "file_type": "pdf",
                "size_bytes": 1,
                "research_field": "ai",
                "paper_topic": "paper 2025",
                "publication_year": "2025",
                "parse_status": "pending",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    documents_output = tmp_path / "processed" / "documents_normalized.jsonl"
    pages_output = tmp_path / "processed" / "pages.jsonl"
    sections_output = tmp_path / "processed" / "sections.jsonl"
    parse_report = tmp_path / "eval" / "academic_parse_report.txt"

    report = parse_manifest(
        manifest,
        documents_output,
        pages_output,
        sections_output,
        parse_report,
    )

    documents = list(read_jsonl(documents_output))
    pages = list(read_jsonl(pages_output))
    sections = list(read_jsonl(sections_output))
    assert report["parsed_documents"] == 1
    assert documents[0]["source_type"] == "academic_paper"
    assert documents[0]["metadata"]["research_field"] == "ai"
    assert pages[0]["doc_id"] == "paper_ai_2025"
    assert {section["section_type"] for section in sections} >= {"abstract", "introduction"}


def test_v3_academic_parse_manifest_reads_pdf_inside_zip(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    zip_path = raw_dir / "TS_science.zip"
    pdf_path = tmp_path / "sample.pdf"
    raw_dir.mkdir(parents=True)
    _write_pdf(pdf_path)
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.write(pdf_path, "/ST_0001_2025.pdf")

    manifest = tmp_path / "processed" / "academic_manifest.jsonl"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        json.dumps(
            {
                "doc_id": "paper_zip_pdf",
                "source_path": str(zip_path),
                "zip_entry": "/ST_0001_2025.pdf",
                "relative_path": "TS_science/ST_0001_2025.pdf",
                "file_name": "ST_0001_2025.pdf",
                "file_type": "pdf",
                "size_bytes": 1,
                "research_field": "science",
                "paper_topic": "ST 0001 2025",
                "publication_year": "2025",
                "parse_status": "pending",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    report = parse_manifest(
        manifest,
        tmp_path / "processed" / "documents_normalized.jsonl",
        tmp_path / "processed" / "pages.jsonl",
        tmp_path / "processed" / "sections.jsonl",
        tmp_path / "eval" / "academic_parse_report.txt",
    )

    assert report["parsed_documents"] == 1
