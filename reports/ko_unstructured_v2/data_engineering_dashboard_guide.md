# ko_unstructured_v2 Data Engineering Dashboard Guide

작성일: 2026-06-30

대상 프로젝트: KoreanOps-RAG `ko_unstructured_v2`

이 문서는 로컬 무과금 데이터 엔지니어링 스택을 어떻게 켜고, 각 대시보드에서 무엇을 확인하며, 어떤 순서로 사용하면 되는지 설명한다. 실제 AWS 계정, AWS Free Tier, 유료 리소스는 사용하지 않는다.

## 1. 전체 구성

현재 구성은 AWS를 직접 쓰지 않고 로컬 Docker로 AWS형 데이터 엔지니어링 환경을 연습하는 구조다.

| 서비스 | URL | 계정 | 역할 |
| --- | --- | --- | --- |
| Airflow | `http://localhost:8080` | `admin / admin` | DAG 실행, task 상태, 로그, 재실행 관리 |
| Spark Master | `http://localhost:8081` | 없음 | Spark application, worker, executor 상태 확인 |
| Spark Worker | `http://localhost:8082` | 없음 | worker 상태 확인 |
| MinIO Console | `http://localhost:9001` | `minioadmin / minioadmin` | 로컬 S3 호환 object storage 연습 |
| Qdrant Dashboard | `http://localhost:6333/dashboard/` | 없음 | vector collection 상태와 point count 확인 |
| OpenSearch API | `http://localhost:9200` | 없음 | BM25 index count/API 확인 |
| OpenSearch Dashboards | `http://localhost:5601` | 없음 | OpenSearch index 탐색 UI |

AWS 대응 관계는 다음처럼 이해하면 된다.

| 로컬 구성 | AWS에서 대응되는 서비스 | 이 프로젝트에서의 의미 |
| --- | --- | --- |
| MinIO | S3 | raw/processed/mart object storage 감각 연습 |
| Airflow | MWAA | DAG 기반 workflow orchestration 연습 |
| Spark | EMR 또는 Glue | JSONL to Parquet, mart 변환 연습 |
| PostgreSQL | RDS PostgreSQL | Airflow metadata DB |
| Parquet lake | S3 data lake / Athena 대상 | 분석용 processed/mart table |
| Qdrant | managed vector DB 계열 | dense vector retrieval serving |
| OpenSearch | Amazon OpenSearch Service | BM25 retrieval serving |

## 2. 켜고 끄기

데이터 엔지니어링 스택만 켠다.

```powershell
docker compose --profile data-engineering up -d `
  airflow-postgres airflow-webserver airflow-scheduler `
  spark-master spark-worker minio
```

기존 OpenSearch Dashboards는 별도 profile이다.

```powershell
docker compose --profile dashboard up -d
```

상태 확인:

```powershell
docker compose ps
```

데이터 엔지니어링 스택만 끄기:

```powershell
docker compose stop `
  airflow-postgres airflow-webserver airflow-scheduler `
  spark-master spark-worker minio
```

주의: 아래 명령은 Qdrant/OpenSearch까지 모두 멈춘다.

```powershell
docker compose stop
```

## 3. Airflow 사용법

Airflow는 파이프라인 실행 상태를 보는 주 대시보드다.

접속:

```text
http://localhost:8080
ID: admin
PW: admin
```

현재 DAG는 두 개다.

| DAG | 목적 | 주의 |
| --- | --- | --- |
| `office_pdf_etl` | v2 PDF JSONL 산출물을 Parquet/mart로 승격하고 DQ 확인 | parsing/chunking task는 기존 JSONL을 다시 만들 수 있음 |
| `retrieval_evaluation` | Qdrant/OpenSearch indexing과 retrieval/RAG 평가 실행 | indexing task는 기존 retrieval index에 write 작업을 함 |

`office_pdf_etl` task 순서:

```text
inventory
-> parse
-> build_chunks_page
-> build_chunks_structure
-> spark_jsonl_to_parquet
-> run_data_quality
-> build_mart
```

`retrieval_evaluation` task 순서:

```text
index_qdrant
index_opensearch
-> run_retrieval_eval
-> run_rag_eval
-> write_eval_mart
```

처음 보는 순서:

1. Airflow 로그인
2. DAG 목록에서 `office_pdf_etl` 클릭
3. `Graph` 또는 `Grid` 화면 확인
4. 각 task 이름을 눌러 command와 로그 위치 확인
5. 처음에는 DAG trigger 전에 CLI로 read-only DQ를 먼저 실행

안전한 첫 검증 명령:

```powershell
uv run koreanops-office-data-quality `
  --data-root C:\vectorsearch-data\ko-unstructured
