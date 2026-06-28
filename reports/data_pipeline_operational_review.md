# Data Pipeline Operational Review

Date: 2026-06-27

Scope: KoreanOps-RAG repository as a local, CPU-first Hybrid RAG experiment platform.

## Implementation Update

2026-06-28 보완:

- 공통 `RunRecorder`와 artifact fingerprint helper를 추가했다.
- `koreanops-load-tickets`, `koreanops-index-qdrant`, `koreanops-index-opensearch`가
  `C:\vectorsearch-data\reports\runs` 아래에 run manifest와 events JSONL을 남긴다.
- Qdrant/OpenSearch indexing은 `C:\vectorsearch-data\reports\checkpoints` 아래에 checkpoint를
  기록한다.
- Qdrant `--resume`은 기존 checkpoint가 있을 경우 collection, config path, input artifact
  fingerprint가 현재 실행과 맞는지 확인한다.
- ticket CSV ingestion은 전체 list 누적 대신 generator streaming으로 동작한다.
- `koreanops-check-env`는 cache path가 `DATA_ROOT` 밖이거나 unset인 경우, service URL이
  local-only가 아닌 경우, OpenSearch security-disabled local boundary를 경고한다.

## Executive Summary

현재 프로젝트는 연구/실험용 데이터 파이프라인으로는 충분히 구조화되어 있다. 데이터는
`C:\vectorsearch-data`로 분리되어 있고, Typer CLI, JSONL 중간 산출물, Pydantic schema,
Qdrant/OpenSearch 분리, 평가 리포트가 갖춰져 있다.

다만 운영형 데이터 플랫폼 관점에서는 아직 부족한 부분이 있다. 특히 공통 structured
logging, run manifest, stage별 lineage, 실패 원인 추적, 대규모 평가셋용 streaming 처리,
워크플로우 오케스트레이션 표준화는 보완 대상이다.

Airflow 같은 대형 오케스트레이터는 현재 규모에서는 필수는 아니다. 단일 Windows PC에서
실험을 반복하는 현재 단계에서는 PowerShell runner와 status JSON을 정비하는 편이 더
경제적이다.

## Priority Improvements

### P0. Add Run Manifest And Structured Stage Logging

현재 상태:

- 일부 PowerShell full-run script는 `*.log`와 `*_status.json`을 남긴다.
- Python CLI는 대부분 `typer.echo()` 기반 진행 메시지에 의존한다.
- run 단위 식별자인 `run_id`, stage별 input/output artifact, config snapshot, elapsed time이
  일관되게 저장되지 않는다.

보완 내용:

- 모든 user-facing CLI 시작 시 `run_id`를 생성하거나 인자로 받는다.
- `C:\vectorsearch-data\reports\runs\<run_id>.json`에 stage manifest를 저장한다.
- 각 stage별로 아래 필드를 기록한다.
  - `run_id`
  - `stage`
  - `command`
  - `config_path`
  - `input_paths`
  - `output_paths`
  - `started_at`
  - `finished_at`
  - `elapsed_ms`
  - `record_count`
  - `status`
  - `error_type`
  - `error_message`

필요 이유:

- 긴 indexing, PDF parsing, LLM-based golden set generation 중 실패 지점을 빠르게 찾을 수 있다.
- 같은 config로 재실행했는지 확인할 수 있다.
- 실험 보고서에 사용한 artifact의 출처를 추적할 수 있다.

권장 구현:

- `src/koreanops_rag/observability.py` 또는 `src/koreanops_rag/pipeline/run_manifest.py` 추가
- `logging` module을 사용하되, 파일 출력은 JSONL 형식 권장
- PowerShell status JSON과 Python manifest가 같은 schema를 쓰도록 정리

### P1. Make Pipeline Stages Explicit And Restartable

현재 상태:

- Office PDF full parse script는 batch 단위 처리와 status JSON을 제공한다.
- Qdrant indexing은 `--resume`을 지원한다.
- 일부 단계는 output 존재 여부 또는 point count 기반으로 재시작한다.

보완 내용:

- stage별 checkpoint 파일을 표준화한다.
- Qdrant resume은 point count만 보지 말고 input artifact hash와 collection name도 같이 확인한다.
- OpenSearch indexing에도 `--resume` 또는 idempotent overwrite 전략을 명시한다.
- batch 실패 시 실패 batch, source file, exception summary를 별도 error JSONL로 남긴다.

