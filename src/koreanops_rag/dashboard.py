from __future__ import annotations

import csv
import html
import json
from collections import Counter
from pathlib import Path
from typing import Any, Literal

import typer
import yaml
from pydantic import BaseModel, Field, model_validator

from koreanops_rag.io import ensure_parent

DEFAULT_PROJECT_REGISTRY = Path("experiments/project_registry.yaml")
DEFAULT_OUTPUT = Path(r"C:\vectorsearch-data\reports\data_dashboard.html")
SAMPLE_LIMIT = 5
QASET_LINK_LIMIT = 1000
TEXT_SNIPPET_LIMIT = 900

DatasetFormat = Literal["jsonl", "csv", "text", "directory"]

app = typer.Typer(add_completion=False)


class DatasetEntry(BaseModel):
    dataset_id: str
    label: str
    scope: str = "default"
    stage: str
    path: Path
    format: DatasetFormat
    source_type: str = ""
    case_id: str = ""
    chunking_strategy: str = ""
    qdrant_collection: str = ""
    opensearch_index: str = ""
    description: str = ""


class ReportEntry(BaseModel):
    report_id: str
    label: str
    scope: str = "default"
    role: str
    path: Path
    description: str = ""


class CaseEntry(BaseModel):
    case_id: str
    stage: str = ""
    group: str = ""
    technique: str = ""
    enabled: bool = True
    index_namespace: str = ""
    chunking_profile: str = ""


class ProjectEntry(BaseModel):
    project_id: str
    version: str
    label: str
    data_root: Path
    namespace_prefix: str = ""
    case_registry: Path | None = None
    datasets: list[DatasetEntry] = Field(default_factory=list)
    reports: list[ReportEntry] = Field(default_factory=list)
    cases: list[CaseEntry] = Field(default_factory=list)


class ProjectRegistry(BaseModel):
    schema_version: int
    projects: list[ProjectEntry]

    @model_validator(mode="after")
    def validate_unique_ids(self) -> "ProjectRegistry":
        project_ids: set[str] = set()
        for project in self.projects:
            if project.project_id in project_ids:
                raise ValueError(f"Duplicate project_id: {project.project_id}")
            project_ids.add(project.project_id)

            dataset_ids: set[str] = set()
            for dataset in project.datasets:
                if dataset.dataset_id in dataset_ids:
                    raise ValueError(
                        f"{project.project_id} has duplicate dataset_id: {dataset.dataset_id}"
                    )
                dataset_ids.add(dataset.dataset_id)
            report_ids: set[str] = set()
            for report in project.reports:
                if report.report_id in report_ids:
                    raise ValueError(
                        f"{project.project_id} has duplicate report_id: {report.report_id}"
                    )
                report_ids.add(report.report_id)
        return self


def load_project_registry(path: Path = DEFAULT_PROJECT_REGISTRY) -> ProjectRegistry:
    with path.open("r", encoding="utf-8") as file:
        raw = yaml.safe_load(file) or {}
    registry = ProjectRegistry.model_validate(raw)
    return _attach_external_cases(registry, path.parent)


def _attach_external_cases(registry: ProjectRegistry, registry_dir: Path) -> ProjectRegistry:
    for project in registry.projects:
        if not project.case_registry:
            continue
        case_path = _resolve_repo_path(project.case_registry, registry_dir)
        if not case_path.exists():
            continue
        with case_path.open("r", encoding="utf-8") as file:
            raw = yaml.safe_load(file) or {}
        project.cases = [
            CaseEntry(
                case_id=str(case.get("case_id", "")),
                stage=str(case.get("stage", "")),
                group=str(case.get("group", "")),
                technique=str(case.get("technique", "")),
                enabled=bool(case.get("enabled", True)),
                index_namespace=str(case.get("index_namespace", "")),
                chunking_profile=str(case.get("chunking_profile", "")),
            )
            for case in raw.get("test_cases", [])
        ]
    return registry


def _resolve_repo_path(path: Path, registry_dir: Path) -> Path:
    if path.is_absolute():
        return path
    direct = Path(path)
    if direct.exists():
        return direct
    return registry_dir / path


def resolve_dataset_path(project: ProjectEntry, dataset: DatasetEntry) -> Path:
    if dataset.path.is_absolute():
        return dataset.path
    return project.data_root / dataset.path


def resolve_report_path(report: ReportEntry) -> Path:
    if report.path.is_absolute():
        return report.path
    return Path(report.path)


