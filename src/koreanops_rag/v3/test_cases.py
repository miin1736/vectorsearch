from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import typer
import yaml
from pydantic import BaseModel, Field, model_validator

from koreanops_rag.io import ensure_parent

DEFAULT_REGISTRY = Path("experiments/ko_dense_technical_v3/test_cases.yaml")
REQUIRED_SUMMARY_FIELDS = [
    "case_id",
    "stage",
    "group",
    "technique",
    "enabled",
    "summary_exists",
    "details_exists",
    "recall_at_10",
    "mrr",
    "ndcg_at_10",
    "p50_latency_ms",
    "p95_latency_ms",
]

app = typer.Typer(add_completion=False)


class TestCase(BaseModel):
    __test__ = False

    case_id: str
    stage: str
    group: str
    technique: str
    enabled: bool = True
    reason: str = ""
    index_namespace: str
    chunking_profile: str
    retriever_profile: str
    reranker_profile: str
    evaluation_profile: str
    expected_artifacts: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_disabled_reason(self) -> "TestCase":
        if not self.enabled and not self.reason:
            raise ValueError(f"{self.case_id} is disabled but has no reason")
        return self


class TestCaseRegistry(BaseModel):
    __test__ = False

    project_id: str
    data_root: Path
    namespace_prefix: str
    default_golden_set_version: str
    case_groups: list[str]
    test_cases: list[TestCase]

    @model_validator(mode="after")
    def validate_registry(self) -> "TestCaseRegistry":
        seen: set[str] = set()
        for case in self.test_cases:
            if case.case_id in seen:
                raise ValueError(f"Duplicate case_id: {case.case_id}")
            seen.add(case.case_id)
            if case.group not in self.case_groups:
                raise ValueError(f"{case.case_id} uses unknown group {case.group}")
            if not case.index_namespace.startswith(self.namespace_prefix):
                raise ValueError(
                    f"{case.case_id} index_namespace must start with {self.namespace_prefix}"
                )
        return self

    def enabled_cases(self) -> list[TestCase]:
        return [case for case in self.test_cases if case.enabled]

    def find_case(self, case_id: str) -> TestCase:
        for case in self.test_cases:
            if case.case_id == case_id:
                return case
        raise KeyError(case_id)


@dataclass(frozen=True)
class CasePaths:
    summary_csv: Path
    details_jsonl: Path
    run_manifest_json: Path


def load_registry(path: Path = DEFAULT_REGISTRY) -> TestCaseRegistry:
    with path.open("r", encoding="utf-8") as file:
        raw = yaml.safe_load(file) or {}
    return TestCaseRegistry.model_validate(raw)


def registry_hash(path: Path = DEFAULT_REGISTRY) -> str:
    data = path.read_bytes()
    return hashlib.sha256(data).hexdigest()[:12]


def case_paths(registry: TestCaseRegistry, case: TestCase) -> CasePaths:
    case_dir = registry.data_root / "eval" / "cases"
    return CasePaths(
        summary_csv=case_dir / f"{case.case_id}_summary.csv",
        details_jsonl=case_dir / f"{case.case_id}_details.jsonl",
        run_manifest_json=case_dir / f"{case.case_id}_run_manifest.json",
    )


def build_case_manifest(
    registry: TestCaseRegistry,
    case: TestCase,
    registry_path: Path,
) -> dict[str, Any]:
    paths = case_paths(registry, case)
    return {
        "project_id": registry.project_id,
        "case_id": case.case_id,
        "stage": case.stage,
        "group": case.group,
        "enabled": case.enabled,
        "technique": case.technique,
        "data_root": str(registry.data_root),
        "namespace_prefix": registry.namespace_prefix,
        "index_namespace": case.index_namespace,
        "qdrant_collection": case.index_namespace,
        "opensearch_index": case.index_namespace,
        "chunking_profile": case.chunking_profile,
        "retriever_profile": case.retriever_profile,
        "reranker_profile": case.reranker_profile,
        "evaluation_profile": case.evaluation_profile,
        "golden_set_version": registry.default_golden_set_version,
        "registry_path": str(registry_path),
        "registry_hash": registry_hash(registry_path),
        "expected_artifacts": [
            str((registry.data_root / artifact).resolve())
            for artifact in case.expected_artifacts
        ],
        "summary_csv": str(paths.summary_csv.resolve()),
        "details_jsonl": str(paths.details_jsonl.resolve()),
    }


