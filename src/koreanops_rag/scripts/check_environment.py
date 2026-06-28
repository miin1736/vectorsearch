from __future__ import annotations

import platform
import os
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

from koreanops_rag.config import AppConfig, load_config


def _run(command: list[str]) -> tuple[bool, str]:
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=15, check=False)
    except FileNotFoundError:
        return False, "not installed"
    except subprocess.TimeoutExpired:
        return False, "timed out"
    output = (result.stdout or result.stderr).strip()
    return result.returncode == 0, output


def _is_local_url(value: str) -> bool:
    hostname = urlparse(value).hostname
    return hostname in {"localhost", "127.0.0.1", "::1"}


def _is_under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def _print_guardrail_warnings(config: AppConfig) -> None:
    config_data_root = Path(config.data_root)
    cache_vars = ["HF_HOME", "SENTENCE_TRANSFORMERS_HOME", "TORCH_HOME", "OLLAMA_MODELS"]
    for name in cache_vars:
        raw = os.getenv(name)
        if not raw:
            print(f"WARNING: {name} is not set; downloads may fall back to a user-profile cache.")
            continue
        if not _is_under(Path(raw), config_data_root):
            print(f"WARNING: {name} is outside DATA_ROOT: {raw}")

    for name, value in {
        "QDRANT_URL": os.getenv("QDRANT_URL", config.qdrant.url),
        "OPENSEARCH_URL": os.getenv("OPENSEARCH_URL", config.opensearch.url),
    }.items():
        if not _is_local_url(value):
            print(f"WARNING: {name} is not local-only: {value}")

    print("WARNING: OpenSearch security is disabled in docker-compose.yml for local experiments only.")


def main() -> None:
    config = load_config()
    print(f"Python: {sys.version.split()[0]} ({platform.architecture()[0]})")
    if platform.architecture()[0] != "64bit":
        raise SystemExit("ERROR: 64-bit Python is required. Do not use the 32-bit python command.")

    data_root = Path(config.data_root)
    data_root.mkdir(parents=True, exist_ok=True)
    for child in ["raw", "processed", "index", "eval", "reports"]:
        (data_root / child).mkdir(exist_ok=True)
    print(f"DATA_ROOT: {data_root}")
    for name in ["HF_HOME", "SENTENCE_TRANSFORMERS_HOME", "TORCH_HOME", "OLLAMA_MODELS"]:
        print(f"{name}: {os.getenv(name, 'not set')}")
    _print_guardrail_warnings(config)

    docker_path = shutil.which("docker")
    print(f"Docker CLI: {docker_path or 'not installed'}")
    ok, output = _run(["docker", "info"])
    if not ok:
        print("Docker daemon: not running or unavailable")
        print(output)
    else:
        print("Docker daemon: OK")

    ok, output = _run(["ollama", "--version"])
    print(f"Ollama: {output if ok else 'not installed'}")
