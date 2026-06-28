# ko_unstructured_v2 Data Processing Spec v2

작성일: 2026-06-28
대상 프로젝트: `ko_unstructured_v2`
데이터 루트: `C:\vectorsearch-data\ko-unstructured`

이 문서는 AI Hub `18.오피스 문서 생성 데이터`를 PDF 검색/RAG 실험용 데이터로 변환한
현재 full run 기준 데이터 처리 스펙이다. 수치는 로컬 산출물 파일을 2026-06-28에 직접
집계한 값이다.

## 1. 데이터 구분

| 구분 | 위치 | 파일 수 | 크기 |
| --- | --- | ---: | ---: |
| 비정형 원천 PDF ZIP | `C:\vectorsearch-data\ko-unstructured\raw`의 `TS_*`, `VS_*` ZIP | 14 | 9,102,703,085 bytes |
| 정형 라벨 JSON ZIP | `C:\vectorsearch-data\ko-unstructured\raw`의 `TL_*`, `VL_*` ZIP | 14 | 228,774,790 bytes |
| 전체 raw ZIP | `C:\vectorsearch-data\ko-unstructured\raw` | 28 | 9,331,477,875 bytes |

비정형 PDF ZIP은 정형 라벨 JSON ZIP보다 약 39.8배 크다.

Split별 raw 크기:

| Split | 구분 | ZIP 수 | 크기 |
| --- | --- | ---: | ---: |
| Training | PDF 원천 | 7 | 7,536,756,794 bytes |
| Training | 라벨 JSON | 7 | 208,027,485 bytes |
| Validation | PDF 원천 | 7 | 1,565,946,291 bytes |
| Validation | 라벨 JSON | 7 | 20,747,305 bytes |

검색/RAG 운영 코퍼스는 PDF에서 파싱한 비정형 텍스트만 사용한다. 라벨 JSON은 Oracle 비교,
Golden Set 생성, 파싱 품질 평가에만 사용하며 최종 PDF-only 검색 코퍼스에는 섞지 않는다.

## 2. Full Run 산출물 요약

| 단계 | 파일 | 레코드 수 | 파일 크기 | 평균 본문 길이 |
| --- | --- | ---: | ---: | ---: |
| Manifest | `processed\office_manifest.jsonl` | 9,491 | 3,561,266 bytes | - |
| PDF 문서 정규화 | `processed\full\office_documents_normalized.jsonl` | 9,491 | 133,377,731 bytes | 2,981.5 chars |
| PDF page 파싱 | `processed\full\pdf_pages_raw.jsonl` | 43,614 | 133,045,382 bytes | 647.3 chars |
| PDF block 파싱 | `processed\full\pdf_blocks_cleaned.jsonl` | 971,236 | 417,185,629 bytes | 27.2 chars |
| Page chunks | `processed\full\chunks_page.jsonl` | 42,676 | 154,746,359 bytes | 661.5 chars |
| Structure chunks | `processed\full\chunks_structure.jsonl` | 18,789 | 144,422,171 bytes | 1,505.0 chars |
| Oracle documents | `eval\full\oracle_documents.jsonl` | 9,491 | 106,367,873 bytes | 2,450.3 chars |
| Oracle pages | `eval\full\oracle_pages.jsonl` | 43,614 | 105,535,933 bytes | 531.7 chars |
| Oracle elements | `eval\full\oracle_elements.jsonl` | 280,946 | 253,405,712 bytes | 160.1 chars |
| Golden candidates | `eval\full\golden_questions_candidates.jsonl` | 300 | 289,268 bytes | - |
| Golden reviewed | `eval\full\golden_questions_reviewed.jsonl` | 300 | 307,387 bytes | - |

Top-level 산출물 크기:

| 위치 | 파일 수 | 크기 |
| --- | ---: | ---: |
| `raw` | 28 | 9,331,477,875 bytes |
| `processed` | 132 | 1,683,949,420 bytes |
| `eval` | 38 | 478,189,185 bytes |
| `reports` | 18 | 110,343 bytes |
| `Sample` | 265 | 30,961,906 bytes |

## 3. 문서 유형 분포

Manifest와 정규화 문서는 같은 9,491개 문서를 가진다.

| 문서 유형 | 문서 수 |
| --- | ---: |
| 보고서(설명형) | 2,714 |
| 보고서(목록형) | 2,614 |
| 보도자료(보도자료) | 1,475 |
| 보도자료(뉴스기사) | 925 |
| 발표자료 | 839 |
| 행정문서(결재형) | 462 |
| 행정문서(계약형) | 462 |

## 4. 파싱 스펙

PDF 파싱은 `PyMuPDF` 기반으로 수행한다.

주요 산출물:

- `office_manifest.jsonl`: ZIP 내부 PDF 목록, split, 문서 유형, 원천 ZIP/member 경로, 파일 크기
- `pdf_pages_raw.jsonl`: PDF 페이지 단위 텍스트와 페이지 크기
- `pdf_blocks_cleaned.jsonl`: 페이지 내부 텍스트 블록, bbox, font size, heading 추정값, reading order
- `office_documents_normalized.jsonl`: PDF 1개당 RAG 공통 문서 1개

Full run 결과:

- 문서: 9,491개
- 페이지: 43,614개
- 텍스트 블록: 971,236개
- 정규화 문서 중 빈 content: 3개
- 문서 레벨 parse error: 0개

## 5. 청킹 스펙

현재 full retrieval 비교에 사용한 최종 청킹 전략은 Page와 Structure다.

