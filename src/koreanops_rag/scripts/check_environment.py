from __future__ import annotations

import platform
import os
import shutil
import subprocess
import sys
from pathlib import Path

from koreanops_rag.config import load_config


def _run(command: list[str]) -> tuple[bool, str]:
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=15, check=False)
    except FileNotFoundError:
        return False, "not installed"
    except subprocess.TimeoutExpired:
        return False, "timed out"
    output = (result.stdout or result.stderr).strip()
    return result.returncode == 0, output


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
