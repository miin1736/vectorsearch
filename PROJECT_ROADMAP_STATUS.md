# KoreanOps-RAG Roadmap Status

Last updated: 2026-06-01

## Current Status Summary

The project scaffold is implemented and verified. The repository now has a Python package,
configuration files, Docker Compose infrastructure, ingestion/document-building logic,
retrieval/evaluation core modules, LLM provider abstraction, report templates, and unit tests.

Current blockers before real experiments:

- Docker Desktop daemon is now running.
- Ollama is installed and the local model has been pulled.
- Real Kaggle/LogHub datasets have not been downloaded into `C:\vectorsearch-data\raw`.
- Kaggle authentication is not configured, so the first smoke run used a public Hugging Face
  ticket CSV mirror plus LogHub HDFS sample data.

## Environment Checklist

- [x] Git repository initialized
- [x] `uv` detected
- [x] Python 3.11 64-bit environment created through `uv`
- [x] `C:\vectorsearch-data` created
- [x] Docker CLI detected
- [x] Docker Compose config validates
- [x] Docker Desktop daemon running
- [x] Qdrant container running
- [x] OpenSearch container running
- [x] Ollama installed
- [x] Ollama model pulled
- [x] Ollama model stored under `C:\vectorsearch-data\models\ollama`
- [x] Ollama local generation smoke test passed
- [x] Qdrant upgraded to `v1.18.0` to match `qdrant-client`
- [x] Model/cache directories created under `C:\vectorsearch-data`
- [x] Project environment script added: `scripts/project-env.ps1`

## Week 1: Environment And Data Pipeline

- [x] Project package scaffold
- [x] `pyproject.toml` with CLI commands
- [x] `.env.example`
- [x] `configs/default.yaml`
- [x] `configs/ticket_columns.yaml`
- [x] Docker Compose for Qdrant and OpenSearch
- [x] Environment check command: `koreanops-check-env`
- [x] Standard `Ticket` schema
- [x] Standard `LogRecord` schema
- [x] Standard `RagDocument` schema
- [x] JSONL streaming utilities
- [x] Text cleaning utilities
- [x] Kaggle-style ticket loader
- [x] LogHub-style log loader
- [x] Ticket/log to RAG document builder
- [x] Download public ticket CSV mirror
- [x] Download LogHub HDFS sample dataset
- [x] Run smoke pipeline with 1,000 ticket records and 1,000 log records
- [ ] Run medium pipeline with 10,000 records
- [ ] Run target pipeline with 100,000+ records
- [ ] Write EDA notes

## Week 2: Indexing And Retrieval Comparison

- [x] Qdrant indexing command scaffold
- [x] OpenSearch indexing command scaffold
- [x] BM25 retriever scaffold
- [x] Qdrant vector retriever scaffold
- [x] Hybrid retriever scaffold
- [x] RRF fusion implementation
- [x] Metadata filter support scaffold
- [x] Retrieval metric functions
- [x] Sample eval questions file
- [x] Start Qdrant/OpenSearch containers
- [x] Index smoke documents into Qdrant
- [x] Index smoke documents into OpenSearch
- [x] Verify sample vector query
- [x] Verify sample BM25 query
- [x] Verify sample hybrid query
- [ ] Build real retrieval eval set
- [x] Run BM25 smoke evaluation
- [x] Run vector smoke evaluation
- [x] Run hybrid smoke evaluation
- [ ] Add reranker experiment
- [x] Generate `retrieval_metrics_smoke.csv`
- [ ] Generate full `retrieval_metrics.csv`
- [ ] Draft retrieval results section in experiment report

## Week 3: RAG, RAGAS, And Final Report

- [x] LLM provider interface
- [x] Ollama provider scaffold
- [x] Mock provider for tests
- [x] RAG prompt builder
- [x] Answer generator scaffold
- [x] Experiment report template
- [x] Failure analysis template
- [ ] Install Ollama
- [ ] Pull 7B/8B quantized instruct model
- [x] Run local LLM smoke test
- [x] Generate RAG answer for a sample hybrid query
- [ ] Implement RAGAS runner
- [ ] Build stratified RAGAS sample set, target 100-300 questions
- [ ] Run RAGAS faithfulness
- [ ] Run RAGAS answer relevancy
- [ ] Run RAGAS context precision
- [ ] Run RAGAS context recall
- [ ] Generate `ragas_metrics.csv`
- [ ] Complete `reports/failure_analysis.md`
- [ ] Complete `reports/experiment_report.md`
- [ ] Finalize README with actual results

## Verification Status

- [x] `uv run pytest`: 9 tests passed
- [x] `uv run ruff check .`: passed
- [x] `docker compose config`: passed
- [x] `uv run koreanops-check-env`: passed with expected warnings
- [ ] Integration tests against Qdrant/OpenSearch
- [ ] End-to-end smoke run from raw data to documents
- [x] End-to-end smoke run from raw data to documents
- [x] End-to-end indexing run
- [x] End-to-end smoke retrieval evaluation run

## Immediate Next Actions

1. Create a larger real retrieval evaluation set under `C:\vectorsearch-data\eval`.

```powershell
2. Run medium scale processing with 10,000 ticket records and all available HDFS sample logs.

```powershell
. .\scripts\project-env.ps1
```

3. Re-run indexing and retrieval evaluation.

4. Add RAGAS runner and evaluate 100-300 stratified samples after retrieval metrics are stable.

```powershell
.\scripts\start-ollama-project.ps1
ollama list
```

3. Put source datasets into:

```text
C:\vectorsearch-data\raw
```

4. Run the 1,000-record smoke pipeline before attempting the 100,000+ target run.
