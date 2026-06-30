# Data Engineering Portfolio Case Study

작성일: 2026-06-29

대상 프로젝트: KoreanOps-RAG / `ko_unstructured_v2`

데이터 루트: `C:\vectorsearch-data`

## 1. 프로젝트 개요

이 프로젝트는 IT 지원 티켓, 시스템 로그, 공공 오피스 PDF 문서를 대상으로 BM25,
dense vector search, hybrid RRF retrieval, RAG 평가를 비교하는 CPU-first 검색/RAG
실험 플랫폼이다.

데이터엔지니어링 관점의 핵심 목표는 다음과 같다.

- 원천 데이터를 Git repository와 분리해 대용량 artifact를 안정적으로 관리한다.
- raw, cleaned, mart 성격의 중간 계층을 JSONL artifact로 분리한다.
- 같은 corpus를 여러 chunking strategy로 변환하고, 각 결과를 독립 index에 적재한다.
- Qdrant와 OpenSearch의 source-target count를 검증해 검색 실험의 재현성을 확보한다.
- 실패 후 재처리, checkpoint, run manifest를 도입해 긴 indexing 작업을 복구 가능하게 만든다.

현재 프로젝트는 운영 DWH가 아니라 로컬 실험 플랫폼이다. 따라서 Airflow, PySpark, 분산
DWH는 실제 운영 구성으로 도입하지 않았고, 단일 Windows PC와 CPU 환경에 맞는 경량
pipeline runner, Typer CLI, PowerShell script, JSONL artifact, Docker Compose 기반
OpenSearch/Qdrant 구조를 우선 사용했다.

## 2. 데이터 수집

### 2.1 원천 데이터

프로젝트에서 다룬 주요 원천은 세 종류다.

| Source | 위치 | 용도 |
| --- | --- | --- |
| AI Hub 오피스 PDF ZIP | `C:\vectorsearch-data\ko-unstructured\raw` | PDF 검색/RAG 실험 corpus |
| AI Hub 라벨 JSON ZIP | `C:\vectorsearch-data\ko-unstructured\raw` | Oracle 비교, Golden Set 생성, parsing 품질 평가 |
| Ticket CSV / HDFS log | `C:\vectorsearch-data\raw` | 초기 KoreanOps ticket/log RAG baseline |

대용량 원천 파일은 repository에 commit하지 않고 `C:\vectorsearch-data` 아래에 둔다.
repository의 `data/` 디렉터리는 placeholder로만 유지한다.

### 2.2 Office PDF 수집 및 inventory

오피스 PDF 실험은 raw ZIP을 그대로 보존하고, 먼저 ZIP 내부 PDF 목록을 inventory로
생성한다.

```powershell
uv run koreanops-office-inventory `
  C:\vectorsearch-data\ko-unstructured\raw `
  C:\vectorsearch-data\ko-unstructured\processed\office_manifest.jsonl
```

`office_manifest.jsonl`은 전체 pipeline의 source-of-truth 역할을 한다.

주요 필드:

- `doc_id`: PDF, page, block, chunk, retrieval result를 연결하는 공통 문서 ID
- `split`: `training` 또는 `validation`
- `document_type`: 보고서, 보도자료, 발표자료, 행정문서 등
- `source_archive`: ZIP archive 상대 경로
- `source_member`: ZIP 내부 PDF 경로
- `file_size`: 원본 PDF 크기
- `is_valid`, `error`: inventory 단계 상태

Full run 기준 원천 크기:

| 구분 | 파일 수 | 크기 |
| --- | ---: | ---: |
| 비정형 PDF ZIP | 14 | 9,102,703,085 bytes |
| 라벨 JSON ZIP | 14 | 228,774,790 bytes |
| 전체 raw ZIP | 28 | 9,331,477,875 bytes |

## 3. Raw / Cleaned / Mart 계층

이 프로젝트는 전통적인 DWH table 대신 file-based data lake 구조를 사용한다. 포트폴리오
관점에서는 다음처럼 계층을 설명할 수 있다.