| 전략 | 입력 | 생성 청크 수 | 부모 문서 수 | 평균 content 길이 | JSONL 크기 |
| --- | --- | ---: | ---: | ---: | ---: |
| Page | `office_documents_normalized.jsonl` + `pdf_pages_raw.jsonl` | 42,676 | 9,351 | 661.5 chars | 154,746,359 bytes |
| Structure | `office_documents_normalized.jsonl` + `pdf_blocks_cleaned.jsonl` | 18,789 | 9,350 | 1,505.0 chars | 144,422,171 bytes |

Page 청크는 텍스트가 있는 PDF 페이지 1개를 청크 1개로 사용한다. 빈 페이지는 검색 청크로 만들지 않는다.

Structure 청크는 block reading order와 heading 추정값을 사용해 섹션 단위로 묶는다. 너무 짧은
section은 인접 section과 병합하고, 청크에는 `parent_doc_id`, `page_start`, `page_end`,
`section_path`, `chunk_index`, `chunking_strategy`를 저장한다.

청크별 문서 유형 분포:

| 문서 유형 | Page chunks | Structure chunks |
| --- | ---: | ---: |
| 보고서(설명형) | 9,365 | 6,978 |
| 보고서(목록형) | 11,575 | 5,977 |
| 보도자료(보도자료) | 4,153 | 2,012 |
| 보도자료(뉴스기사) | 1,859 | 1,015 |
| 발표자료 | 14,040 | 1,766 |
| 행정문서(결재형) | 497 | 469 |
| 행정문서(계약형) | 1,187 | 572 |

## 6. Vector DB 스펙

Embedding 모델:

- 모델: `intfloat/multilingual-e5-small`
- 벡터 차원: 384
- 거리 함수: Cosine
- 실행 장치: CPU
- 기본 batch size: 64
- 입력 텍스트: `embedding_text`, 없으면 `content`

Qdrant collection은 청킹 전략별로 분리한다.

| 전략 | Qdrant collection | 입력 JSONL | live point 수 | collection status | indexed_vectors_count | 로컬 Qdrant 저장소 크기 |
| --- | --- | --- | ---: | --- | ---: | ---: |
| Page | `ko_unstructured_pdf_page` | `chunks_page.jsonl` | 42,676 | green | 0 | 655,471,835 bytes |
| Structure | `ko_unstructured_pdf_structure` | `chunks_structure.jsonl` | 18,789 | green | 0 | 654,970,207 bytes |
| Fixed pilot | `ko_unstructured_pdf_fixed` | pilot fixed chunks | 184 | green | 0 | 553,917,202 bytes |
| Contextual pilot | `ko_unstructured_pdf_contextual` | pilot contextual chunks | 168 | green | 0 | 553,916,866 bytes |
| Oracle pilot 비교용 | `ko_unstructured_pdf_oracle` | pilot Oracle chunks | 644 | green | 0 | 621,034,701 bytes |

Qdrant live count는 2026-06-28에 `http://localhost:6333/collections/{collection}` API로
확인했다. Page와 Structure collection의 live point 수는 최종 인덱싱 입력 JSONL 레코드 수와
일치한다.

`indexed_vectors_count`는 모든 `ko_unstructured_pdf_*` collection에서 0으로 표시된다. 이 값은
point가 없다는 뜻이 아니라 현재 local Qdrant collection의 HNSW/vector index materialization
상태를 나타내는 값이다. 실제 검색 대상 수는 `points_count`를 기준으로 본다.

이론상 순수 float32 벡터 메모리만 계산하면 다음과 같다.

| 전략 | 벡터 수 | 차원 | 순수 벡터 크기 |
| --- | ---: | ---: | ---: |
| Page | 42,676 | 384 | 약 62.5 MiB |
| Structure | 18,789 | 384 | 약 27.5 MiB |

실제 Qdrant 저장소는 payload JSON, segment, WAL, 인덱스/메타데이터가 포함되므로 순수 벡터
크기보다 훨씬 크다.

## 7. OpenSearch/BM25 스펙

OpenSearch에는 Qdrant와 같은 청크 JSON을 저장한다.

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

BM25 검색은 기본적으로 `content` 필드를 사용한다. 로컬 OpenSearch 저장소 전체 크기는
`C:\vectorsearch-data\index\opensearch` 기준 369,535,571 bytes였지만, 2026-06-28 확인 시점에
OpenSearch API 조회는 수행하지 못했으므로 index별 live document count는 문서에 확정하지 않는다.

## 8. 평가 데이터

Full Golden Set:

- 후보 질문: `eval\full\golden_questions_candidates.jsonl`, 300개
- 리뷰 결과: `eval\full\golden_questions_reviewed.jsonl`, 300개
- 리뷰 기준 통과/탈락 집계는 `reports\ko_unstructured_v2\full_golden_set_review.md`를 참고한다.

주요 full retrieval 결과 문서:

- `reports\ko_unstructured_v2\full_retrieval_experiment.md`
- `reports\ko_unstructured_v2\retrieval_experiment.md`
- `reports\ko_unstructured_v2\rag_evaluation.md`

## 9. 기존 문서와 관계

기존 스키마 초안:

- `reports\ko_unstructured_v2\data_parsing_chunking_vector_schema_v1.md`

위 v1 문서는 파싱/청킹/vector schema 설계를 설명하지만, 현재 환경에서는 한글이 깨져 보이고
pilot 중심 수치가 포함되어 있다. 현재 full run 데이터 크기, 청크 수, 벡터 저장소 크기는 이 v2
문서를 기준으로 본다.
