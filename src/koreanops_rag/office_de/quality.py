from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import typer

from koreanops_rag.io import ensure_parent, read_jsonl
from koreanops_rag.office_de.paths import DEFAULT_REPO_DQ_REPORT, OfficeDePaths

app = typer.Typer(add_completion=False)


@dataclass(frozen=True)
class CheckResult:
    name: str
    status: str
    observed: str
    expected: str
    details: str = ""


def count_jsonl(path: Path) -> int:
    if not path.exists():
        return -1
    with path.open("r", encoding="utf-8") as file:
        return sum(1 for line in file if line.strip())


def _metadata(row: dict[str, Any]) -> dict[str, Any]:
    metadata = row.get("metadata")
    return metadata if isinstance(metadata, dict) else {}


def _load_document_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    return {str(row.get("doc_id", "")) for row in read_jsonl(path)}


def _chunk_checks(
    chunk_path: Path,
    document_ids: set[str],
    strategy: str,
) -> list[CheckResult]:
    seen: set[str] = set()
    duplicates = 0
    missing_parent = 0
    invalid_pages = 0
    rows = 0
    if not chunk_path.exists():
        return [
            CheckResult(
                f"{strategy} chunk file exists",
                "WARN",
                "missing",
                str(chunk_path),
            )
        ]
    for row in read_jsonl(chunk_path):
        rows += 1
        chunk_id = str(row.get("chunk_uid") or row.get("doc_id") or "")
        if chunk_id in seen:
            duplicates += 1
        seen.add(chunk_id)
        metadata = _metadata(row)
        parent = str(metadata.get("parent_doc_id") or "")
        if parent not in document_ids:
            missing_parent += 1
        page_start = int(metadata.get("page_start") or 0)
        page_end = int(metadata.get("page_end") or 0)
        if page_start > page_end:
            invalid_pages += 1
    return [
        CheckResult(
            f"{strategy} duplicate chunk ids",
            "PASS" if duplicates == 0 else "FAIL",
            str(duplicates),
            "0",
            f"rows={rows}",
        ),
        CheckResult(
            f"{strategy} chunk parent_doc_id exists",
            "PASS" if missing_parent == 0 else "FAIL",
            str(missing_parent),
            "0",
            f"rows={rows}",
        ),
        CheckResult(
            f"{strategy} page_start <= page_end",
            "PASS" if invalid_pages == 0 else "FAIL",
            str(invalid_pages),
            "0",
            f"rows={rows}",
        ),
    ]


def _qdrant_points(url: str, collection: str) -> int | None:
    try:
        response = httpx.get(f"{url.rstrip('/')}/collections/{collection}", timeout=5.0)
        response.raise_for_status()
        return int(response.json()["result"]["points_count"])
    except Exception:
        return None


def _opensearch_count(url: str, index: str) -> int | None:
    try:
        response = httpx.get(f"{url.rstrip('/')}/{index}/_count", timeout=5.0)
        response.raise_for_status()
        return int(response.json()["count"])
    except Exception:
        return None


def run_quality_checks(
    paths: OfficeDePaths,
    *,
    qdrant_url: str = "http://localhost:6333",
    opensearch_url: str = "http://localhost:9200",
    check_live_indexes: bool = True,
) -> list[CheckResult]:
    manifest_count = count_jsonl(paths.manifest_jsonl)
    document_count = count_jsonl(paths.documents_jsonl)
    results = [
        CheckResult(
            "manifest count equals normalized documents count",
            "PASS" if manifest_count == document_count and manifest_count >= 0 else "FAIL",
            str(document_count),
            str(manifest_count),
        )
    ]
    empty_documents = 0
    if paths.documents_jsonl.exists():
        for row in read_jsonl(paths.documents_jsonl):
            if not str(row.get("content") or "").strip():
                empty_documents += 1
    results.append(
        CheckResult(
            "empty content document count",
            "WARN" if empty_documents else "PASS",
            str(empty_documents),
            "0",
        )
    )

    document_ids = _load_document_ids(paths.documents_jsonl)
    chunk_inputs = {
        "page": paths.chunks_page_jsonl,
        "structure": paths.chunks_structure_jsonl,
    }
    for strategy, chunk_path in chunk_inputs.items():
        results.extend(_chunk_checks(chunk_path, document_ids, strategy))

    if check_live_indexes:
        live_targets = {
            "page": ("ko_unstructured_pdf_page", paths.chunks_page_jsonl),
            "structure": ("ko_unstructured_pdf_structure", paths.chunks_structure_jsonl),
        }
        for strategy, (target, chunk_path) in live_targets.items():
            input_count = count_jsonl(chunk_path)
            points = _qdrant_points(qdrant_url, target)
            results.append(
                CheckResult(
                    f"Qdrant {strategy} points_count equals chunk input count",
                    "WARN"
                    if points is None
                    else "PASS"
                    if points == input_count
                    else "FAIL",
                    "unavailable" if points is None else str(points),
                    str(input_count),
                )
            )
            docs = _opensearch_count(opensearch_url, target)
            results.append(
                CheckResult(
                    f"OpenSearch {strategy} _count equals chunk input count",
                    "WARN"
                    if docs is None
                    else "PASS"
                    if docs == input_count
                    else "FAIL",
                    "unavailable" if docs is None else str(docs),
                    str(input_count),
                )
            )
    return results


def render_report(results: list[CheckResult]) -> str:
    status_counts = {status: sum(row.status == status for row in results) for status in ["PASS", "WARN", "FAIL"]}
    lines = [
        "# ko_unstructured_v2 Data Quality Report",
        "",
        "This report is read-only: it checks JSONL artifacts and live index counts without "
        "creating, deleting, or mutating Qdrant/OpenSearch data.",
        "",
        "## Summary",
        "",
        f"- PASS: {status_counts['PASS']}",
        f"- WARN: {status_counts['WARN']}",
        f"- FAIL: {status_counts['FAIL']}",
        "",
        "## Checks",
        "",
        "| Check | Status | Observed | Expected | Details |",
        "| --- | --- | ---: | ---: | --- |",
    ]
    for row in results:
        lines.append(
            f"| {row.name} | {row.status} | {row.observed} | {row.expected} | {row.details} |"
        )
    lines.append("")
    return "\n".join(lines)


def write_reports(report: str, repo_report: Path, external_report: Path) -> None:
    for path in (repo_report, external_report):
        ensure_parent(path)
        path.write_text(report, encoding="utf-8")


@app.command()
def run(
    data_root: Path = typer.Option(OfficeDePaths().data_root),
    repo_report: Path = typer.Option(DEFAULT_REPO_DQ_REPORT),
    external_report: Path | None = typer.Option(None),
    qdrant_url: str = "http://localhost:6333",
    opensearch_url: str = "http://localhost:9200",
    live_indexes: bool = typer.Option(True),
) -> None:
    """Run read-only data quality checks for ko_unstructured_v2."""
    paths = OfficeDePaths(data_root)
    results = run_quality_checks(
        paths,
        qdrant_url=qdrant_url,
        opensearch_url=opensearch_url,
        check_live_indexes=live_indexes,
    )
    report = render_report(results)
    write_reports(
        report,
        repo_report,
        external_report or paths.reports_root / "data_quality_report.md",
    )
    failures = sum(row.status == "FAIL" for row in results)
    typer.echo(f"Wrote data quality report with {failures} failures to {repo_report}")
    if failures:
        raise typer.Exit(1)


def main() -> None:
    app()