| 계층 | 실제 위치 | 대표 artifact | 역할 |
| --- | --- | --- | --- |
| Raw | `ko-unstructured\raw` | `TS_*`, `VS_*`, `TL_*`, `VL_*` ZIP | 원천 보존, 재처리 기준점 |
| Bronze manifest | `ko-unstructured\processed` | `office_manifest.jsonl` | ZIP 내부 파일 목록과 source lineage |
| Cleaned | `ko-unstructured\processed\full` | `pdf_pages_raw.jsonl`, `pdf_blocks_cleaned.jsonl`, `office_documents_normalized.jsonl` | PDF parsing, text 정규화, page/block 구조화 |
| Mart | `ko-unstructured\processed\full` | `chunks_page.jsonl`, `chunks_structure.jsonl` | 검색 index 적재용 chunk corpus |
| Evaluation mart | `ko-unstructured\eval\full` | `oracle_documents.jsonl`, `golden_questions_reviewed.jsonl` | 평가, oracle 비교, 품질 검증 |
| Serving index | `C:\vectorsearch-data\index` | Qdrant collections, OpenSearch indexes | retrieval serving layer |

Cleaned 계층은 원천 PDF를 검색 가능한 page/block/document 단위로 변환한다.

Full run 산출물:

| 단계 | 파일 | 레코드 수 | 파일 크기 |
| --- | --- | ---: | ---: |
| Manifest | `processed\office_manifest.jsonl` | 9,491 | 3,561,266 bytes |
| PDF 문서 정규화 | `processed\full\office_documents_normalized.jsonl` | 9,491 | 133,377,731 bytes |
| PDF page parsing | `processed\full\pdf_pages_raw.jsonl` | 43,614 | 133,045,382 bytes |
| PDF block parsing | `processed\full\pdf_blocks_cleaned.jsonl` | 971,236 | 417,185,629 bytes |
| Page chunks | `processed\full\chunks_page.jsonl` | 42,676 | 154,746,359 bytes |
| Structure chunks | `processed\full\chunks_structure.jsonl` | 18,789 | 144,422,171 bytes |

## 4. 변환 로직

### 4.1 PDF parsing

PDF parsing은 `PyMuPDF` 기반으로 수행한다.

주요 변환:

- ZIP을 무조건 풀지 않고 manifest를 먼저 생성해 source lineage를 고정한다.
- PDF page 단위 텍스트를 추출해 `pdf_pages_raw.jsonl`로 저장한다.
- page 내부 text block, bbox, font size, heading 후보, reading order를 추출해
  `pdf_blocks_cleaned.jsonl`로 저장한다.
- 반복 머리말, 꼬리말, 페이지 번호를 제거하고 PDF 1개당 normalized document 1개를 만든다.

Full run 품질 수치:

| 항목 | 값 |
| --- | ---: |
| 문서 수 | 9,491 |
| 페이지 수 | 43,614 |
| 텍스트 블록 수 | 971,236 |
| 정규화 문서 중 빈 content | 3 |
| 문서 레벨 parse error | 0 |

### 4.2 Chunk mart 생성

검색 품질 비교를 위해 동일한 cleaned corpus에서 여러 mart를 만든다.

| Strategy | 입력 | 생성 chunk | 설계 의도 |
| --- | --- | ---: | --- |
| Page | normalized document + page text | 42,676 | PDF page를 그대로 근거 단위로 보존 |
| Structure | normalized document + cleaned blocks | 18,789 | heading, reading order 기반 section 단위 검색 |
| Fixed | normalized document | pilot 184 | 일정 길이 baseline |
| Contextual | structure chunk + parent metadata | pilot 168 | dense retrieval용 context 보강 |
| Oracle | label JSON | pilot 644 | PDF-only parsing의 성능 상한 비교 |

Page chunk는 텍스트가 있는 PDF page 1개를 chunk 1개로 만든다. Structure chunk는
block reading order와 heading 추정값을 사용해 section 단위로 묶고, 너무 짧은 section은
인접 section과 병합한다.

각 chunk에는 다음 lineage metadata를 유지한다.

- `parent_doc_id`
- `page_start`, `page_end`
- `section_path`
- `chunk_index`
- `chunking_strategy`
- `split`
- `document_type`
- `source_archive`, `source_member`

