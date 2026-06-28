# KoreanOps-RAG

CPU-first Hybrid RAG experiment platform for Korean IT support tickets, system logs, and
office PDF documents.

The project compares BM25, dense vector search, Hybrid RRF/weighted retrieval, and grounded
RAG while keeping experiments reproducible on a Windows PC without CUDA.

## Current Status

The active experiment is `ko_unstructured_v2`, based on AI Hub
`18.오피스 문서 생성 데이터`.

- 9,491 PDFs and 9,491 matching label documents have been inventoried.
- Label JSON is used only as evaluation Oracle data, never to build the production corpus.
- Fixed, Page, Structure, Contextual, and Oracle chunk pipelines are implemented.
- All 9,491 PDFs have been parsed and indexed for the Page and Structure variants.
- Full retrieval evaluation uses 294 auto-approved questions after deterministic Golden Set review.
- Structure Vector is the current winner with Recall@10 `0.5680`, versus Page Vector `0.4626`.
- A 200-question grounded RAG evaluation is complete; the current bottleneck is top-5 evidence
  recall rather than citation plumbing.

These pilot results are provisional. See
[`experiments/ko_unstructured_v2/OFFICE_PDF_STATUS.md`](experiments/ko_unstructured_v2/OFFICE_PDF_STATUS.md)
for current metrics, remaining work, and artifact paths.

Historical ticket/log experiments and their latest findings are documented in
[`PROJECT_PROGRESS_AND_NEXT_PLAN.md`](PROJECT_PROGRESS_AND_NEXT_PLAN.md).

## Local Environment

This repository is configured for the current Windows machine profile:

- CPU-first execution on Ryzen 7 7800X3D
- 32 GB RAM-aware batching
- Python 3.11 64-bit through the project `.venv`
- `uv run ...` instead of the system `python` command
- Docker Compose for Qdrant and OpenSearch
- large data, indexes, models, and generated artifacts under `C:\vectorsearch-data`

The system `python` command must not be used because it points to 32-bit Python 3.10 on the
current machine.

## Quick Start

```powershell
uv python install 3.11
uv venv --python 3.11
uv sync --all-groups
. .\scripts\project-env.ps1
uv run koreanops-check-env
```

Start retrieval infrastructure after Docker Desktop is running:

```powershell
docker compose up -d qdrant opensearch
```

For Ollama, use the project script so the server inherits the project model directory:

```powershell
.\scripts\start-ollama-project.ps1
ollama list
```

If `ollama list` is empty even though model files exist under `C:\vectorsearch-data`, close
the Ollama tray app and rerun the script.

## Data

Raw source data is not committed to GitHub. The shared project data is available from:

