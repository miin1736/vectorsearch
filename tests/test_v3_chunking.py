from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from koreanops_rag.io import read_jsonl, write_jsonl
from koreanops_rag.v3.chunking import (
    audit_token_lengths,
    iter_fixed_chunks,
    iter_passage_chunks,
    iter_page_subchunks,
    iter_sentence_chunks,
    iter_section_chunks,
    merge_text_units,
    token_windows,
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


def _write_inputs(tmp_path: Path) -> dict[str, Path]:
    docs = tmp_path / "documents.jsonl"
    pages = tmp_path / "pages.jsonl"
    sections = tmp_path / "sections.jsonl"
    write_jsonl(
        docs,
        [
            {
                "doc_id": "paper_1",
                "source_type": "academic_paper",
                "title": "Paper 1",
                "content": " ".join(f"w{i}" for i in range(14)),
                "metadata": {"research_field": "science"},
            }
        ],
    )
    write_jsonl(
        pages,
        [
            {
                "doc_id": "paper_1",
                "page_num": 1,
                "clean_text": " ".join(f"p{i}" for i in range(8)),
            }
        ],
    )
    write_jsonl(
        sections,
        [
            {
                "doc_id": "paper_1",
                "section_id": "paper_1__section_0000",
                "section_index": 0,
                "section_type": "method",
                "section_title": "2. Method",
                "page_start": 1,
                "page_end": 1,
                "text": " ".join(f"s{i}" for i in range(9))
                + ". "
                + " ".join(f"t{i}" for i in range(9))
                + ".",
            }
        ],
    )
    return {"docs": docs, "pages": pages, "sections": sections}


def test_v3_token_windows_uses_overlap() -> None:
    windows = list(token_windows("a b c d e f", FakeTokenCounter(), 4, 1))

    assert [(start, end) for _, start, end in windows] == [(0, 4), (3, 6)]


def test_v3_fixed_chunks_preserve_parent_metadata(tmp_path: Path) -> None:
    paths = _write_inputs(tmp_path)

    chunks = list(
        iter_fixed_chunks(
            paths["docs"],
            FakeTokenCounter(),  # type: ignore[arg-type]
            strategy="tokenizer_fixed",
            token_budget=5,
            overlap=1,
        )
    )

    assert len(chunks) == 4
    assert chunks[0]["metadata"]["parent_doc_id"] == "paper_1"
    assert chunks[0]["metadata"]["chunking_strategy"] == "tokenizer_fixed"
    assert chunks[0]["metadata"]["token_count"] <= 5


def test_v3_page_and_section_chunks_keep_locations(tmp_path: Path) -> None:
    paths = _write_inputs(tmp_path)

    page_chunks = list(
        iter_page_subchunks(
            paths["docs"],
            paths["pages"],
            FakeTokenCounter(),  # type: ignore[arg-type]
            token_budget=5,
            overlap=1,
        )
    )
    section_chunks = list(
        iter_section_chunks(
            paths["docs"],
            paths["sections"],
            FakeTokenCounter(),  # type: ignore[arg-type]
            token_budget=5,
            overlap=1,
        )
    )

    assert page_chunks[0]["metadata"]["page_start"] == 1
    assert section_chunks[0]["metadata"]["section_type"] == "method"
    assert section_chunks[0]["metadata"]["section_title"] == "2. Method"


def test_v3_sentence_and_passage_chunks_keep_section_metadata(tmp_path: Path) -> None:
    paths = _write_inputs(tmp_path)

    sentence_chunks = list(
        iter_sentence_chunks(
            paths["docs"],
            paths["sections"],
            FakeTokenCounter(),  # type: ignore[arg-type]
            token_budget=12,
            min_tokens=4,
            overlap_units=0,
        )
    )
    passage_chunks = list(
        iter_passage_chunks(
            paths["docs"],
            paths["sections"],
            FakeTokenCounter(),  # type: ignore[arg-type]
            token_budget=12,
            min_tokens=4,
            overlap_units=0,
        )
    )

    assert sentence_chunks[0]["metadata"]["chunking_strategy"] == "sentence"
    assert sentence_chunks[0]["metadata"]["section_type"] == "method"
    assert passage_chunks[0]["metadata"]["chunking_strategy"] == "passage"
    assert passage_chunks[0]["metadata"]["parent_doc_id"] == "paper_1"


def test_v3_merge_text_units_splits_oversized_unit() -> None:
    chunks = list(
        merge_text_units(
            [" ".join(f"w{i}" for i in range(12))],
            FakeTokenCounter(),  # type: ignore[arg-type]
            token_budget=5,
            min_tokens=4,
        )
    )

    assert len(chunks) == 3
    assert all(token_count <= 5 for _, _, _, token_count in chunks)


def test_v3_audit_token_lengths_writes_summary(tmp_path: Path) -> None:
    paths = _write_inputs(tmp_path)
    output = tmp_path / "audit.csv"

    rows = audit_token_lengths(
        paths["docs"],
        paths["pages"],
        paths["sections"],
        FakeTokenCounter(),  # type: ignore[arg-type]
        output,
        max_length=5,
    )

    assert [row["unit"] for row in rows] == ["document", "page", "section"]
    assert rows[0]["over_max_count"] == 1
    with output.open("r", encoding="utf-8", newline="") as file:
        csv_rows: list[dict[str, Any]] = list(csv.DictReader(file))
    assert csv_rows[0]["unit"] == "document"
    assert list(read_jsonl(paths["docs"]))[0]["doc_id"] == "paper_1"
