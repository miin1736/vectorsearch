from pathlib import Path

from koreanops_rag.dashboard import (
    build_dashboard_model,
    load_project_registry,
    render_dashboard,
    resolve_dataset_path,
)


def test_project_registry_loads_all_projects() -> None:
    registry = load_project_registry()

    project_ids = {project.project_id for project in registry.projects}

    assert project_ids == {
        "koreanops_v1",
        "ko_unstructured_v2",
        "ko_dense_technical_v3",
        "shared",
    }
    assert registry.projects[2].cases
    assert registry.projects[2].cases[0].case_id == "baseline_fixed_512"
    assert registry.projects[2].reports
    assert registry.projects[3].reports[0].report_id == "data_dashboard_guide"


def test_dashboard_model_uses_standard_dataset_shape(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    data_root.mkdir()
    (data_root / "sample.jsonl").write_text(
        '{"doc_id":"a","content":"hello","metadata":{"chunking_strategy":"fixed"}}\n',
        encoding="utf-8",
    )
    registry_path = tmp_path / "registry.yaml"
    registry_path.write_text(
        f"""
schema_version: 1
projects:
  - project_id: demo
    version: v0
    label: Demo
    data_root: {data_root}
    datasets:
      - dataset_id: sample
        label: Sample
        scope: pilot
        stage: chunked
        path: sample.jsonl
        format: jsonl
        case_id: case_a
        chunking_strategy: fixed
""",
        encoding="utf-8",
    )

    registry = load_project_registry(registry_path)
    model = build_dashboard_model(registry)
    row = model["datasets"][0]

    assert resolve_dataset_path(registry.projects[0], registry.projects[0].datasets[0]).exists()
    assert row["project_id"] == "demo"
    assert row["scope"] == "pilot"
    assert row["stage"] == "chunked"
    assert row["case_id"] == "case_a"
    assert row["chunking_strategy"] == "fixed"
    assert row["records"] == 1
    assert row["samples"][0]["doc_id"] == "a"


def test_dashboard_model_includes_reports(tmp_path: Path) -> None:
    report_path = tmp_path / "report.md"
    report_path.write_text("# Report\n\nA short note.\n", encoding="utf-8")
    registry_path = tmp_path / "registry.yaml"
    registry_path.write_text(
        f"""
schema_version: 1
projects:
  - project_id: demo
    version: v0
    label: Demo
    data_root: {tmp_path}
    datasets: []
    reports:
      - report_id: report
        label: Report
        scope: pilot
        role: evaluation
        path: {report_path}
""",
        encoding="utf-8",
    )

    registry = load_project_registry(registry_path)
    model = build_dashboard_model(registry)
    report = model["reports"][0]

    assert report["artifact_type"] == "report"
    assert report["stage"] == "report"
    assert report["report_role"] == "evaluation"
    assert report["records"] == 3
    assert model["artifacts"][0]["dataset_id"] == "report"


def test_dashboard_model_builds_qaset_links(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    (data_root / "eval").mkdir(parents=True)
    (data_root / "processed").mkdir()
    (data_root / "eval" / "questions.jsonl").write_text(
        (
            '{"question_id":"q1","question":"What happened?",'
            '"reference_answer":"It restarted.","gold_doc_ids":["doc_1"],'
            '"gold_pages":[2],"evidence_text":"service restarted"}\n'
        ),
        encoding="utf-8",
    )
    (data_root / "processed" / "documents.jsonl").write_text(
        '{"doc_id":"doc_1","title":"Incident","content":"The service restarted."}\n',
        encoding="utf-8",
    )
    registry_path = tmp_path / "registry.yaml"
    registry_path.write_text(
        f"""
schema_version: 1
projects:
  - project_id: demo
    version: v0
    label: Demo
    data_root: {data_root}
    datasets:
      - dataset_id: documents_full
        label: Documents
        scope: pilot
        stage: normalized
        path: processed/documents.jsonl
        format: jsonl
      - dataset_id: validation_questions
        label: Questions
        scope: pilot
        stage: qaset
        path: eval/questions.jsonl
        format: jsonl
""",
        encoding="utf-8",
    )

    registry = load_project_registry(registry_path)
    model = build_dashboard_model(registry)
    links = model["qaset_links"]["demo"]

    assert links[0]["question_id"] == "q1"
    assert links[0]["scope"] == "pilot"
    assert links[0]["documents"][0]["doc_id"] == "doc_1"
    assert links[0]["documents"][0]["content"] == "The service restarted."


def test_render_dashboard_embeds_model() -> None:
    html = render_dashboard(
        {
            "schema_version": 1,
            "projects": [],
            "datasets": [],
            "reports": [],
            "artifacts": [],
            "qaset_links": {},
            "summary": {"projects": 0, "datasets": 0, "scopes": []},
        }
    )

    assert "KoreanOps-RAG Data Dashboard" in html
    assert "dashboard-data" in html
    assert "Linked QASET question" in html
    assert "All scopes" in html