필요 이유:

- `point_count`만으로 resume하면 입력 JSONL이 바뀐 경우 잘못 이어질 수 있다.
- 대규모 PDF parsing과 embedding indexing은 실패 후 부분 재시작이 가장 중요하다.

권장 구현:

- `C:\vectorsearch-data\reports\checkpoints\<stage>.json`
- `input_sha256`, `config_sha256`, `completed_batches`, `failed_batches`
- batch output은 이미 존재하는 `batches/` 구조를 유지

### P2. Convert Remaining Large-Data Paths To True Streaming

현재 상태:

- JSONL reader/writer는 streaming 형태다.
- PDF parsing은 batch 처리된다.
- ticket loader는 `pd.read_csv(..., chunksize=...)`를 쓰지만 내부에서 list에 누적 후 반환한다.
- 평가/golden set 생성 일부는 `list(read_jsonl(...))`로 전체 파일을 메모리에 올린다.

보완 내용:

- `load_tickets.iter_tickets()`가 list 대신 iterator를 yield하도록 수정한다.
- 평가셋이 커질 경우 retrieval detail rows를 streaming write하고 summary만 집계한다.
- golden set generation은 현재 300문항 규모에서는 괜찮지만, 수천 문항 이상이면 문서 전체
  preload를 줄이는 방식으로 바꾼다.

필요 이유:

- 현재 실험 규모에서는 문제가 작지만, 100,000+ record나 대형 PDF corpus로 확장하면 메모리
  사용량이 급격히 증가할 수 있다.

권장 구현:

- ingestion 단계부터 generator 유지
- evaluation detail CSV는 stage 진행 중 append
- summary 통계는 online aggregation 또는 bounded in-memory aggregation 사용

### P3. Add Lightweight Workflow Runner Before Airflow

현재 상태:

- Airflow, Prefect, Dagster, Luigi 같은 workflow manager는 없다.
- 대신 Typer CLI와 PowerShell scripts가 단계별 실행을 담당한다.
- `pyproject.toml`에 user-facing CLI entrypoint가 잘 나뉘어 있다.

판단:

- 현재 규모에서는 Airflow는 과하다.
- Dockerized scheduler, metadata DB, DAG authoring, worker 관리가 오히려 실험 속도를 늦출 수 있다.
- 먼저 작은 runner가 적합하다.

보완 내용:

- `scripts/run-pipeline.ps1` 또는 `koreanops-run-pipeline` CLI를 둔다.
- pipeline spec YAML을 읽어 stage 순서, command, input, output, skip condition을 실행한다.
- 실패 시 manifest와 status JSON을 업데이트한다.

권장 spec 예시:

```yaml
name: office_pdf_structure_retrieval
stages:
  - name: inventory
    command: koreanops-office-inventory
  - name: parse
    command: scripts/run-office-full-parse.ps1
  - name: chunk_structure
    command: koreanops-office-build-chunks
  - name: index_qdrant
    command: koreanops-index-qdrant
  - name: index_opensearch
    command: koreanops-index-opensearch
  - name: evaluate_retrieval
    command: koreanops-office-eval-retrieval
```

Airflow 도입 기준:

- 매일/매주 자동 스케줄링이 필요하다.
- 여러 머신이나 여러 작업자가 동시에 돈다.
- retry, SLA, backfill, web UI가 필요하다.
- 실험이 아니라 운영 데이터 제품으로 승격된다.

### P4. Add Data Quality Gates

현재 상태:

- unit tests와 평가 리포트가 있다.
- parsing, chunking, retrieval, RAG evaluation command가 존재한다.
- Golden Set review workflow가 일부 존재한다.

보완 내용:

- stage마다 최소 품질 조건을 둔다.
- 예:
  - parsed documents count > 0
  - parse error rate <= threshold
  - empty content rate <= threshold
  - chunk count within expected range
  - Qdrant point count == input row count
  - OpenSearch document count == input row count
  - retrieval Recall@10 does not regress beyond tolerance

필요 이유:

- 실험 결과가 나빠졌을 때 retrieval logic 문제인지, parsing/chunking 품질 문제인지 분리할 수 있다.

권장 구현:

