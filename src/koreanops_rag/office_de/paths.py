from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


DEFAULT_DATA_ROOT = Path(r"C:\vectorsearch-data\ko-unstructured")
DEFAULT_REPO_DQ_REPORT = Path("reports/ko_unstructured_v2/data_quality_report.md")


@dataclass(frozen=True)
class OfficeDePaths:
    data_root: Path = DEFAULT_DATA_ROOT

    @property
    def processed_root(self) -> Path:
        return self.data_root / "processed"

    @property
    def full_processed_root(self) -> Path:
        return self.processed_root / "full"

    @property
    def eval_root(self) -> Path:
        return self.data_root / "eval" / "full"

    @property
    def lake_processed_root(self) -> Path:
        return self.data_root / "lake" / "processed"

    @property
    def lake_mart_root(self) -> Path:
        return self.data_root / "lake" / "mart"

    @property
    def reports_root(self) -> Path:
        return self.data_root / "reports"

    @property
    def manifest_jsonl(self) -> Path:
        return self.processed_root / "office_manifest.jsonl"

    @property
    def documents_jsonl(self) -> Path:
        return self.full_processed_root / "office_documents_normalized.jsonl"

    @property
    def pages_jsonl(self) -> Path:
        return self.full_processed_root / "pdf_pages_raw.jsonl"

    @property
    def blocks_jsonl(self) -> Path:
        return self.full_processed_root / "pdf_blocks_cleaned.jsonl"

    @property
    def chunks_page_jsonl(self) -> Path:
        return self.full_processed_root / "chunks_page.jsonl"

    @property
    def chunks_structure_jsonl(self) -> Path:
        return self.full_processed_root / "chunks_structure.jsonl"

    @property
    def golden_questions_jsonl(self) -> Path:
        return self.eval_root / "golden_questions_reviewed.jsonl"