```

Airflow에서 DAG 실행:

1. DAG 화면으로 이동
2. 오른쪽 위 Trigger 버튼 클릭
3. Grid 화면에서 task별 상태 확인
4. 실패 task 클릭
5. `Logs` 탭에서 실패 원인 확인

상태 색상 감각:

| 상태 | 의미 |
| --- | --- |
| Success / green | task 성공 |
| Failed / red | task 실패 |
| Running | 실행 중 |
| Queued | scheduler가 실행 대기 중 |
| Skipped | 조건상 건너뜀 |

## 4. Spark 사용법

Spark는 JSONL 파일을 Parquet으로 변환하고 mart table을 만드는 처리 엔진이다.

접속:

```text
Spark Master UI: http://localhost:8081
Spark Worker UI: http://localhost:8082
```

Spark Master UI에서 볼 것:

- Alive Workers가 1개 이상인지
- Running Applications가 있는지
- Completed Applications가 쌓이는지
- 실패 application이 있는지

JSONL을 Parquet으로 변환:

```powershell
uv run koreanops-office-jsonl-to-parquet `
  --data-root C:\vectorsearch-data\ko-unstructured
```

출력 위치:

```text
C:\vectorsearch-data\ko-unstructured\lake\processed
```

mart 생성:

```powershell
uv run koreanops-office-build-mart `
  --data-root C:\vectorsearch-data\ko-unstructured
```

출력 위치:

```text
C:\vectorsearch-data\ko-unstructured\lake\mart
```

생성되는 mart table:

| Table | 의미 |
| --- | --- |
| `dim_document` | PDF 문서 dimension |
| `fact_pdf_parse_quality` | 문서별 parsing 품질 fact |
| `fact_chunk_quality` | chunk 전략별 품질 fact |
| `fact_indexing_result` | indexing 대상과 input count fact |
| `fact_retrieval_eval` | retrieval 평가 summary fact |
| `fact_rag_eval` | RAG 평가 summary fact |

Spark UI는 CLI나 Airflow task로 Spark job이 실행될 때 가장 의미가 있다. 아무 job도 돌리지 않은 상태에서는 worker 상태만 확인하면 된다.

## 5. MinIO 사용법

MinIO는 로컬 S3 호환 저장소다. 실제 AWS S3가 아니므로 비용이 발생하지 않는다.

접속:

```text
http://localhost:9001
ID: minioadmin
PW: minioadmin
```

추천 bucket:

```text
koreanops-raw
koreanops-processed
koreanops-mart
koreanops-reports
```

현재 프로젝트의 정본 데이터는 여전히 Windows 경로다.

```text
C:\vectorsearch-data\ko-unstructured
```

MinIO는 다음 목적에 쓰면 좋다.

- S3 bucket/object 개념 연습
- raw/processed/mart zone을 object storage처럼 보는 연습
- 나중에 AWS S3로 옮길 때 path 설계를 미리 검증

처음에는 MinIO에 원본 대용량 ZIP을 복사하지 않아도 된다. 비용은 없지만 로컬 디스크를 많이 쓸 수 있다.

## 6. PostgreSQL 사용법

PostgreSQL은 Airflow 내부 metadata DB다.

용도:

- DAG run 상태 저장
- task instance 상태 저장
- Airflow 사용자와 session 저장
- scheduler metadata 저장

직접 접속해서 데이터를 분석하는 DB가 아니다. `dim_document`, `fact_chunk_quality` 같은 mart는 PostgreSQL이 아니라 Parquet으로 저장한다.

따라서 평소에는 PostgreSQL을 직접 만지지 않는다. Airflow UI가 뜨고 DAG 상태가 보이면 PostgreSQL은 정상이라고 보면 된다.

## 7. Qdrant 사용법

Qdrant는 dense vector retrieval serving layer다.

접속:

```text
http://localhost:6333/dashboard/
```

주요 collection:

```text
ko_unstructured_pdf_page
ko_unstructured_pdf_structure
```

확인할 것:

- collection이 존재하는지
- status가 green인지
- points count가 chunk input count와 맞는지
- vector size가 384인지
- distance가 Cosine인지

PowerShell 확인:

```powershell
(Invoke-RestMethod `
  "http://localhost:6333/collections/ko_unstructured_pdf_page").result.points_count

(Invoke-RestMethod `
  "http://localhost:6333/collections/ko_unstructured_pdf_structure").result.points_count