- `koreanops-validate-artifacts`
- `reports/data_quality_checks.md` 또는 `C:\vectorsearch-data\reports\data_quality_checks.json`

### P5. Improve Security Boundaries For Local Services

현재 상태:

- OpenSearch security plugin is disabled for local experiments.
- `.env.example` includes default local OpenSearch credentials.
- Qdrant, OpenSearch, Ollama are expected to run on localhost/local Docker.
- Raw datasets, generated indexes, model caches, and large artifacts are kept outside Git.

보완 내용:

- README 또는 별도 security note에 "local-only, do not expose ports externally" 명시
- Docker ports are bound for local development only; firewall/public network exposure is prohibited.
- `.env` should not be committed.
- real API keys or private data should never be written into reports, logs, or sample configs.
- LLM prompts may contain source document text, so provider boundary must stay local unless explicitly configured.

필요 이유:

- OpenSearch security plugin disabled 상태에서 외부 네트워크에 노출되면 index 내용이 보호되지 않는다.
- RAG pipeline logs can accidentally contain document text or generated answer content.

권장 구현:

- `reports/security_and_data_governance.md` 또는 README section 추가
- `koreanops-check-env`에 warning 추가:
  - OpenSearch security disabled
  - service URLs not localhost
  - model cache path outside `C:\vectorsearch-data`

## Implemented Data Pipeline Capabilities

### Environment And Artifact Isolation

구현됨:

- Python 3.11 64-bit `.venv` 사용 전제
- `uv run ...` 기반 실행
- large data, indexes, generated artifacts, model caches are stored under `C:\vectorsearch-data`
- repository-local `data/` directories are placeholders
- `scripts/project-env.ps1` sets:
  - `DATA_ROOT`
  - `HF_HOME`
  - `SENTENCE_TRANSFORMERS_HOME`
  - `TORCH_HOME`
  - `OLLAMA_MODELS`

평가:

- 실험 재현성과 PC-local storage 분리 관점에서 좋은 구조다.
- OneDrive-backed repo에 대형 파일을 넣지 않는 점도 적절하다.

### Ingestion

구현됨:

- Ticket CSV ingestion
- Log ingestion
- Office PDF inventory
- Office PDF parsing from archives
- AI Hub label JSON은 production corpus가 아니라 evaluation Oracle 용도로 분리

평가:

- source별 schema를 분리하고 JSONL로 normalization하는 방향은 좋다.
- ticket ingestion의 list accumulation은 streaming으로 보완하는 것이 좋다.

### Transformation And Chunking

구현됨:

- ticket/log to RAG document conversion
- fixed/page/structure/contextual/oracle chunk variants
- contextual chunking with parent metadata repeated in embedding text
- separate experiment configs for v1 ticket/log and v2 office PDF

평가:

- 여러 chunking strategy를 같은 schema로 비교할 수 있게 만든 점이 강점이다.
- strategy별 output, Qdrant collection, OpenSearch index를 분리하는 방식도 좋다.

### Indexing

구현됨:

- Qdrant vector indexing
- OpenSearch BM25 indexing
- separate Qdrant collections and OpenSearch indexes by experiment/config
- Qdrant `--resume`
- CPU-first embedding config with model, batch size, device

평가:

- indexing 재시작 지원은 중요한 장점이다.
- OpenSearch side에는 resume/checkpoint 성격이 약하므로 보완 대상이다.
- Qdrant resume은 input 변경 감지 없이 point count 기반이라는 한계가 있다.

### Retrieval And Evaluation

구현됨:

- BM25 retrieval
- dense vector retrieval
- Hybrid RRF retrieval
- weighted Hybrid evaluation
- parent-aware and page-aware retrieval evaluation
- metrics:
  - Recall@5
  - Recall@10
  - MRR
  - nDCG@10
  - latency p50/p95
  - bootstrap confidence interval for Office PDF retrieval

평가:

- 실험 플랫폼의 핵심 기능은 잘 구현되어 있다.
- evaluation set이 커질 경우 detail row streaming과 summary aggregation 개선이 필요하다.

### RAG And LLM Boundary

구현됨:

- LLM provider abstraction under `src/koreanops_rag/rag/`
- Ollama local provider
- answer generation module
- RAG smoke/evaluation commands

평가:

