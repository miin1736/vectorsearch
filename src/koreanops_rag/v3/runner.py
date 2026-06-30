from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import typer
from pydantic import BaseModel, Field

from koreanops_rag.io import ensure_parent
from koreanops_rag.v3.profiles import ExperimentProfile, get_profile
from koreanops_rag.v3.test_cases import (
    DEFAULT_REGISTRY,
    TestCase,
    TestCaseRegistry,
    build_case_manifest,
    case_paths,
    load_registry,
)

app = typer.Typer(add_completion=False)


class RunnerStep(BaseModel):
    step_id: str
    kind: str
    profile_name: str
    implementation: str
    inputs: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)
    parameters: dict[str, Any] = Field(default_factory=dict)
    status: str = "planned"


class CaseExecutionPlan(BaseModel):
    project_id: str
    case_id: str
    enabled: bool
    stage: str
    index_namespace: str
    qdrant_collection: str
    opensearch_index: str
    data_root: str
    manifest: dict[str, Any]
    steps: list[RunnerStep]


def _profile_step(
    step_id: str,
    profile: ExperimentProfile,
    *,
    inputs: list[Path | str] | None = None,
    outputs: list[Path | str] | None = None,
) -> RunnerStep:
    return RunnerStep(
        step_id=step_id,
        kind=profile.kind,
        profile_name=profile.name,
        implementation=profile.implementation,
        inputs=[str(value) for value in inputs or []],
        outputs=[str(value) for value in outputs or []],
        parameters=profile.parameters,
    )


def _stringify_paths(values: list[Path | str]) -> list[str]:
    return [str(value) for value in values]


def _case_artifact_path(registry: TestCaseRegistry, artifact: str) -> Path:
    return registry.data_root / artifact


def build_execution_plan(
    registry: TestCaseRegistry,
    case: TestCase,
    registry_path: Path = DEFAULT_REGISTRY,
) -> CaseExecutionPlan:
    paths = case_paths(registry, case)
    manifest = build_case_manifest(registry, case, registry_path)
    chunking = get_profile("chunking", case.chunking_profile)
    retriever = get_profile("retriever", case.retriever_profile)
    reranker = get_profile("reranker", case.reranker_profile)
    evaluation = get_profile("evaluation", case.evaluation_profile)

    chunk_outputs = [
        _case_artifact_path(registry, artifact)
        for artifact in case.expected_artifacts
        if artifact.startswith("processed/")
    ]
    graph_outputs = [
        _case_artifact_path(registry, artifact)
        for artifact in case.expected_artifacts
        if artifact.startswith("processed/graphs/")
    ]

    steps = [
        _profile_step(
            "01_chunking",
            chunking,
            inputs=[registry.data_root / "processed" / "documents_normalized.jsonl"],
            outputs=chunk_outputs or graph_outputs,
        ),
        RunnerStep(
            step_id="02_indexing",
            kind="indexing",
            profile_name=case.index_namespace,
            implementation="qdrant_and_opensearch_indexing",
            inputs=_stringify_paths(chunk_outputs or graph_outputs),
            outputs=[case.index_namespace],
            parameters={
                "qdrant_collection": case.index_namespace,
                "opensearch_index": case.index_namespace,
            },
        ),
        _profile_step(
            "03_retrieval",
            retriever,
            inputs=[
                registry.data_root / "eval" / "golden_questions.jsonl",
                case.index_namespace,
            ],
            outputs=[paths.details_jsonl],
        ),
        _profile_step(
            "04_reranking",
            reranker,
            inputs=[paths.details_jsonl],
            outputs=[paths.details_jsonl],
        ),
        _profile_step(
            "05_evaluation",
            evaluation,
            inputs=[paths.details_jsonl],
            outputs=[paths.summary_csv],
        ),
    ]

    if chunking.implementation in {"no_chunking", "selected_smoke_winner", "selected_pilot_winner"}:
        steps[0].status = "skipped"
    if retriever.implementation == "no_retrieval":
        steps[2].status = "skipped"
    if reranker.implementation == "no_reranker":
        steps[3].status = "skipped"
    if evaluation.implementation == "not_scheduled":
        steps[4].status = "skipped"

    return CaseExecutionPlan(
        project_id=registry.project_id,
        case_id=case.case_id,
        enabled=case.enabled,
        stage=case.stage,
        index_namespace=case.index_namespace,
        qdrant_collection=case.index_namespace,
        opensearch_index=case.index_namespace,
        data_root=str(registry.data_root),
        manifest=manifest,
        steps=steps,
    )


def write_execution_plan(path: Path, plan: CaseExecutionPlan) -> None:
    ensure_parent(path)
    path.write_text(
        json.dumps(plan.model_dump(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


@app.command("plan")
def plan_case(
    case_id: str,
    output_json: Path | None = typer.Option(None, "--output"),
    registry_path: Path = typer.Option(DEFAULT_REGISTRY, "--registry"),
) -> None:
    """Resolve one V3 case into an execution plan without running heavy work."""
    registry = load_registry(registry_path)
    case = registry.find_case(case_id)
    plan = build_execution_plan(registry, case, registry_path)
    output = output_json or case_paths(registry, case).run_manifest_json
    write_execution_plan(output, plan)
    typer.echo(f"Wrote V3 execution plan for {case_id} to {output}")


@app.command("plan-all")
def plan_all_cases(
    enabled_only: bool = typer.Option(True, "--enabled-only/--all"),
    output_dir: Path | None = typer.Option(None, "--output-dir"),
    registry_path: Path = typer.Option(DEFAULT_REGISTRY, "--registry"),
) -> None:
    """Resolve V3 cases into execution plans without running heavy work."""
    registry = load_registry(registry_path)
    cases = registry.enabled_cases() if enabled_only else registry.test_cases
    target_dir = output_dir or registry.data_root / "eval" / "cases"
    for case in cases:
        plan = build_execution_plan(registry, case, registry_path)
        write_execution_plan(target_dir / f"{case.case_id}_execution_plan.json", plan)
    typer.echo(f"Wrote {len(cases)} V3 execution plans to {target_dir}")


def main() -> None:
    app()
