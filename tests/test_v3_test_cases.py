from __future__ import annotations

import csv
from pathlib import Path

import pytest

from koreanops_rag.v3.test_cases import (
    DEFAULT_REGISTRY,
    REQUIRED_SUMMARY_FIELDS,
    TestCaseRegistry,
    build_case_manifest,
    load_registry,
    summarize_registry,
    write_csv,
)


def test_v3_registry_loads_and_uses_isolated_namespace() -> None:
    registry = load_registry(DEFAULT_REGISTRY)

    assert registry.project_id == "ko_dense_technical_v3"
    assert len(registry.test_cases) >= 20
    assert all(
        case.index_namespace.startswith("ko_dense_technical_v3_")
        for case in registry.test_cases
    )
    assert {case.group for case in registry.test_cases}.issubset(set(registry.case_groups))


def test_v3_registry_rejects_duplicate_case_ids() -> None:
    raw = {
        "project_id": "ko_dense_technical_v3",
        "data_root": r"C:\vectorsearch-data\ko-dense-technical",
        "namespace_prefix": "ko_dense_technical_v3_",
        "default_golden_set_version": "test",
        "case_groups": ["baseline"],
        "test_cases": [
            {
                "case_id": "same",
                "stage": "smoke",
                "group": "baseline",
                "technique": "a",
                "index_namespace": "ko_dense_technical_v3_a",
                "chunking_profile": "a",
                "retriever_profile": "a",
                "reranker_profile": "none",
                "evaluation_profile": "a",
            },
            {
                "case_id": "same",
                "stage": "smoke",
                "group": "baseline",
                "technique": "b",
                "index_namespace": "ko_dense_technical_v3_b",
                "chunking_profile": "b",
                "retriever_profile": "b",
                "reranker_profile": "none",
                "evaluation_profile": "b",
            },
        ],
    }

    with pytest.raises(ValueError, match="Duplicate case_id"):
        TestCaseRegistry.model_validate(raw)


def test_v3_case_manifest_maps_one_namespace_to_qdrant_and_opensearch() -> None:
    registry = load_registry(DEFAULT_REGISTRY)
    case = registry.find_case("parent_child_child_search_section_context")

    manifest = build_case_manifest(registry, case, DEFAULT_REGISTRY)

    assert manifest["case_id"] == case.case_id
    assert manifest["qdrant_collection"] == case.index_namespace
    assert manifest["opensearch_index"] == case.index_namespace
    assert manifest["registry_hash"]
    assert manifest["golden_set_version"] == registry.default_golden_set_version


def test_v3_summarize_registry_reads_existing_case_summary(tmp_path: Path) -> None:
    registry = load_registry(DEFAULT_REGISTRY)
    registry.data_root = tmp_path
    summary_path = tmp_path / "eval" / "cases" / "baseline_fixed_512_summary.csv"
    write_csv(
        summary_path,
        [
            {
                "method": "vector",
                "group": "overall",
                "recall_at_10": "0.75",
                "mrr": "0.50",
                "ndcg_at_10": "0.60",
                "p50_latency_ms": "12.0",
                "p95_latency_ms": "40.0",
            }
        ],
        [
            "method",
            "group",
            "recall_at_10",
            "mrr",
            "ndcg_at_10",
            "p50_latency_ms",
            "p95_latency_ms",
        ],
    )

    rows = summarize_registry(registry)
    baseline = next(row for row in rows if row["case_id"] == "baseline_fixed_512")

    assert baseline["summary_exists"] == "true"
    assert baseline["recall_at_10"] == "0.75"
    assert list(baseline) == REQUIRED_SUMMARY_FIELDS


def test_v3_write_csv_creates_matrix(tmp_path: Path) -> None:
    output = tmp_path / "matrix.csv"
    write_csv(
        output,
        [{"case_id": "case_a", "stage": "smoke"}],
        ["case_id", "stage"],
    )

    with output.open("r", encoding="utf-8", newline="") as file:
        rows = list(csv.DictReader(file))
    assert rows == [{"case_id": "case_a", "stage": "smoke"}]