이 구조 덕분에 retrieval 결과를 다시 원본 PDF, ZIP member, page 범위로 추적할 수 있다.

## 5. 재처리와 실패 복구

### 5.1 Run manifest와 event log

공통 `RunRecorder`를 도입해 user-facing CLI가 run manifest와 event JSONL을 남기도록 했다.

저장 위치:

```text
C:\vectorsearch-data\reports\runs
C:\vectorsearch-data\reports\checkpoints
```

run manifest에는 stage, command, config, input artifact, output artifact, started/finished
timestamp, record count, status, error message를 기록하는 방향으로 설계했다.

### 5.2 Checkpoint와 resume

Qdrant indexing은 `--resume`을 지원한다.

```powershell
uv run koreanops-index-qdrant `
  C:\vectorsearch-data\ko-unstructured\processed\full\chunks_structure.jsonl `
  --config-path experiments\ko_unstructured_v2\configs\pdf_structure.yaml `
  --resume
```

보완된 resume 검증은 point count만 보지 않고 다음 값을 함께 확인한다.

- target collection
- config path
- input artifact fingerprint

이는 입력 JSONL이 바뀌었는데 point count만 맞는 경우 잘못 이어서 indexing하는 문제를
막기 위한 장치다.

OpenSearch indexing은 같은 `doc_id`에 대해 overwrite/upsert하는 idempotent 성격이 있다.
다만 Qdrant 수준의 formal checkpoint는 아직 약하므로, 운영형 data product로 확장한다면
OpenSearch에도 stage checkpoint와 source-target count gate를 더 명시해야 한다.

## 6. Airflow DAG, Retry, Schedule 설계 판단

현재 repository에는 Airflow DAG를 실제로 두지 않았다. 이유는 명확하다.

- 단일 Windows PC에서 반복 실험하는 CPU-first 프로젝트다.
- Dockerized scheduler, metadata DB, worker 관리가 현재 규모에서는 실험 속도를 늦출 수 있다.
- 현재 필요한 것은 web scheduler보다 artifact lineage, checkpoint, row count 검증이다.

대신 Typer CLI, PowerShell runner, status JSON, run manifest를 사용한다.

운영형 pipeline으로 승격할 경우 Airflow DAG는 다음 의존성으로 설계할 수 있다.

```text
inventory
  -> parse_pdf
  -> build_page_chunks
  -> build_structure_chunks
  -> validate_chunks
  -> index_qdrant_page
  -> index_qdrant_structure
  -> index_opensearch_page
  -> index_opensearch_structure
  -> validate_source_target_counts
  -> run_retrieval_eval
  -> publish_report