- LLM call boundary를 provider interface 뒤에 둔 점은 좋다.
- 외부 LLM provider를 추가할 경우 prompt/data leakage 방지 정책이 필요하다.

### Reporting

구현됨:

- human-facing reports under `reports/`
- large generated metrics and artifacts under `C:\vectorsearch-data`
- project progress/status files
- vector quality diagnosis and retrieval experiment reports

평가:

- 실험 기록은 잘 남기고 있다.
- machine-readable run manifest가 추가되면 보고서의 근거 추적성이 더 좋아진다.

## Security And Governance Review

### Implemented Safeguards

- Raw datasets and large generated artifacts are not committed.
- Model/cache paths are redirected away from arbitrary user-profile folders.
- Qdrant/OpenSearch data directories are under `C:\vectorsearch-data\index`.
- Ollama model directory is controlled by `scripts/project-env.ps1` and
  `scripts/start-ollama-project.ps1`.
- LLM integration is isolated through provider interfaces.
- Office PDF labels are explicitly treated as evaluation-only Oracle data.

### Current Risks

- OpenSearch security plugin is disabled, which is acceptable only for local experiments.
- Default `admin/admin` values appear in sample config/defaults.
- Logs and reports may contain document text, generated answers, or evidence snippets.
- Docker service ports are exposed on the host. They must not be exposed to public networks.
- No automated check currently blocks model caches from falling back to user-profile paths if the
  environment is not loaded.

### Recommended Guardrails

- Keep `.env` untracked and do not store real secrets in repo files.
- Treat generated logs/reports as potentially sensitive if source documents are private.
- Keep Qdrant/OpenSearch/Ollama bound to local machine or trusted private network only.
- Add `koreanops-check-env` checks for service URLs and cache paths.
- Add a README warning that disabled OpenSearch security is a local-only experiment setting.

## Resource Efficiency Review

### Positive Design Choices

- CPU-first default device.
- Configurable embedding batch size.
- OpenSearch heap limited to 2 GB.
- Model/cache/data directories under `C:\vectorsearch-data`.
- Qdrant resume for long embedding runs.
- Deterministic subset experiment for expensive embedding model comparison.
- Avoiding full BGE-M3 scaling unless quality gain justifies CPU cost.

### Potential Overhead Sources

- Hybrid retrieval calls both BM25 and vector retrievers, so it naturally adds latency.
- BGE-M3 has significantly higher CPU latency than `intfloat/multilingual-e5-small`.
- Field/contextual chunking increases candidate space and index size.
- Evaluation scripts that hold all rows in memory can grow expensive with larger evaluation sets.
- Qdrant resume by point count still scans skipped input rows.
- LLM-based Golden Set generation is slow and can hold long document/page text in memory.

## Recommended Roadmap

### Near Term

1. Add common run manifest and structured JSONL logging.
2. Standardize status/checkpoint files across PowerShell scripts and Python CLIs.
3. Convert ticket ingestion to true streaming.
4. Add environment/security warnings to `koreanops-check-env`.
5. Document local-only security boundary in README or a dedicated security report.

### Medium Term

1. Add lightweight pipeline runner before considering Airflow.
2. Add artifact validation gates after parse/chunk/index/eval.
3. Add OpenSearch indexing checkpoint/idempotency documentation.
4. Add regression thresholds for retrieval metrics.
5. Add summarized run history table under `C:\vectorsearch-data\reports`.

### Later

1. Consider Prefect/Dagster/Airflow only if recurring scheduled execution becomes necessary.
2. Add MLflow or a simple experiment registry if many model/config runs need comparison.
3. Add remote artifact storage only if the project moves beyond a single local PC.

## Final Assessment

현재 프로젝트는 실험 플랫폼으로는 탄탄하다. 특히 데이터/모델/인덱스를 repo 밖에 두고,
CLI 단계를 분리하고, Qdrant/OpenSearch 양쪽 검색을 비교하며, latency와 retrieval quality를
같이 측정하는 점이 좋다.

가장 먼저 보완해야 할 것은 Airflow 도입이 아니라 관측성과 재현성이다. run manifest,
structured logging, checkpoint, data quality gate가 갖춰지면 현재 규모의 실험 속도를 해치지
않으면서도 운영형 데이터 파이프라인에 가까워진다.
