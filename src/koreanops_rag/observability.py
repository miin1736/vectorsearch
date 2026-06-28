from __future__ import annotations

import json
import os
import time
import uuid
from contextlib import AbstractContextManager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from koreanops_rag.io import ensure_parent


def default_reports_dir() -> Path:
    return Path(os.getenv("DATA_ROOT", r"C:\vectorsearch-data")) / "reports"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def path_fingerprint(path: Path) -> dict[str, Any]:
    """Return a cheap artifact fingerprint without reading large files twice."""
    resolved = path.resolve()
    if not resolved.exists():
        return {
            "path": str(resolved),
            "exists": False,
        }
    stat = resolved.stat()
    return {
        "path": str(resolved),
        "exists": True,
        "size_bytes": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
    }


class RunRecorder(AbstractContextManager["RunRecorder"]):
    def __init__(
        self,
        stage: str,
        reports_dir: Path,
        *,
        run_id: str | None = None,
        command: str = "",
        config_path: Path | None = None,
        input_paths: list[Path] | None = None,
        output_paths: list[Path] | None = None,
    ) -> None:
        self.run_id = run_id or uuid.uuid4().hex[:12]
        self.stage = stage
        self.command = command
        self.config_path = config_path
        self.input_paths = input_paths or []
        self.output_paths = output_paths or []
        self.reports_dir = reports_dir
        self.run_dir = reports_dir / "runs"
        self.manifest_path = self.run_dir / f"{self.run_id}_{stage}.json"
        self.events_path = self.run_dir / f"{self.run_id}_{stage}.events.jsonl"
        self.started_at = utc_now()
        self.started_perf = time.perf_counter()
        self.record_count = 0

    def __enter__(self) -> "RunRecorder":
        ensure_parent(self.manifest_path)
        self.event("stage_started")
        self._write_manifest("running")
        return self

    def __exit__(self, exc_type, exc, traceback) -> bool:
        if exc is None:
            self.event("stage_finished", record_count=self.record_count)
            self._write_manifest("succeeded")
            return False
        self.event(
            "stage_failed",
            error_type=exc_type.__name__ if exc_type else "",
            error_message=str(exc),
            record_count=self.record_count,
        )
        self._write_manifest(
            "failed",
            error_type=exc_type.__name__ if exc_type else "",
            error_message=str(exc),
        )
        return False

    def set_record_count(self, count: int) -> None:
        self.record_count = count

    def event(self, event: str, **payload: Any) -> None:
        ensure_parent(self.events_path)
        row = {
            "run_id": self.run_id,
            "stage": self.stage,
            "event": event,
            "timestamp": utc_now(),
            **payload,
        }
        with self.events_path.open("a", encoding="utf-8", newline="\n") as file:
            file.write(json.dumps(row, ensure_ascii=False) + "\n")

    def _write_manifest(
        self,
        status: str,
        *,
        error_type: str = "",
        error_message: str = "",
    ) -> None:
        finished_at = utc_now() if status != "running" else ""
        manifest = {
            "run_id": self.run_id,
            "stage": self.stage,
            "status": status,
            "command": self.command,
            "config_path": str(self.config_path.resolve()) if self.config_path else "",
            "input_artifacts": [path_fingerprint(path) for path in self.input_paths],
            "output_artifacts": [path_fingerprint(path) for path in self.output_paths],
            "started_at": self.started_at,
            "finished_at": finished_at,
            "elapsed_ms": round((time.perf_counter() - self.started_perf) * 1000, 3),
            "record_count": self.record_count,
            "error_type": error_type,
            "error_message": error_message,
            "events_path": str(self.events_path.resolve()),
        }
        self.manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