def _read_overall_summary(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8", newline="") as file:
        rows = list(csv.DictReader(file))
    if not rows:
        return {}
    for row in rows:
        if row.get("group") == "overall":
            return row
    return rows[0]


def summarize_registry(registry: TestCaseRegistry) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for case in registry.test_cases:
        paths = case_paths(registry, case)
        summary = _read_overall_summary(paths.summary_csv)
        row = {
            "case_id": case.case_id,
            "stage": case.stage,
            "group": case.group,
            "technique": case.technique,
            "enabled": str(case.enabled).lower(),
            "summary_exists": str(paths.summary_csv.exists()).lower(),
            "details_exists": str(paths.details_jsonl.exists()).lower(),
            "recall_at_10": summary.get("recall_at_10", ""),
            "mrr": summary.get("mrr", ""),
            "ndcg_at_10": summary.get("ndcg_at_10", ""),
            "p50_latency_ms": summary.get("p50_latency_ms", ""),
            "p95_latency_ms": summary.get("p95_latency_ms", ""),
        }
        rows.append(row)
    return rows


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    ensure_parent(path)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


@app.command("list")
def list_cases(
    registry_path: Path = typer.Option(DEFAULT_REGISTRY, "--registry"),
    enabled_only: bool = typer.Option(False, "--enabled-only"),
) -> None:
    """List V3 test cases from the registry."""
    registry = load_registry(registry_path)
    cases = registry.enabled_cases() if enabled_only else registry.test_cases
    for case in cases:
        status = "enabled" if case.enabled else "disabled"
        typer.echo(
            f"{case.case_id}\t{status}\t{case.stage}\t{case.group}\t"
            f"{case.technique}\t{case.index_namespace}"
        )


@app.command("manifest")
def write_manifest(
    case_id: str,
    output_json: Path | None = typer.Option(None, "--output"),
    registry_path: Path = typer.Option(DEFAULT_REGISTRY, "--registry"),
) -> None:
    """Write the execution manifest for one V3 case."""
    registry = load_registry(registry_path)
    case = registry.find_case(case_id)
    manifest = build_case_manifest(registry, case, registry_path)
    output = output_json or case_paths(registry, case).run_manifest_json
    ensure_parent(output)
    output.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    typer.echo(f"Wrote V3 case manifest for {case_id} to {output}")


@app.command("summarize")
def summarize_cases(
    output_csv: Path | None = typer.Option(None, "--output"),
    registry_path: Path = typer.Option(DEFAULT_REGISTRY, "--registry"),
) -> None:
    """Summarize V3 case result files into one matrix CSV."""
    registry = load_registry(registry_path)
    rows = summarize_registry(registry)
    output = output_csv or registry.data_root / "eval" / "case_matrix_summary.csv"
    write_csv(output, rows, REQUIRED_SUMMARY_FIELDS)
    typer.echo(f"Wrote {len(rows)} V3 case summary rows to {output}")


@app.command("validate")
def validate_cases(
    registry_path: Path = typer.Option(DEFAULT_REGISTRY, "--registry"),
) -> None:
    """Validate registry schema, ids, groups, and namespace isolation."""
    registry = load_registry(registry_path)
    enabled = len(registry.enabled_cases())
    disabled = len(registry.test_cases) - enabled
    typer.echo(
        f"Validated {len(registry.test_cases)} V3 test cases "
        f"({enabled} enabled, {disabled} disabled)"
    )


def main() -> None:
    app()