```

권장 retry/schedule:

| Stage | Retry | Schedule | 비고 |
| --- | ---: | --- | --- |
| inventory | 1 | on-demand 또는 raw 도착 시 | deterministic, 빠름 |
| parse_pdf | 2 | on-demand batch | source archive 단위 실패 격리 |
| build_chunks | 1 | parse 성공 후 | pure transform, 재실행 쉬움 |
| index_qdrant | 2 | chunk mart 변경 시 | embedding 비용 큼, checkpoint 필요 |
| index_opensearch | 2 | chunk mart 변경 시 | idempotent upsert 가능 |
| validate_counts | 0 | index 후 즉시 | 실패 시 downstream 차단 |
| retrieval_eval | 1 | index 검증 후 | 평가 artifact 생성 |
| publish_report | 0 | eval 성공 후 | human-facing report |

Airflow 도입 기준은 다음과 같이 잡는다.

- 매일 또는 매주 반복 schedule이 필요하다.
- 여러 worker나 여러 machine에서 병렬 실행해야 한다.
- retry, SLA, backfill, web UI가 운영 요구사항이 된다.
- 실험 repository가 운영 data product로 승격된다.

## 7. PySpark 사용 여부와 판단

현재 프로젝트는 PySpark를 사용하지 않았다.

그 이유는 데이터와 실행 환경의 제약 때문이다.

- 현재 full run raw는 약 9.3GB이고, 핵심 mart는 수십만에서 백만 행 규모의 JSONL이다.
- 단일 Windows PC, CPU-first 환경에서 Spark runtime과 cluster-style dependency는 운영 부담이 크다.
- PDF parsing과 embedding indexing은 Spark SQL보다 Python library, batch IO, model inference 병목이 더 크다.
- 현재 단계에서는 streaming JSONL, chunked pandas/iterator, batch indexing이 더 단순하고 재현성이 높다.

대신 Spark로 전환 가능한 경계는 명확하게 유지했다.

| 현재 artifact | Spark 전환 시 DataFrame |
| --- | --- |
| `office_manifest.jsonl` | source file inventory table |
| `pdf_pages_raw.jsonl` | page-level bronze/silver table |
| `pdf_blocks_cleaned.jsonl` | block-level silver table |
| `chunks_page.jsonl`, `chunks_structure.jsonl` | retrieval mart table |
| retrieval result JSONL | evaluation fact table |

Spark를 도입한다면 다음 변환이 적합하다.

- `doc_id`, `split`, `document_type` 기준 partitioned parquet 저장
- page/block 단위 deduplication과 null/empty content validation
- chunk count, empty rate, parse error rate 집계
- source archive별 backfill 대상 산출
- retrieval result를 evaluation mart로 적재해 strategy별 metric aggregation

즉, 이 프로젝트의 현재 선택은 "PySpark를 몰라서 쓰지 않은 것"이 아니라, 단일 PC 실험
환경에서 Spark보다 JSONL + streaming + explicit index validation이 더 적합하다는 판단이다.

## 8. Source-Target Row Count 검증

검색 실험에서는 count mismatch가 품질 비교를 왜곡할 수 있으므로, source artifact와 target
index의 count를 비교한다.

### 8.1 Qdrant 검증

Full run Qdrant 검증:

| Strategy | 입력 JSONL | 입력 레코드 | Qdrant collection | live points |
| --- | --- | ---: | --- | ---: |
| Page | `chunks_page.jsonl` | 42,676 | `ko_unstructured_pdf_page` | 42,676 |
| Structure | `chunks_structure.jsonl` | 18,789 | `ko_unstructured_pdf_structure` | 18,789 |

검증 명령:

```powershell
(Invoke-RestMethod `
  "http://localhost:6333/collections/ko_unstructured_pdf_page").result.points_count
```

Qdrant에서는 `indexed_vectors_count`가 0으로 보여도 point가 없다는 뜻이 아니다. 현재 local
collection의 HNSW/vector index materialization 상태를 나타내는 값이므로 실제 검색 대상 수는
`points_count`를 기준으로 확인한다.

### 8.2 OpenSearch 검증

OpenSearch는 Qdrant와 같은 chunk JSON을 저장하고 `_id`는 chunk의 문자열 `doc_id`를 사용한다.

검증 명령:

```powershell
Invoke-RestMethod "http://localhost:9200/ko_unstructured_pdf_page/_count"
```

Pilot 100 단계에서는 모든 strategy의 JSONL chunk 수, Qdrant point 수, OpenSearch document
수가 일치했다.

| Strategy | JSONL chunks | Qdrant points | OpenSearch docs |
| --- | ---: | ---: | ---: |
| Fixed | 184 | 184 | 184 |
| Page | 644 | 644 | 644 |
| Structure | 168 | 168 | 168 |
| Contextual | 168 | 168 | 168 |
| Oracle | 644 | 644 | 644 |

Full run 문서에서는 Qdrant live count를 확정했고, OpenSearch full-run index별 live count는
API 조회가 완료된 시점에 추가 확정해야 한다.

## 9. Partition, Incremental Load, Backfill

### 9.1 현재 partition 기준

현재 명시적으로 보존하는 partition key는 다음과 같다.

- `split`: training / validation
- `document_type`: 보고서, 보도자료, 발표자료, 행정문서 등
- `chunking_strategy`: page / structure / fixed / contextual / oracle
- `source_archive`: 원천 ZIP archive

검색 serving 계층에서는 partition 대신 strategy별 namespace를 사용한다.

| Strategy | Qdrant collection | OpenSearch index |
| --- | --- | --- |
| Page | `ko_unstructured_pdf_page` | `ko_unstructured_pdf_page` |
| Structure | `ko_unstructured_pdf_structure` | `ko_unstructured_pdf_structure` |
| Fixed pilot | `ko_unstructured_pdf_fixed` | `ko_unstructured_pdf_fixed` |
| Contextual pilot | `ko_unstructured_pdf_contextual` | `ko_unstructured_pdf_contextual` |
| Oracle pilot | `ko_unstructured_pdf_oracle` | `ko_unstructured_pdf_oracle` |

이 설계는 하나의 index 안에 여러 실험 전략을 섞지 않기 위한 것이다. chunking strategy가
달라지면 문서 수, 평균 길이, retrieval latency가 달라지므로 strategy별 독립 namespace가
공정한 비교에 유리하다.

### 9.2 Incremental load

현재 full run은 batch rebuild 중심이다. 하지만 incremental load를 위해 필요한 key는 이미
있다.

- `doc_id`: document-level idempotency key
- `source_archive`, `source_member`: source file lineage
- `chunking_strategy`, `chunk_index`: mart-level idempotency key
- OpenSearch `_id = doc_id`: overwrite/upsert 가능
- Qdrant payload `doc_id`: source chunk 추적 가능

향후 incremental load는 다음 방식으로 확장할 수 있다.

1. 새 raw ZIP 또는 변경된 ZIP을 inventory에서 감지한다.
2. 변경된 `source_archive`/`source_member`만 parse한다.
3. 해당 `parent_doc_id`의 chunk만 재생성한다.
4. OpenSearch는 같은 `_id`로 upsert한다.
5. Qdrant는 `parent_doc_id` filter delete 후 재insert하거나 deterministic point id를 도입한다.
6. source-target count와 retrieval smoke test를 통과한 뒤 report를 갱신한다.

### 9.3 Backfill

Backfill은 raw ZIP과 manifest를 기준으로 재현한다.

Backfill 단위:

- 전체 corpus
- split별 backfill
- `source_archive`별 backfill
- `document_type`별 backfill
- chunking strategy별 mart 재생성

현재는 formal backfill CLI보다 script와 CLI 조합으로 처리한다. 운영형으로 확장하면
`koreanops-run-pipeline --from parse --to index --where source_archive=...` 같은 runner를
추가하는 것이 자연스럽다.

## 10. DWH 또는 OpenSearch 적재

### 10.1 현재 serving target

현재 최종 serving target은 DWH가 아니라 retrieval engine이다.

| Target | 역할 | 저장 경로 |
| --- | --- | --- |
| OpenSearch | BM25, lexical retrieval, hybrid 후보 생성 | `C:\vectorsearch-data\index\opensearch` |
| Qdrant | dense vector retrieval | `C:\vectorsearch-data\index\qdrant` |
| JSONL reports | evaluation result, run output, failure analysis | `C:\vectorsearch-data\reports`, repository `reports/` |

OpenSearch에는 Qdrant와 같은 chunk JSON을 저장한다.

현재 mapping 개념:

```json
{
  "doc_id": {"type": "keyword"},
  "source_type": {"type": "keyword"},
  "title": {"type": "text"},
  "content": {"type": "text"},
  "metadata": {"type": "object", "enabled": true}
}
```

Qdrant에는 384차원 `intfloat/multilingual-e5-small` embedding과 chunk payload를 저장한다.

| 항목 | 값 |
| --- | --- |
| Embedding model | `intfloat/multilingual-e5-small` |
| Dimension | 384 |
| Distance | Cosine |
| Device | CPU |
| Default batch size | 64 |
| Input text | `embedding_text`, 없으면 `content` |

### 10.2 DWH 관점의 해석

현재는 별도 DWH를 두지 않았지만, JSONL artifact는 DWH table로 옮기기 쉬운 형태다.

| DWH table 후보 | Source artifact | Grain |
| --- | --- | --- |
| `dim_document` | `office_manifest.jsonl` | PDF 1개 |
| `fact_pdf_page` | `pdf_pages_raw.jsonl` | PDF page 1개 |
| `fact_pdf_block` | `pdf_blocks_cleaned.jsonl` | PDF text block 1개 |
| `mart_retrieval_chunk` | `chunks_page.jsonl`, `chunks_structure.jsonl` | 검색 chunk 1개 |
| `fact_index_validation` | count validation output | index validation 1회 |
| `fact_retrieval_eval` | retrieval result JSONL | query-strategy-result 1개 |

이 구조로 DWH를 추가하면 source-target count, parse quality, retrieval metric을 SQL로 추적할 수 있다.

## 11. 고도화 과정 요약

| 단계 | 고도화 내용 | 데이터엔지니어링 의미 |
| --- | --- | --- |
| 초기 ticket/log ingestion | CSV/log를 normalized JSONL로 변환 | raw to cleaned pipeline 시작 |
| Baseline indexing | Qdrant/OpenSearch 적재 | vector/BM25 serving target 분리 |
| Field/context chunking | parent metadata 보존 chunk 생성 | mart 설계와 lineage 강화 |
| Office PDF v2 | AI Hub ZIP 기반 PDF inventory/parse/chunk | 대용량 비정형 문서 처리 확장 |
| Strategy namespace 분리 | page/structure/fixed/contextual/oracle index 분리 | 실험 간 contamination 방지 |
| Full run sizing | raw, processed, eval artifact count/size 측정 | 운영 비용과 scale 근거 확보 |
| RunRecorder/checkpoint | manifest, event log, resume 검증 | 실패 복구와 재현성 강화 |
| Count validation | JSONL record count와 target index count 비교 | source-target integrity 확보 |

## 12. 포트폴리오에서 강조할 점

이 프로젝트는 단순히 RAG demo를 만든 것이 아니라, 검색 품질 실험을 신뢰할 수 있도록
데이터 pipeline을 단계적으로 고도화한 사례다.

강조할 수 있는 점:

- raw data를 repository와 분리하고 `C:\vectorsearch-data`에 일관되게 격리했다.
- ZIP 내부 source lineage를 manifest로 고정해 재처리 기준점을 만들었다.
- PDF를 page, block, normalized document, retrieval chunk로 분해해 cleaned/mart 계층을 만들었다.
- 같은 cleaned corpus에서 여러 chunk mart를 생성하고 Qdrant/OpenSearch namespace를 분리했다.
- Qdrant point count와 JSONL record count를 맞춰 source-target 검증을 수행했다.
- long-running embedding indexing을 위해 checkpoint, resume, input artifact fingerprint 검증을 도입했다.
- Airflow와 PySpark는 현재 규모에서 의도적으로 배제하고, 도입 기준과 전환 경계를 문서화했다.

## 13. 남은 보완 과제

포트폴리오 완성도를 더 높이려면 다음 문서를 추가하면 좋다.

| 우선순위 | 보완 과제 | 이유 |
| --- | --- | --- |
| P0 | `reports/data_quality_checks.md` | parse error, empty content, chunk count, source-target count를 한 문서에 집계 |
| P0 | OpenSearch full-run `_count` 재확인 | Qdrant와 동일하게 full-run source-target 검증 완성 |
| P1 | `koreanops-run-pipeline` 또는 `scripts/run-pipeline.ps1` | Airflow 이전 단계의 lightweight orchestration 구현 |
| P1 | Backfill runbook | source archive 단위 재처리 절차 명확화 |
| P2 | DWH table proposal 또는 parquet export | 데이터엔지니어 포트폴리오에서 warehouse 관점 보강 |
| P2 | Spark migration note | PySpark 전환 기준과 DataFrame 변환 계획 명시 |

현재 상태만으로도 프로젝트는 실험 플랫폼으로 충분히 탄탄하다. 다만 데이터엔지니어
포트폴리오 제출용으로는 "Airflow/PySpark를 실제로 썼다"보다 "현재 규모에서 왜 쓰지
않았고, 어떤 기준에서 도입할 것인지"를 명확히 설명하는 편이 더 정직하고 설득력 있다.
