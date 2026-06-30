from __future__ import annotations

from pathlib import Path

from koreanops_rag.io import read_jsonl, write_jsonl
from koreanops_rag.v3.reconstruction import (
    build_preserved_inventory,
    build_reconstructed_documents_and_sections,
    detect_case_type,
    reconstruct_text,
)


def test_reconstruction_preserves_table_and_caption_lines() -> None:
    raw = """
    www.earticle.net
    Table 1: Accuracy by model
    Source: author calculation
    본 연구는 검색 성능을 비교한다
    """

    reconstructed = reconstruct_text(raw, profile="reconstruct_fielded")

    assert "www.earticle.net" not in reconstructed["embedding_text"]
    assert "Table 1" in reconstructed["bm25_text"]
    assert "Source:" in reconstructed["bm25_text"]
    assert any(item["case_type"] == "table" for item in reconstructed["preserved_elements"])
    assert any(item["case_type"] == "caption" for item in reconstructed["preserved_elements"])
    assert reconstructed["alignment_map"]


def test_reconstruction_packs_broken_korean_lines() -> None:
    raw = "본 연구의 목적은 교육 현장에서 현지조사를 어떻게 인식하고, 이를 교육에 어\n떻게 통합할 수 있는지 파악하는 것이다."

    reconstructed = reconstruct_text(raw, profile="reconstruct_packed")

    assert "어\n떻게" not in reconstructed["embedding_text"]
    assert "어떻게" in reconstructed["embedding_text"] or "어떻게" in reconstructed["embedding_text"].replace(" ", "")


def test_detect_case_type_keeps_information_anchors() -> None:
    assert detect_case_type("Table 2: Results") == "table"
    assert detect_case_type("Figure 1. Model architecture") == "figure"
    assert detect_case_type("References") == "reference"


def test_build_reconstructed_documents_and_sections_writes_fields(tmp_path: Path) -> None:
    docs = tmp_path / "docs.jsonl"
    sections = tmp_path / "sections.jsonl"
    write_jsonl(
        docs,
        [
            {
                "doc_id": "paper_1",
                "source_type": "academic_paper",
                "title": "Paper",
                "content": "www.earticle.net\nTable 1: Result\n본문 문장이다.",
                "metadata": {},
            }
        ],
    )
    write_jsonl(
        sections,
        [
            {
                "doc_id": "paper_1",
                "section_id": "s1",
                "section_index": 1,
                "section_type": "result",
                "text": "Table 1: Result\n본문 문장이다.",
            }
        ],
    )

    outputs = build_reconstructed_documents_and_sections(
        docs,
        sections,
        tmp_path / "out",
        profile="reconstruct_fielded",
    )
    row = next(read_jsonl(outputs["documents"]))

    assert row["bm25_text"]
    assert row["embedding_text"]
    assert row["display_text"]
    assert row["preserved_elements"]
    assert row["metadata"]["reconstruction_profile"] == "reconstruct_fielded"


def test_build_preserved_inventory_writes_cases(tmp_path: Path) -> None:
    sections = tmp_path / "sections.jsonl"
    output = tmp_path / "inventory.csv"
    write_jsonl(
        sections,
        [
            {
                "doc_id": "paper_1",
                "section_id": "s1",
                "section_type": "result",
                "page_start": 1,
                "page_end": 1,
                "text": "Table 1: Result\n본문 문장이다.",
            }
        ],
    )

    rows = build_preserved_inventory(sections, output)

    assert rows
    assert rows[0]["case_type"] == "table"
    assert output.exists()
