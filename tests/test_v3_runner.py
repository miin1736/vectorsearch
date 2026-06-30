from __future__ import annotations

import json
from pathlib import Path

from koreanops_rag.v3.runner import build_execution_plan, write_execution_plan
from koreanops_rag.v3.test_cases import DEFAULT_REGISTRY, load_registry


def test_v3_runner_builds_parent_child_execution_plan() -> None:
    registry = load_registry(DEFAULT_REGISTRY)
    case = registry.find_case("parent_child_child_search_section_context")

    plan = build_execution_plan(registry, case, DEFAULT_REGISTRY)

    assert plan.case_id == case.case_id
    assert plan.qdrant_collection == "ko_dense_technical_v3_parent_child"
    assert plan.opensearch_index == "ko_dense_technical_v3_parent_child"
    assert [step.step_id for step in plan.steps] == [
        "01_chunking",
        "02_indexing",
        "03_retrieval",
        "04_reranking",
        "05_evaluation",
    ]
    assert plan.steps[0].implementation == "child_passage_parent_section"
    assert plan.steps[2].implementation == "dense_child_parent_context"
    assert plan.steps[3].implementation == "parent_score_aggregation"
    assert plan.steps[4].implementation == "context_efficiency_metrics"


def test_v3_runner_skips_audit_retrieval_and_reranking() -> None:
    registry = load_registry(DEFAULT_REGISTRY)
    case = registry.find_case("truncation_audit_e5")

    plan = build_execution_plan(registry, case, DEFAULT_REGISTRY)

    statuses = {step.step_id: step.status for step in plan.steps}
    assert statuses["03_retrieval"] == "skipped"
    assert statuses["04_reranking"] == "skipped"
    assert plan.steps[4].implementation == "token_length_distribution"


def test_v3_runner_writes_execution_plan_json(tmp_path: Path) -> None:
    registry = load_registry(DEFAULT_REGISTRY)
    registry.data_root = tmp_path
    case = registry.find_case("baseline_fixed_512")
    output = tmp_path / "plan.json"

    write_execution_plan(output, build_execution_plan(registry, case, DEFAULT_REGISTRY))

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["case_id"] == "baseline_fixed_512"
    assert payload["steps"][0]["parameters"]["token_budget"] == 512


def test_v3_runner_builds_topic_keyword_execution_plan() -> None:
    registry = load_registry(DEFAULT_REGISTRY)
    case = registry.find_case("topic_keyword_soft_boost")

    plan = build_execution_plan(registry, case, DEFAULT_REGISTRY)

    assert plan.index_namespace == "ko_dense_technical_v3_topic_keyword_soft_boost"
    assert plan.steps[2].profile_name == "topic_keyword_soft_boost"
    assert plan.steps[2].parameters["fields"] == [
        "research_field",
        "paper_topic",
        "keyword",
        "publication_year",
    ]