- [Google Drive data folder](https://drive.google.com/drive/folders/1uyCAlEuKjXTVFXh3eV0jux2ivFC7NKZY?usp=sharing)

Download or copy the required source files from Google Drive into `C:\vectorsearch-data`.
Do not place large datasets inside this OneDrive-backed repository.

```text
C:\vectorsearch-data
  raw\
  processed\
  index\
  eval\
  reports\
  models\
  cache\
  ko-unstructured\
    raw\
    processed\
    eval\
    reports\
```

The repository-local `data/` directories are placeholders only. Generated JSONL files,
vector indexes, model caches, and large evaluation artifacts must remain outside Git.

## Active Office PDF Experiment

The `ko_unstructured_v2` experiment is isolated from the historical KoreanOps ticket/log
experiment by its data root and index names:

- Data root: `C:\vectorsearch-data\ko-unstructured`
- Qdrant/OpenSearch prefix: `ko_unstructured_pdf_`
- Configs: `experiments/ko_unstructured_v2/configs/`

Do not use `configs/default.yaml` for Office PDF runs. Use one of the experiment-specific
configs such as:

- `pdf_fixed.yaml`
- `pdf_page.yaml`
- `pdf_structure.yaml`
- `pdf_contextual.yaml`
- `pdf_oracle.yaml`

Typical pipeline:

```powershell
# 1. Inventory PDFs in the downloaded AI Hub ZIP archives
uv run koreanops-office-inventory `
  C:\vectorsearch-data\ko-unstructured\raw `
  C:\vectorsearch-data\ko-unstructured\processed\office_manifest.jsonl

# 2. Parse PDFs without consulting label JSON
uv run koreanops-office-parse `
  C:\vectorsearch-data\ko-unstructured\raw `
  C:\vectorsearch-data\ko-unstructured\processed\office_manifest.jsonl `
  C:\vectorsearch-data\ko-unstructured\processed\pages.jsonl `
  C:\vectorsearch-data\ko-unstructured\processed\blocks.jsonl `
  C:\vectorsearch-data\ko-unstructured\processed\documents.jsonl

# 3. Build a structure-aware corpus
uv run koreanops-office-build-chunks `
  C:\vectorsearch-data\ko-unstructured\processed\documents.jsonl `
  C:\vectorsearch-data\ko-unstructured\processed\chunks_structure.jsonl `
  structure `
  --blocks-jsonl C:\vectorsearch-data\ko-unstructured\processed\blocks.jsonl `
  --pages-jsonl C:\vectorsearch-data\ko-unstructured\processed\pages.jsonl
```

Index the resulting corpus with the matching experiment config:

```powershell
uv run koreanops-index-qdrant `
  C:\vectorsearch-data\ko-unstructured\processed\chunks_structure.jsonl `
  --config-path experiments\ko_unstructured_v2\configs\pdf_structure.yaml `
  --resume

uv run koreanops-index-opensearch `
  C:\vectorsearch-data\ko-unstructured\processed\chunks_structure.jsonl `
  --config-path experiments\ko_unstructured_v2\configs\pdf_structure.yaml
```

The Office PDF workflow also includes:

- `koreanops-office-build-oracle`
- `koreanops-office-build-golden`
- `koreanops-office-review-golden`
- `koreanops-office-eval-parsing`
- `koreanops-office-eval-chunking`
- `koreanops-office-eval-retrieval`
- `koreanops-office-eval-rag`

These commands cover evaluation-only Oracle generation, Golden Set creation, parsing/chunking
quality checks, retrieval evaluation with bootstrap confidence intervals, and grounded RAG
evaluation. Run any CLI with `--help` for its exact arguments.

## Historical Ticket/Log Pipeline

Normalize tickets and logs:

```powershell
uv run koreanops-load-tickets `
  C:\vectorsearch-data\raw\tickets.csv `
  C:\vectorsearch-data\processed\tickets.jsonl `
  --source-dataset customer_support `
  --dataset-key multilingual_customer_support

uv run koreanops-load-logs `
  C:\vectorsearch-data\raw\HDFS.log `
  C:\vectorsearch-data\processed\logs.jsonl `
  --source-dataset loghub_hdfs `
  --system hdfs
```

Build and index RAG documents:

```powershell
uv run koreanops-build-docs `
  C:\vectorsearch-data\processed\documents.jsonl `
  --ticket-jsonl C:\vectorsearch-data\processed\tickets.jsonl `
  --log-jsonl C:\vectorsearch-data\processed\logs.jsonl

uv run koreanops-index-qdrant C:\vectorsearch-data\processed\documents.jsonl
uv run koreanops-index-opensearch C:\vectorsearch-data\processed\documents.jsonl
```

The current CPU-first default embedding model remains
`intfloat/multilingual-e5-small`. BGE-M3 produced only a marginal quality gain on the
10,000-chunk comparison subset while adding substantial CPU latency.

## Experiment Outputs

Primary retrieval metrics:

- Recall@5 and Recall@10
- MRR
- nDCG@10
- P50 and P95 latency
- parent/page-aware matching for chunked documents
- 95% bootstrap confidence intervals for Office PDF retrieval

RAG evaluation uses manually approved Golden questions and checks grounded answers with
document/page citations. Human-facing outputs live in `reports/`, while large generated
metrics and artifacts remain under `C:\vectorsearch-data`.

## Verification

Run before considering a code change complete:

```powershell
uv run ruff check .
uv run pytest
uv run koreanops-check-env
docker compose config
```
