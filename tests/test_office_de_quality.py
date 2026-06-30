import json
from pathlib import Path

from koreanops_rag.office_de.paths import OfficeDePaths
from koreanops_rag.office_de.quality import render_report, run_quality_checks


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as file:
        for row in rows:
            file.write(json.dumps(row, ensure_ascii=False) + "\n")


def test_quality_checks_detect_chunk_integrity_errors(tmp_path):
    paths = OfficeDePaths(tmp_path)
    _write_jsonl(
        paths.manifest_jsonl,
        [{"doc_id": "doc-1"}, {"doc_id": "doc-2"}],
    )
    _write_jsonl(
        paths.documents_jsonl,
        [
            {"doc_id": "doc-1", "content": "content"},
            {"doc_id": "doc-2", "content": ""},
        ],
    )
    bad_chunk = {
        "doc_id": "chunk-1",
        "content": "chunk",
        "metadata": {"parent_doc_id": "missing", "page_start": 3, "page_end": 1},
    }
    _write_jsonl(paths.chunks_page_jsonl, [bad_chunk, bad_chunk])
    _write_jsonl(
        paths.chunks_structure_jsonl,
        [
            {
                "doc_id": "chunk-2",
                "content": "chunk",
                "metadata": {"parent_doc_id": "doc-1", "page_start": 1, "page_end": 2},
            }
        ],
    )

    results = run_quality_checks(paths, check_live_indexes=False)
    by_name = {row.name: row for row in results}

    assert by_name["empty content document count"].status == "WARN"
    assert by_name["page duplicate chunk ids"].status == "FAIL"
    assert by_name["page chunk parent_doc_id exists"].status == "FAIL"
    assert by_name["page page_start <= page_end"].status == "FAIL"
    assert by_name["structure chunk parent_doc_id exists"].status == "PASS"


def test_quality_report_renders_summary():
    report = render_report(
        [
            type(
                "Result",
                (),
                {
                    "name": "check",
                    "status": "PASS",
                    "observed": "1",
                    "expected": "1",
                    "details": "",
                },
            )()
        ]
    )

    assert "# ko_unstructured_v2 Data Quality Report" in report
    assert "| check | PASS | 1 | 1 |  |" in report