```

현재 기대 count:

| Collection | Expected points |
| --- | ---: |
| `ko_unstructured_pdf_page` | 42,676 |
| `ko_unstructured_pdf_structure` | 18,789 |

주의: Qdrant의 `indexed_vectors_count`가 0으로 보여도 point가 없다는 뜻은 아니다. 이 프로젝트에서는 live 검증 기준으로 `points_count`를 사용한다.

## 8. OpenSearch / OpenSearch Dashboards 사용법

OpenSearch는 BM25 retrieval serving layer다.

API:

```text
http://localhost:9200
```

Dashboards:

```text
http://localhost:5601
```

주요 index:

```text
ko_unstructured_pdf_page
ko_unstructured_pdf_structure
```

PowerShell count 확인:

```powershell
Invoke-RestMethod "http://localhost:9200/ko_unstructured_pdf_page/_count"
Invoke-RestMethod "http://localhost:9200/ko_unstructured_pdf_structure/_count"
```

현재 기대 count:

| Index | Expected docs |
| --- | ---: |
| `ko_unstructured_pdf_page` | 42,676 |
| `ko_unstructured_pdf_structure` | 18,789 |

Dashboards에서 처음 볼 것:

1. OpenSearch Dashboards 접속
2. Discover 또는 index management 화면 이동
3. `ko_unstructured_pdf_page`, `ko_unstructured_pdf_structure` 확인
4. 문서 field 확인
5. `content`, `metadata.parent_doc_id`, `metadata.page_start`, `metadata.page_end` 확인

단일 노드 local OpenSearch에서는 cluster/index 상태가 yellow로 보일 수 있다. replica가 배치되지 않아서 생기는 local 실험 환경의 정상적인 상태다.

## 9. Data Quality Report 사용법

DQ 리포트는 현재 v2 data lake와 retrieval index가 서로 맞는지 보는 가장 중요한 결과물이다.

문서 위치:

```text
reports\ko_unstructured_v2\data_quality_report.md
```

외부 복사본:

```text
C:\vectorsearch-data\ko-unstructured\reports\data_quality_report.md
```

다시 생성:

```powershell
uv run koreanops-office-data-quality `
  --data-root C:\vectorsearch-data\ko-unstructured
```

검증 항목:

| Check | 의미 |
| --- | --- |
| manifest count equals normalized documents count | inventory 문서 수와 normalized document 수 비교 |
| empty content document count | content가 빈 문서 수 확인 |
| duplicate chunk ids | chunk id 중복 여부 |
| chunk parent_doc_id exists | chunk가 원본 document를 참조하는지 |
| page_start <= page_end | page range 무결성 |
| Qdrant points_count equals chunk input count | vector DB 적재 수 검증 |
| OpenSearch _count equals chunk input count | BM25 index 적재 수 검증 |

현재 확인된 결과:

```text
PASS: 11
WARN: 1
FAIL: 0
```

WARN:

```text
empty content document count = 141
```

이 WARN은 DQ에서 관찰해야 할 품질 지표다. 현재 index count mismatch는 없다.

## 10. 추천 실습 순서

처음 하루는 아래 순서로 보는 것을 추천한다.

1. 전체 상태 확인

```powershell
docker compose ps
```

2. Airflow 접속

```text
http://localhost:8080
```

3. DAG 두 개 확인

```text
office_pdf_etl
retrieval_evaluation
```

4. DQ 리포트 확인

```text
reports\ko_unstructured_v2\data_quality_report.md
```

5. read-only DQ 재실행

```powershell
uv run koreanops-office-data-quality `
  --data-root C:\vectorsearch-data\ko-unstructured
```

6. Spark UI 확인

```text
http://localhost:8081
```

7. JSONL to Parquet 실행

```powershell
uv run koreanops-office-jsonl-to-parquet `
  --data-root C:\vectorsearch-data\ko-unstructured
```

8. Spark UI에서 completed application 확인

9. Mart 생성

```powershell
uv run koreanops-office-build-mart `
  --data-root C:\vectorsearch-data\ko-unstructured
```

10. MinIO Console 접속 후 bucket 구조 연습

```text
http://localhost:9001
```

## 11. 안전 규칙

- 실제 AWS 계정은 사용하지 않는다.
- AWS Free Tier도 사용하지 않는다.
- Airflow DAG는 manual trigger로만 실행한다.
- `retrieval_evaluation` DAG는 indexing task가 있으므로 신중하게 실행한다.
- 기존 Qdrant/OpenSearch index를 지우는 명령은 사용하지 않는다.
- 대용량 Parquet, MinIO object, Docker volume data는 Git에 커밋하지 않는다.
- 새 데이터 산출물은 `C:\vectorsearch-data` 아래에 둔다.

## 12. 문제 해결

Airflow가 열리지 않을 때:

```powershell
docker compose ps airflow-webserver airflow-scheduler airflow-postgres
docker compose logs --tail=100 airflow-webserver
```

Spark UI가 열리지 않을 때:

```powershell
docker compose ps spark-master spark-worker
docker compose logs --tail=100 spark-master
```

MinIO가 열리지 않을 때:

```powershell
docker compose ps minio
docker compose logs --tail=100 minio
```

Qdrant/OpenSearch count가 맞지 않을 때:

```powershell
uv run koreanops-office-data-quality `
  --data-root C:\vectorsearch-data\ko-unstructured
```

기본 Compose가 기존 검색 서비스만 포함하는지 확인:

```powershell
docker compose config --services
```

기대값:

```text
opensearch
qdrant
```

data-engineering profile 서비스 확인:

```powershell
docker compose --profile data-engineering config --services
```

기대값에는 아래 서비스가 포함된다.

```text
airflow-postgres
airflow-scheduler
airflow-webserver
minio
spark-master
spark-worker
```

OpenSearch Dashboards는 별도 profile이다.

```powershell
docker compose --profile dashboard config --services
```

기대값:

```text
opensearch
opensearch-dashboards
qdrant
```

