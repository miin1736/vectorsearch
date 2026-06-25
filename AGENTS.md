# KoreanOps-RAG Codex Working Rules

## Project Goal

Build a CPU-first, reproducible Hybrid RAG experiment platform for IT support tickets and
system logs. The main deliverable is an experiment report comparing BM25, dense vector
search, hybrid RRF retrieval, and optional reranking.

## Required Execution Rules

- Use `uv run ...` for Python commands.
- Do not use the system `python` command directly. On this PC it points to 32-bit Python 3.10.
- Use Python 3.11 64-bit through the project `.venv`.
- Keep large data, indexes, and generated experiment artifacts under `C:\vectorsearch-data`.
- Keep downloaded model/cache artifacts under `C:\vectorsearch-data` as well:
  - HuggingFace: `C:\vectorsearch-data\models\huggingface`
  - Sentence Transformers: `C:\vectorsearch-data\models\huggingface\sentence-transformers`
  - Torch cache: `C:\vectorsearch-data\cache\torch`
  - Ollama models: `C:\vectorsearch-data\models\ollama`
- Do not install project-specific packages or model assets into arbitrary user-profile folders.
  Executable installers may live outside the project, but their data/model directories should be
  pointed back to the project repo or `C:\vectorsearch-data`.
- Do not commit raw datasets, large processed JSONL files, vector indexes, or OpenSearch data.
- Do not hard-code local absolute paths in source code; read them from config or environment.
- Keep source code CPU-friendly. Do not assume CUDA GPU acceleration.
- Design large-data processing as streaming or batched work.
- Make indexing restartable where practical.
- Keep LLM calls isolated behind provider interfaces in `src/koreanops_rag/rag/`.

## Code Style

- Prefer simple, typed Python.
- Use Pydantic models for shared schemas.
- Use JSONL for large intermediate datasets.
- Keep public functions small and testable.
- Add short docstrings when behavior is not obvious.
- Use `ruff` and `pytest` before considering a task complete.

## Verification Commands

```powershell
uv run ruff check .
uv run pytest
uv run koreanops-check-env
docker compose config
```

Before downloading models, load `.env` values into the shell or set equivalent user-level
environment variables so caches do not default to the Windows user profile.

For Ollama on Windows, do not rely on the tray app for project runs. The tray app can start
`ollama serve` before `OLLAMA_MODELS` is loaded, causing Ollama to look at the default
`%USERPROFILE%\.ollama\models` directory. Prefer `.\scripts\start-ollama-project.ps1` so
the server inherits `OLLAMA_MODELS=C:\vectorsearch-data\models\ollama`.

## Docker Notes

- Qdrant and OpenSearch are managed through `docker-compose.yml`.
- Docker Desktop must be running before service-dependent commands.
- OpenSearch is configured without the security plugin for local experiments.
- OpenSearch heap is intentionally limited to 2 GB for the current 32 GB RAM PC.

## Codex Preferences

- First check existing files with `rg` or `rg --files`.
- Prefer extending existing modules over creating unrelated scripts.
- Keep generated files out of the repo unless they are small samples, templates, or reports.
- When adding a new pipeline step, include a CLI entry in `pyproject.toml` if it is user-facing.
- When changing retrieval or evaluation logic, add or update unit tests.
- Treat `reports/experiment_report.md` and `reports/failure_analysis.md` as human-facing outputs.
