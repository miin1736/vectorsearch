from __future__ import annotations

import json
from pathlib import Path

from koreanops_rag.observability import RunRecorder, path_fingerprint


def test_path_fingerprint_records_stable_file_metadata(tmp_path: Path):
    path = tmp_path / "input.jsonl"
    path.write_text('{"x": 1}\n', encoding="utf-8")

    fingerprint = path_fingerprint(path)

    assert fingerprint["path"] == str(path.resolve())
    assert fingerprint["exists"] is True
    assert fingerprint["size_bytes"] > 0
    assert "mtime_ns" in fingerprint


def test_run_recorder_writes_manifest_and_events(tmp_path: Path):
    input_path = tmp_path / "input.jsonl"
    output_path = tmp_path / "output.jsonl"
    input_path.write_text('{"x": 1}\n', encoding="utf-8")

    with RunRecorder(
        "demo_stage",
        tmp_path / "reports",
        run_id="run123",
        command="demo-command",
        input_paths=[input_path],
        output_paths=[output_path],
    ) as recorder:
        output_path.write_text('{"ok": true}\n', encoding="utf-8")
        recorder.set_record_count(1)
        recorder.event("custom_event", value=7)

    manifest = json.loads(
        (tmp_path / "reports" / "runs" / "run123_demo_stage.json").read_text(encoding="utf-8")
    )
    events = [
        json.loads(line)
        for line in (tmp_path / "reports" / "runs" / "run123_demo_stage.events.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]

    assert manifest["status"] == "succeeded"
    assert manifest["record_count"] == 1
    assert manifest["input_artifacts"][0]["exists"] is True
    assert manifest["output_artifacts"][0]["exists"] is True
    assert [event["event"] for event in events] == [
        "stage_started",
        "custom_event",
        "stage_finished",
    ]
