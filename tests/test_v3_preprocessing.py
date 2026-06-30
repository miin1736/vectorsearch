from __future__ import annotations

from pathlib import Path

from koreanops_rag.io import read_jsonl, write_jsonl
from koreanops_rag.v3.chunking import iter_fixed_chunks
from koreanops_rag.v3.preprocessing import (
    clean_text,
    noise_score,
    preprocess_documents_and_sections,
    sentence_boundary_break_ratio,
)


class FakeTokenCounter:
    model_name = "fake-tokenizer"

    def ids(self, text: str) -> list[int]:
        return list(range(len(text.split())))

    def count(self, text: str) -> int:
        return len(text.split())

    def decode(self, token_ids: list[int]) -> str:
        return " ".join(f"t{index}" for index in token_ids)

    def decode_with_budget(self, token_ids: list[int], token_budget: int) -> str:
        return self.decode(token_ids[:token_budget])


def test_clean_light_removes_url_doi_and_provider_noise() -> None:
    text = """
    www.earticle.net https://doi.org/10.1000/demo
    Download by IP [Provider: demo]
    This paper explains the retrieval method.
    """

    cleaned, removed = clean_text(text, profile="clean_light")

    assert "http" not in cleaned
    assert "Provider" not in cleaned
    assert removed["url"] >= 1
    assert removed["provider"] >= 1


def test_clean_structural_removes_references_and_table_markers() -> None:
    text = """
    Main result sentence.
    Table 1: noisy table marker
    References
    [1] Noisy citation entry.
    """

    cleaned, removed = clean_text(text, profile="clean_structural")

    assert "Main result sentence." in cleaned
    assert "References" not in cleaned
    assert "Noisy citation" not in cleaned
    assert removed["reference_heading"] >= 1


def test_embedding_optimized_reduces_noise_and_line_breaks() -> None:
    raw = "short\nThis is a broken academic sentence without ending\n[12] noisy citation\n"

    cleaned, _ = clean_text(raw, profile="clean_embedding_optimized")

    assert "short" not in cleaned
    assert "[12]" not in cleaned
    assert noise_score(cleaned) <= noise_score(raw)
    assert sentence_boundary_break_ratio(cleaned) <= sentence_boundary_break_ratio(raw)


def test_preprocess_documents_and_sections_writes_metadata(tmp_path: Path) -> None:
    docs = tmp_path / "docs.jsonl"
    sections = tmp_path / "sections.jsonl"
    pages = tmp_path / "pages.jsonl"
    write_jsonl(
        docs,
        [
            {
                "doc_id": "paper_1",
                "source_type": "academic_paper",
                "title": "Paper",
                "content": "www.earticle.net\nThis paper studies retrieval.",
                "metadata": {"research_field": "ai"},
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
                "section_type": "method",
                "section_title": "Method",
                "page_start": 1,
                "page_end": 1,
                "text": "www.earticle.net\nThis method uses dense retrieval.",
            }
        ],
    )
    write_jsonl(pages, [{"doc_id": "paper_1", "page_num": 1, "clean_text": "www.earticle.net"}])

    outputs = preprocess_documents_and_sections(
        docs,
        sections,
        tmp_path / "out",
        profile="clean_embedding_optimized",
        pages_jsonl=pages,
    )
    row = next(read_jsonl(outputs["documents"]))
    section = next(read_jsonl(outputs["sections"]))

    assert row["metadata"]["cleaning_profile"] == "clean_embedding_optimized"
    assert row["metadata"]["raw_content_hash"]
    assert "www.earticle.net" not in row["embedding_text"]
    assert section["raw_text"]
    assert outputs["report"].exists()


def test_chunking_prefers_embedding_text(tmp_path: Path) -> None:
    docs = tmp_path / "docs.jsonl"
    write_jsonl(
        docs,
        [
            {
                "doc_id": "paper_1",
                "source_type": "academic_paper",
                "title": "Paper",
                "content": "raw raw raw raw raw raw",
                "embedding_text": "clean clean clean clean clean clean",
                "metadata": {},
            }
        ],
    )

    chunks = list(
        iter_fixed_chunks(
            docs,
            FakeTokenCounter(),  # type: ignore[arg-type]
            strategy="tokenizer_fixed",
            token_budget=3,
            overlap=0,
        )
    )

    assert chunks[0]["content"].startswith("t0")
    assert "raw" not in chunks[0]["content"]
