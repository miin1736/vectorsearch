# KoreanOps-RAG

Hybrid RAG experiment platform for IT support tickets and system logs.

This repository is configured for the current local machine profile:

- CPU-first execution on Ryzen 7 7800X3D
- 32GB RAM aware batching
- large data outside OneDrive under `C:\vectorsearch-data`
- Docker Compose for Qdrant and OpenSearch
- `uv run ...` instead of the system `python` command, because the default `python`
  on this PC points to 32-bit Python 3.10

## Quick Start

```powershell
uv python install 3.11
uv venv --python 3.11
uv sync --all-groups
uv run koreanops-check-env
```

For model downloads and caches, keep all non-exe artifacts under `C:\vectorsearch-data`.
In PowerShell, dot-source the project environment script before downloading models or
running embedding commands:

```powershell
. .\scripts\project-env.ps1
uv run koreanops-check-env
```

If Ollama was installed through the Windows installer, start its server through the project
script so it inherits `OLLAMA_MODELS`:

```powershell
.\scripts\start-ollama-project.ps1
ollama list
```

If `ollama list` is empty even though model files exist under `C:\vectorsearch-data`, close
the Ollama tray app and rerun `.\scripts\start-ollama-project.ps1`.

Start retrieval infrastructure after Docker Desktop is running:

```powershell
docker compose up -d qdrant opensearch
```

## Data Layout

Large files should not live in this OneDrive-backed repository.

```text
C:\vectorsearch-data
  raw\
  processed\
  index\
  eval\
  reports\
  models\
  cache\
```

Repo-local `data/` directories are placeholders only.

## Pipeline

Normalize tickets:

```powershell
uv run koreanops-load-tickets `
  C:\vectorsearch-data\raw\tickets.csv `
  C:\vectorsearch-data\processed\tickets.jsonl `
  --source-dataset customer_support `
  --dataset-key multilingual_customer_support
```

Normalize LogHub logs:

```powershell
uv run koreanops-load-logs `
  C:\vectorsearch-data\raw\HDFS.log `
  C:\vectorsearch-data\processed\logs.jsonl `
  --source-dataset loghub_hdfs `
  --system hdfs
```

Build RAG documents:

```powershell
uv run koreanops-build-docs `
  C:\vectorsearch-data\processed\documents.jsonl `
  --ticket-jsonl C:\vectorsearch-data\processed\tickets.jsonl `
  --log-jsonl C:\vectorsearch-data\processed\logs.jsonl
```

Index documents after Docker services are healthy:

```powershell
uv run koreanops-index-qdrant C:\vectorsearch-data\processed\documents.jsonl
uv run koreanops-index-opensearch C:\vectorsearch-data\processed\documents.jsonl
```

## Experiment Goal

The primary output is not a demo UI. The primary output is a reproducible experiment
report comparing:

- BM25
- Dense vector search
- Hybrid retrieval with RRF
- Hybrid plus optional reranking

Core metrics:

- Recall@5
- Recall@10
- MRR
- nDCG@10
- P50/P95 latency
- RAGAS faithfulness, answer relevancy, context precision, context recall

RAGAS evaluation should use a stratified sample of 100-300 questions because local
LLM evaluation is CPU-bound and slow.

## Active Experiment Isolation

The current next experiment is `ko_unstructured_v2`. Do not use `configs/default.yaml` for that
experiment. Use one of the stage-specific configs under:

```text
experiments/ko_unstructured_v2/configs/
```

The v2 experiment uses isolated data and index namespaces:

- Data root: `C:\vectorsearch-data\ko-unstructured`
- Qdrant/OpenSearch prefix: `ko_unstructured_`

KoreanOps v1 collections and indexes are historical baselines and should not be deleted or reused
for v2 runs.

## Office PDF v2

The active dataset is AI Hub `18.오피스 문서 생성 데이터`. PDF content is parsed without
consulting labels; labels are used only as an Oracle for evaluation and Golden Set creation.

See `experiments/ko_unstructured_v2/OFFICE_PDF_STATUS.md` for current results and artifact paths.