def _sample_jsonl(path: Path) -> tuple[int, list[dict[str, Any]], list[str]]:
    total = 0
    samples: list[dict[str, Any]] = []
    keys: set[str] = set()
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            if not line.strip():
                continue
            total += 1
            if len(samples) < SAMPLE_LIMIT:
                row = json.loads(line)
                samples.append(row)
                keys.update(row.keys())
    return total, samples, sorted(keys)


def _sample_csv(path: Path) -> tuple[int, list[dict[str, Any]], list[str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        samples: list[dict[str, Any]] = []
        total = 0
        for row in reader:
            total += 1
            if len(samples) < SAMPLE_LIMIT:
                samples.append(dict(row))
    return total, samples, list(reader.fieldnames or [])


def _sample_text(path: Path) -> tuple[int, list[dict[str, Any]], list[str]]:
    samples: list[dict[str, Any]] = []
    total = 0
    with path.open("r", encoding="utf-8", errors="replace") as file:
        for line in file:
            total += 1
            if len(samples) < SAMPLE_LIMIT:
                samples.append({"line": line.rstrip("\n")})
    return total, samples, ["line"]


def _sample_markdown(path: Path) -> tuple[int, list[dict[str, Any]], list[str]]:
    samples: list[dict[str, Any]] = []
    total = 0
    with path.open("r", encoding="utf-8", errors="replace") as file:
        for line in file:
            total += 1
            text = line.rstrip("\n")
            if len(samples) < SAMPLE_LIMIT and text.strip():
                samples.append({"line": total, "text": text})
    return total, samples, ["line", "text"]


def _sample_directory(path: Path) -> tuple[int, list[dict[str, Any]], list[str]]:
    if not path.exists():
        return 0, [], ["path", "bytes", "modified"]
    files = [child for child in path.rglob("*") if child.is_file()]
    samples = [
        {
            "path": str(child),
            "bytes": child.stat().st_size,
            "modified": child.stat().st_mtime,
        }
        for child in sorted(files)[:SAMPLE_LIMIT]
    ]
    return len(files), samples, ["path", "bytes", "modified"]


def _read_jsonl_rows(path: Path, limit: int | None = None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            if not line.strip():
                continue
            rows.append(json.loads(line))
            if limit is not None and len(rows) >= limit:
                break
    return rows


def _clip_text(value: Any, limit: int = TEXT_SNIPPET_LIMIT) -> str:
    text = str(value or "").replace("\r\n", "\n").strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "..."


def _doc_id(row: dict[str, Any]) -> str:
    return str(row.get("doc_id") or row.get("question_id") or "")


def _parent_doc_id(row: dict[str, Any]) -> str:
    metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    return str(metadata.get("parent_doc_id") or row.get("doc_id") or "")


def _page_num(row: dict[str, Any]) -> int | None:
    for key in ("page_num", "page_start"):
        value = row.get(key)
        if value is not None:
            return int(value)
    metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    value = metadata.get("page_start")
    return int(value) if value is not None else None


def _page_range(row: dict[str, Any]) -> tuple[int | None, int | None]:
    metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    start = metadata.get("page_start", row.get("page_num"))
    end = metadata.get("page_end", start)
    return (
        int(start) if start is not None else None,
        int(end) if end is not None else None,
    )


def _matches_pages(row: dict[str, Any], pages: set[int]) -> bool:
    if not pages:
        return True
    start, end = _page_range(row)
    if start is None:
        return True
    if start <= 0:
        return True
    end = end if end is not None else start
    return any(start <= page <= end for page in pages)


def _scope_matches(dataset: DatasetEntry, scope: str) -> bool:
    return dataset.scope in {scope, "shared", "all_cases"}


def _find_dataset(
    project: ProjectEntry,
    *,
    stage: str,
    scope: str,
    dataset_ids: set[str] | None = None,
    chunking_strategies: set[str] | None = None,
) -> DatasetEntry | None:
    for dataset in project.datasets:
        if dataset.stage != stage or not _scope_matches(dataset, scope):
            continue
        if dataset_ids and dataset.dataset_id not in dataset_ids:
            continue
        if chunking_strategies and dataset.chunking_strategy not in chunking_strategies:
            continue
        return dataset
    return None


def _find_datasets(
    project: ProjectEntry,
    *,
    stage: str,
    scope: str,
    chunking_strategies: set[str] | None = None,
) -> list[DatasetEntry]:
    rows = []
    for dataset in project.datasets:
        if dataset.stage != stage or not _scope_matches(dataset, scope):
            continue
        if chunking_strategies and dataset.chunking_strategy not in chunking_strategies:
            continue
        rows.append(dataset)
    return rows


def _summarize_text_row(row: dict[str, Any], kind: str) -> dict[str, Any]:
    metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    return {
        "kind": kind,
        "doc_id": _doc_id(row),
        "parent_doc_id": _parent_doc_id(row),
        "title": row.get("title", ""),
        "page_num": row.get("page_num", metadata.get("page_start", "")),
        "page_start": metadata.get("page_start", ""),
        "page_end": metadata.get("page_end", ""),
        "chunking_strategy": metadata.get("chunking_strategy", ""),
        "chunk_index": metadata.get("chunk_index", ""),
        "section_path": metadata.get("section_path", ""),
        "content": _clip_text(
            row.get("content") or row.get("clean_text") or row.get("raw_text") or row.get("text")
        ),
        "metadata": {
            key: metadata.get(key, "")
            for key in (
                "document_type",
                "publisher",
                "research_field",
                "paper_topic",
                "source_archive",
                "source_member",
                "source_path",
                "parent_doc_id",
            )
            if metadata.get(key, "") != ""
        },
    }


def _load_rows_by_doc_id(path: Path, wanted_doc_ids: set[str], kind: str) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    if not wanted_doc_ids or not path.exists():
        return rows
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            if not line.strip():
                continue
            row = json.loads(line)
            doc_id = _doc_id(row)
            if doc_id in wanted_doc_ids and doc_id not in rows:
                rows[doc_id] = _summarize_text_row(row, kind)
                if len(rows) == len(wanted_doc_ids):
                    break
    return rows


def _load_page_rows(
    path: Path,
    wanted_doc_ids: set[str],
    wanted_pages_by_doc: dict[str, set[int]],
    kind: str,
) -> dict[str, list[dict[str, Any]]]:
    rows: dict[str, list[dict[str, Any]]] = {doc_id: [] for doc_id in wanted_doc_ids}
    if not wanted_doc_ids or not path.exists():
        return rows
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            if not line.strip():
                continue
            row = json.loads(line)
            doc_id = _parent_doc_id(row)
            if doc_id not in wanted_doc_ids:
                continue
            pages = wanted_pages_by_doc.get(doc_id, set())
            if not _matches_pages(row, pages):
                continue
            if len(rows[doc_id]) < 3:
                rows[doc_id].append(_summarize_text_row(row, kind))
    return rows


def _dataset_by_id(project: ProjectEntry) -> dict[str, DatasetEntry]:
    return {dataset.dataset_id: dataset for dataset in project.datasets}


def build_qaset_links(project: ProjectEntry) -> list[dict[str, Any]]:
    qaset_dataset = next((dataset for dataset in project.datasets if dataset.stage == "qaset"), None)
    if not qaset_dataset:
        return []
    scope = qaset_dataset.scope
    qaset_path = resolve_dataset_path(project, qaset_dataset)
    questions = _read_jsonl_rows(qaset_path, limit=QASET_LINK_LIMIT)
    if not questions:
        return []

    wanted_doc_ids: set[str] = set()
    wanted_pages_by_doc: dict[str, set[int]] = {}
    for question in questions:
        doc_ids = [str(doc_id) for doc_id in question.get("gold_doc_ids", [])]
        pages = {int(page) for page in question.get("gold_pages", []) if str(page).isdigit()}
        for doc_id in doc_ids:
            wanted_doc_ids.add(doc_id)
            wanted_pages_by_doc.setdefault(doc_id, set()).update(pages)

    document_dataset = _find_dataset(
        project,
        stage="normalized",
        scope=scope,
        dataset_ids={"normalized_documents", "documents_full", "pilot_1000_normalized_documents"},
    )
    document_rows = (
        _load_rows_by_doc_id(
            resolve_dataset_path(project, document_dataset),
            wanted_doc_ids,
            "normalized_document",
        )
        if document_dataset
        else {}
    )

    page_rows: dict[str, list[dict[str, Any]]] = {doc_id: [] for doc_id in wanted_doc_ids}
    for dataset in _find_datasets(project, stage="parsed", scope=scope):
        if "page" not in dataset.dataset_id:
            continue
        loaded = _load_page_rows(
            resolve_dataset_path(project, dataset),
            wanted_doc_ids,
            wanted_pages_by_doc,
            "raw_page",
        )
        for doc_id, rows in loaded.items():
            page_rows.setdefault(doc_id, []).extend(rows)

    primary_chunk_rows: dict[str, list[dict[str, Any]]] = {doc_id: [] for doc_id in wanted_doc_ids}
    for dataset in _find_datasets(
        project,
        stage="chunked",
        scope=scope,
        chunking_strategies={"page", "fixed", "passage", "tokenizer_fixed"},
    ):
        loaded = _load_page_rows(
            resolve_dataset_path(project, dataset),
            wanted_doc_ids,
            wanted_pages_by_doc,
            f"{dataset.chunking_strategy}_chunk",
        )
        for doc_id, rows in loaded.items():
            primary_chunk_rows.setdefault(doc_id, []).extend(rows)

    structure_chunk_rows: dict[str, list[dict[str, Any]]] = {
        doc_id: [] for doc_id in wanted_doc_ids
    }
    for dataset in _find_datasets(
        project,
        stage="chunked",
        scope=scope,
        chunking_strategies={"structure", "section"},
    ):
        loaded = _load_page_rows(
            resolve_dataset_path(project, dataset),
            wanted_doc_ids,
            wanted_pages_by_doc,
            f"{dataset.chunking_strategy}_chunk",
        )
        for doc_id, rows in loaded.items():
            structure_chunk_rows.setdefault(doc_id, []).extend(rows)

    links: list[dict[str, Any]] = []
    for index, question in enumerate(questions, start=1):
        doc_ids = [str(doc_id) for doc_id in question.get("gold_doc_ids", [])]
        links.append(
            {
                "question_index": index,
                "question_id": str(question.get("question_id") or f"q_{index:04d}"),
                "question": _clip_text(question.get("question"), 500),
                "reference_answer": _clip_text(question.get("reference_answer"), 500),
                "gold_doc_ids": doc_ids,
                "gold_pages": question.get("gold_pages", []),
                "evidence_text": _clip_text(question.get("evidence_text"), 700),
                "question_type": question.get("question_type", ""),
                "difficulty": question.get("difficulty", ""),
                "scope": scope,
                "review_status": question.get("review_status", ""),
                "source_type": question.get("source_type", ""),
                "documents": [
                    document_rows[doc_id] for doc_id in doc_ids if doc_id in document_rows
                ],
                "raw_pages": [
                    row for doc_id in doc_ids for row in page_rows.get(doc_id, [])
                ],
                "page_chunks": [
                    row for doc_id in doc_ids for row in primary_chunk_rows.get(doc_id, [])
                ],
                "structure_chunks": [
                    row for doc_id in doc_ids for row in structure_chunk_rows.get(doc_id, [])
                ],
            }
        )
    return links


def summarize_dataset(project: ProjectEntry, dataset: DatasetEntry) -> dict[str, Any]:
    path = resolve_dataset_path(project, dataset)
    exists = path.exists()
    total = 0
    samples: list[dict[str, Any]] = []
    fields: list[str] = []
    error = ""

    if exists:
        try:
            if dataset.format == "jsonl":
                total, samples, fields = _sample_jsonl(path)
            elif dataset.format == "csv":
                total, samples, fields = _sample_csv(path)
            elif dataset.format == "text":
                total, samples, fields = _sample_text(path)
            elif dataset.format == "directory":
                total, samples, fields = _sample_directory(path)
        except Exception as exc:  # pragma: no cover - defensive for local data drift.
            error = str(exc)

    size = path.stat().st_size if exists and path.is_file() else _directory_size(path)
    return {
        "artifact_type": "data",
        "project_id": project.project_id,
        "project_version": project.version,
        "project_label": project.label,
        "data_root": str(project.data_root),
        "dataset_id": dataset.dataset_id,
        "label": dataset.label,
        "scope": dataset.scope,
        "stage": dataset.stage,
        "format": dataset.format,
        "source_type": dataset.source_type,
        "case_id": dataset.case_id,
        "chunking_strategy": dataset.chunking_strategy,
        "qdrant_collection": dataset.qdrant_collection,
        "opensearch_index": dataset.opensearch_index,
        "path": str(path),
        "exists": exists,
        "records": total,
        "bytes": size,
        "fields": fields,
        "samples": samples,
        "error": error,
        "report_role": "",
    }


def summarize_report(project: ProjectEntry, report: ReportEntry) -> dict[str, Any]:
    path = resolve_report_path(report)
    exists = path.exists()
    total = 0
    samples: list[dict[str, Any]] = []
    fields: list[str] = []
    error = ""

    if exists:
        try:
            total, samples, fields = _sample_markdown(path)
        except Exception as exc:  # pragma: no cover - defensive for local report drift.
            error = str(exc)

    return {
        "artifact_type": "report",
        "project_id": project.project_id,
        "project_version": project.version,
        "project_label": project.label,
        "data_root": str(project.data_root),
        "dataset_id": report.report_id,
        "label": report.label,
        "scope": report.scope,
        "stage": "report",
        "format": "markdown",
        "source_type": "",
        "case_id": "",
        "chunking_strategy": "",
        "qdrant_collection": "",
        "opensearch_index": "",
        "path": str(path),
        "exists": exists,
        "records": total,
        "bytes": path.stat().st_size if exists and path.is_file() else 0,
        "fields": fields,
        "samples": samples,
        "error": error,
        "report_role": report.role,
    }


def _directory_size(path: Path) -> int:
    if not path.exists() or not path.is_dir():
        return 0
    return sum(child.stat().st_size for child in path.rglob("*") if child.is_file())


def build_dashboard_model(registry: ProjectRegistry) -> dict[str, Any]:
    datasets = [
        summarize_dataset(project, dataset)
        for project in registry.projects
        for dataset in project.datasets
    ]
    reports = [
        summarize_report(project, report)
        for project in registry.projects
        for report in project.reports
    ]
    artifacts = datasets + reports
    stages = sorted({row["stage"] for row in artifacts})
    scopes = sorted({row["scope"] for row in artifacts})
    projects = [
        {
            "project_id": project.project_id,
            "version": project.version,
            "label": project.label,
            "data_root": str(project.data_root),
            "namespace_prefix": project.namespace_prefix,
            "cases": [case.model_dump() for case in project.cases],
        }
        for project in registry.projects
    ]
    qaset_links = {
        project.project_id: build_qaset_links(project)
        for project in registry.projects
    }
    return {
        "schema_version": registry.schema_version,
        "projects": projects,
        "datasets": datasets,
        "reports": reports,
        "artifacts": artifacts,
        "qaset_links": qaset_links,
        "summary": {
            "projects": len(projects),
            "datasets": len(datasets),
            "reports": len(reports),
            "artifacts": len(artifacts),
            "stages": stages,
            "scopes": scopes,
            "artifacts_by_stage": dict(Counter(row["stage"] for row in artifacts)),
            "artifacts_by_scope": dict(Counter(row["scope"] for row in artifacts)),
            "artifacts_by_type": dict(Counter(row["artifact_type"] for row in artifacts)),
            "datasets_by_stage": dict(Counter(row["stage"] for row in datasets)),
            "datasets_by_scope": dict(Counter(row["scope"] for row in datasets)),
        },
    }


def render_dashboard(model: dict[str, Any]) -> str:
    payload = json.dumps(model, ensure_ascii=False)
    escaped_payload = html.escape(payload, quote=False)
    return f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>KoreanOps-RAG Data Dashboard</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f6f7f9;
      --panel: #ffffff;
      --text: #18202a;
      --muted: #697381;
      --line: #d9dee7;
      --accent: #176b87;
      --accent-2: #4f6f52;
      --warn: #9a5b00;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font: 14px/1.5 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    header {{
      padding: 22px 28px 14px;
      background: var(--panel);
      border-bottom: 1px solid var(--line);
    }}
    h1 {{ margin: 0; font-size: 24px; letter-spacing: 0; }}
    main {{ padding: 18px 28px 28px; }}
    .toolbar {{
      display: grid;
      grid-template-columns: repeat(5, minmax(140px, 1fr));
      gap: 12px;
      margin-bottom: 16px;
    }}
    label {{ display: grid; gap: 5px; color: var(--muted); font-size: 12px; }}
    select, input {{
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 9px 10px;
      background: #fff;
      color: var(--text);
      font: inherit;
    }}
    .metrics {{
      display: grid;
      grid-template-columns: repeat(4, minmax(140px, 1fr));
      gap: 12px;
      margin-bottom: 16px;
    }}
    .metric {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 12px;
    }}
    .metric b {{ display: block; font-size: 20px; }}
    .layout {{
      display: grid;
      grid-template-columns: minmax(360px, 43%) minmax(420px, 1fr);
      gap: 16px;
      align-items: start;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      overflow: hidden;
    }}
    th, td {{
      padding: 9px 10px;
      border-bottom: 1px solid var(--line);
      text-align: left;
      vertical-align: top;
    }}
    th {{ color: var(--muted); font-size: 12px; background: #fbfcfd; }}
    tr {{ cursor: pointer; }}
    tr:hover, tr.selected {{ background: #eef6f8; }}
    .detail {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      overflow: hidden;
    }}
    .detail-head {{ padding: 14px 16px; border-bottom: 1px solid var(--line); }}
    .detail-head h2 {{ margin: 0 0 4px; font-size: 18px; }}
    .linked-view {{ border-top: 1px solid var(--line); padding: 14px 16px; }}
    .linked-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 10px; }}
    .linked-panel {{ border: 1px solid var(--line); border-radius: 8px; overflow: hidden; background: #fff; }}
    .linked-panel h3 {{ margin: 0; padding: 9px 10px; font-size: 13px; background: #fbfcfd; border-bottom: 1px solid var(--line); }}
    .linked-panel pre {{ max-height: 280px; border-top: 0; }}
    .muted {{ color: var(--muted); }}
    .chips {{ display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }}
    .chip {{
      border-radius: 999px;
      padding: 2px 8px;
      background: #eef1f5;
      color: #344054;
      font-size: 12px;
    }}
    pre {{
      margin: 0;
      padding: 14px 16px;
      max-height: 68vh;
      overflow: auto;
      border-top: 1px solid var(--line);
      white-space: pre-wrap;
      word-break: break-word;
      font: 12px/1.55 Consolas, "Courier New", monospace;
      background: #fbfcfd;
    }}
    .path {{
      font-family: Consolas, "Courier New", monospace;
      font-size: 12px;
      overflow-wrap: anywhere;
    }}
    .missing {{ color: var(--warn); font-weight: 600; }}
    @media (max-width: 980px) {{
      .toolbar, .metrics, .layout, .linked-grid {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>KoreanOps-RAG Data Dashboard</h1>
    <div class="muted">Project registry driven view for V1, V2, and V3 data artifacts.</div>
  </header>
  <main>
    <section class="toolbar">
      <label>Project<select id="projectFilter"></select></label>
      <label>Scope<select id="scopeFilter"></select></label>
      <label>Stage<select id="stageFilter"></select></label>
      <label>Case or chunk<select id="caseFilter"></select></label>
      <label>Search<input id="searchBox" placeholder="doc, qaset, path, strategy"></label>
    </section>
    <section class="metrics" id="metrics"></section>
    <section class="layout">
      <table>
        <thead>
          <tr>
            <th>Project</th><th>Artifact</th><th>Stage</th><th>Records</th><th>Status</th>
          </tr>
        </thead>
        <tbody id="datasetRows"></tbody>
      </table>
      <aside class="detail" id="detail"></aside>
    </section>
  </main>
  <script type="application/json" id="dashboard-data">{escaped_payload}</script>
  <script>
    const model = JSON.parse(document.getElementById("dashboard-data").textContent);
    const rows = model.artifacts || model.datasets;
    const qasetLinks = model.qaset_links || {{}};
    const state = {{ selected: rows[0]?.dataset_id || "" }};
    const byId = Object.fromEntries(rows.map(row => [row.project_id + "::" + row.dataset_id, row]));
    const projectFilter = document.getElementById("projectFilter");
    const scopeFilter = document.getElementById("scopeFilter");
    const stageFilter = document.getElementById("stageFilter");
    const caseFilter = document.getElementById("caseFilter");
    const searchBox = document.getElementById("searchBox");

    function optionList(values, allLabel) {{
      return [`<option value="">${{allLabel}}</option>`]
        .concat([...new Set(values.filter(Boolean))].sort().map(v => `<option>${{v}}</option>`))
        .join("");
    }}

    projectFilter.innerHTML = optionList(rows.map(row => row.project_id), "All projects");
    scopeFilter.innerHTML = optionList(rows.map(row => row.scope), "All scopes");
    stageFilter.innerHTML = optionList(rows.map(row => row.stage), "All stages");
    caseFilter.innerHTML = optionList(
      rows.flatMap(row => [row.case_id, row.chunking_strategy]).filter(Boolean),
      "All cases/strategies"
    );

    function filteredRows() {{
      const project = projectFilter.value;
      const scope = scopeFilter.value;
      const stage = stageFilter.value;
      const caseValue = caseFilter.value;
      const query = searchBox.value.trim().toLowerCase();
      return rows.filter(row => {{
        if (project && row.project_id !== project) return false;
        if (scope && row.scope !== scope) return false;
        if (stage && row.stage !== stage) return false;
        if (caseValue && row.case_id !== caseValue && row.chunking_strategy !== caseValue) return false;
        if (!query) return true;
        return JSON.stringify(row).toLowerCase().includes(query);
      }});
    }}

    function fmtInt(value) {{
      return Number(value || 0).toLocaleString();
    }}

    function renderMetrics(activeRows) {{
      const totalRecords = activeRows.reduce((sum, row) => sum + Number(row.records || 0), 0);
      const totalBytes = activeRows.reduce((sum, row) => sum + Number(row.bytes || 0), 0);
      document.getElementById("metrics").innerHTML = [
        ["Artifacts", activeRows.length],
        ["Records/lines/files", fmtInt(totalRecords)],
        ["Bytes", fmtInt(totalBytes)],
        ["Missing", activeRows.filter(row => !row.exists).length],
      ].map(([label, value]) => `<div class="metric"><span class="muted">${{label}}</span><b>${{value}}</b></div>`).join("");
    }}

    function renderRows() {{
      const activeRows = filteredRows();
      renderMetrics(activeRows);
      const tbody = document.getElementById("datasetRows");
      tbody.innerHTML = activeRows.map(row => {{
        const key = row.project_id + "::" + row.dataset_id;
        const status = row.exists ? "ready" : "<span class='missing'>missing</span>";
        const selected = state.selected === key ? " class='selected'" : "";
        return `<tr data-key="${{key}}"${{selected}}>
          <td>${{row.project_version}}<br><span class="muted">${{row.project_id}}</span></td>
          <td><b>${{row.label}}</b><br><span class="path">${{row.dataset_id}}</span></td>
          <td>${{row.stage}}<br><span class="muted">${{row.scope}}</span></td>
          <td>${{fmtInt(row.records)}}</td>
          <td>${{status}}</td>
        </tr>`;
      }}).join("");
      tbody.querySelectorAll("tr").forEach(tr => tr.addEventListener("click", () => {{
        state.selected = tr.dataset.key;
        renderRows();
        renderDetail(byId[state.selected]);
      }}));
      const selected = byId[state.selected] || activeRows[0];
      if (selected) {{
        state.selected = selected.project_id + "::" + selected.dataset_id;
        renderDetail(selected);
      }}
    }}

    function renderDetail(row) {{
      if (!row) return;
      const sample = JSON.stringify(row.samples, null, 2);
      const qasetView = row.stage === "qaset" ? renderQasetLinks(row.project_id) : "";
      document.getElementById("detail").innerHTML = `
        <div class="detail-head">
          <h2>${{row.label}}</h2>
          <div class="muted">${{row.project_id}} / ${{row.stage}}</div>
          <div class="chips">
            <span class="chip">${{row.artifact_type || "data"}}</span>
            <span class="chip">${{row.format}}</span>
            <span class="chip">scope: ${{row.scope}}</span>
            ${{row.report_role ? `<span class="chip">role: ${{row.report_role}}</span>` : ""}}
            ${{row.case_id ? `<span class="chip">case: ${{row.case_id}}</span>` : ""}}
            ${{row.chunking_strategy ? `<span class="chip">chunk: ${{row.chunking_strategy}}</span>` : ""}}
            ${{row.qdrant_collection ? `<span class="chip">qdrant: ${{row.qdrant_collection}}</span>` : ""}}
          </div>
        </div>
        <pre>${{JSON.stringify({{
          path: row.path,
          artifact_type: row.artifact_type,
          exists: row.exists,
          scope: row.scope,
          report_role: row.report_role,
          records: row.records,
          bytes: row.bytes,
          fields: row.fields,
          error: row.error,
        }}, null, 2)}}</pre>
        ${{qasetView}}
        <pre>${{sample}}</pre>
      `;
      const selector = document.getElementById("qasetSelector");
      if (selector) {{
        selector.addEventListener("change", () => renderSelectedQaset(row.project_id, Number(selector.value)));
        renderSelectedQaset(row.project_id, Number(selector.value || 0));
      }}
    }}

    function renderQasetLinks(projectId) {{
      const links = qasetLinks[projectId] || [];
      if (!links.length) {{
        return `<section class="linked-view"><b>QASET linked view</b><div class="muted">No linked QASET records are available for this project yet.</div></section>`;
      }}
      const options = links.map((link, index) => {{
        const label = `${{link.question_id}} · ${{link.question || ""}}`.slice(0, 120);
        return `<option value="${{index}}">${{label}}</option>`;
      }}).join("");
      return `<section class="linked-view">
        <label>Linked QASET question<select id="qasetSelector">${{options}}</select></label>
        <div id="qasetLinkedDetail"></div>
      </section>`;
    }}

    function panel(title, value) {{
      return `<div class="linked-panel"><h3>${{title}}</h3><pre>${{JSON.stringify(value, null, 2)}}</pre></div>`;
    }}

    function renderSelectedQaset(projectId, index) {{
      const links = qasetLinks[projectId] || [];
      const link = links[index];
      const target = document.getElementById("qasetLinkedDetail");
      if (!target || !link) return;
      target.innerHTML = `
        <div class="chips">
          <span class="chip">${{link.question_id}}</span>
          ${{link.question_type ? `<span class="chip">${{link.question_type}}</span>` : ""}}
          ${{link.review_status ? `<span class="chip">${{link.review_status}}</span>` : ""}}
          ${{link.difficulty ? `<span class="chip">${{link.difficulty}}</span>` : ""}}
          ${{link.scope ? `<span class="chip">scope: ${{link.scope}}</span>` : ""}}
          <span class="chip">gold docs: ${{(link.gold_doc_ids || []).length}}</span>
        </div>
        <div class="linked-grid">
          ${{panel("QASET", {{
            question: link.question,
            reference_answer: link.reference_answer,
            gold_doc_ids: link.gold_doc_ids,
            gold_pages: link.gold_pages,
            evidence_text: link.evidence_text,
          }})}}
          ${{panel("Normalized Document", link.documents || [])}}
          ${{panel("Raw Pages", link.raw_pages || [])}}
          ${{panel("Page Chunks", link.page_chunks || [])}}
          ${{panel("Structure Chunks", link.structure_chunks || [])}}
        </div>`;
    }}

    [projectFilter, scopeFilter, stageFilter, caseFilter, searchBox].forEach(el => el.addEventListener("input", renderRows));
    renderRows();
  </script>
</body>
</html>
"""


@app.command("inventory")
def write_inventory(
    output_json: Path = typer.Option(
        Path(r"C:\vectorsearch-data\reports\data_dashboard_inventory.json"),
        "--output",
    ),
    registry_path: Path = typer.Option(DEFAULT_PROJECT_REGISTRY, "--registry"),
) -> None:
    """Write the standardized project/dataset inventory as JSON."""
    registry = load_project_registry(registry_path)
    model = build_dashboard_model(registry)
    ensure_parent(output_json)
    output_json.write_text(
        json.dumps(model, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    typer.echo(f"Wrote data dashboard inventory to {output_json}")


@app.command("build")
def build_dashboard(
    output_html: Path = typer.Option(DEFAULT_OUTPUT, "--output"),
    registry_path: Path = typer.Option(DEFAULT_PROJECT_REGISTRY, "--registry"),
) -> None:
    """Build a static local HTML dashboard from the project registry."""
    registry = load_project_registry(registry_path)
    model = build_dashboard_model(registry)
    ensure_parent(output_html)
    output_html.write_text(render_dashboard(model), encoding="utf-8", newline="\n")
    typer.echo(f"Wrote data dashboard to {output_html}")


@app.command("validate")
def validate_registry(
    registry_path: Path = typer.Option(DEFAULT_PROJECT_REGISTRY, "--registry"),
) -> None:
    """Validate the standardized project registry and referenced artifacts."""
    registry = load_project_registry(registry_path)
    model = build_dashboard_model(registry)
    artifacts = model.get("artifacts", model["datasets"])
    missing = [row for row in artifacts if not row["exists"]]
    typer.echo(
        f"Validated {len(registry.projects)} projects, {len(model['datasets'])} datasets, "
        f"and {len(model.get('reports', []))} reports "
        f"({len(missing)} missing local artifacts)"
    )


def main() -> None:
    app()
