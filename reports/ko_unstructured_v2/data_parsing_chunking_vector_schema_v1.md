# 한국어 오피스 PDF 파싱·청킹·Vector DB 스키마 설계서 v1

작성일: 2026-06-25  
대상 프로젝트: `ko_unstructured_v2`  
대상 데이터: AI Hub `18.오피스 문서 생성 데이터`

## 1. 문서 목적

이 문서는 PDF 원본이 검색 가능한 청크로 변환되는 과정과 각 단계의 데이터 구조,
청킹 전략, Qdrant 및 OpenSearch 적재 스키마를 정의한다.

핵심 원칙은 다음과 같다.

- 검색 코퍼스는 PDF만 사용해 생성한다.
- AI Hub 라벨 JSON은 Oracle 평가와 Golden Set 생성에만 사용한다.
- 파싱 결과, 청크, 인덱스는 동일한 `doc_id`와 `parent_doc_id`로 추적 가능해야 한다.
- 청킹 전략별 인덱스를 분리하여 같은 질문으로 공정하게 비교한다.
- 원문 정보와 페이지 위치를 보존하여 검색 결과를 PDF 근거로 역추적할 수 있게 한다.

## 2. 전체 데이터 흐름

```text
PDF ZIP
  |
  v
office_manifest.jsonl
  |
  v
PyMuPDF PDF 파싱
  |
  +--> pdf_pages_raw.jsonl
  +--> pdf_blocks_cleaned.jsonl
  +--> office_documents_normalized.jsonl
           |
           +--> chunks_fixed.jsonl
           +--> chunks_page.jsonl
           +--> chunks_structure.jsonl
           +--> chunks_contextual.jsonl
                       |
                       +--> Qdrant: dense vector search
                       +--> OpenSearch: BM25 search

라벨 JSON ZIP
  |
  +--> oracle_documents.jsonl
  +--> oracle_pages.jsonl
  +--> oracle_elements.jsonl
           |
           +--> chunks_oracle.jsonl
           +--> Golden Set 후보
           +--> 파싱·청킹 품질 평가
```

PDF 파싱 경로와 Oracle 경로는 물리적으로 분리된다. Oracle 데이터가 실제 검색 코퍼스에
섞이는 것을 방지하기 위해 별도 파일과 별도 `ko_unstructured_pdf_oracle` 인덱스를 사용한다.

## 3. 파싱 데이터 구조

### 3.1 PDF Manifest

파일:

```text
C:\vectorsearch-data\ko-unstructured\processed\office_manifest.jsonl
C:\vectorsearch-data\ko-unstructured\processed\pilot_100\office_manifest.jsonl
```

PDF ZIP을 풀지 않고 내부 PDF 목록을 조사한 결과다.

| 필드 | 의미 |
| --- | --- |
| `doc_id` | 전 파이프라인 공통 문서 ID |
| `split` | `training` 또는 `validation` |
| `document_type` | 보고서, 보도자료, 발표자료, 행정문서 등 |
| `source_archive` | 데이터 루트 기준 ZIP 상대경로 |
| `source_member` | ZIP 내부 PDF 경로 |
| `file_size` | PDF 원본 크기 |
| `is_valid`, `error` | inventory 단계 상태 |

`doc_id` 예:

```text
OC2_240927_TY3_0092
```

이 ID는 PDF, Oracle, 청크, Golden Set, 검색 결과를 연결하는 기본 키다.

### 3.2 페이지 파싱 데이터

파일:

```text
processed\pilot_100\pdf_pages_raw.jsonl
```

PDF 한 페이지당 한 행이다.

| 필드 | 의미 |
| --- | --- |
| `doc_id` | 부모 PDF ID |
| `page_num` | 1부터 시작하는 페이지 번호 |
| `width`, `height` | PDF 페이지 좌표계 크기 |
| `raw_text` | 읽기 순서를 적용한 원본 블록 텍스트 |
| `clean_text` | 반복 머리말·꼬리말·페이지 번호 제거 후 텍스트 |

페이지 데이터는 Page 청킹, Fixed 청크의 페이지 범위 계산, Gold page 평가에 사용한다.

### 3.3 정제 블록 데이터

파일:

```text
processed\pilot_100\pdf_blocks_cleaned.jsonl
```

페이지 안의 텍스트 블록당 한 행이다.

| 필드 | 의미 |
| --- | --- |
| `block_id` | `문서ID + 페이지 + 블록번호` |
| `doc_id`, `page_num` | 부모 문서와 페이지 |
| `bbox` | `[x0, y0, x1, y1]` 위치 좌표 |
| `raw_text` | 원래 블록 텍스트 |
| `text` | 공백을 정규화한 검색용 텍스트 |
| `font_size` | 블록 내부 최대 글꼴 크기 |
| `is_heading` | 페이지 중앙 글꼴 대비 제목 후보 여부 |
| `reading_order` | 정렬 후 페이지 내 읽기 순서 |
| `block_type` | 현재 `text` |

현재 읽기 순서 복원 규칙:

1. 페이지 중앙선을 기준으로 왼쪽·오른쪽·전폭 블록을 분리한다.
2. 양쪽 열이 존재하면 상단 전폭 블록을 먼저 배치한다.
3. 왼쪽 열을 위에서 아래로 읽고 오른쪽 열을 위에서 아래로 읽는다.
4. 나머지 전폭 블록을 마지막에 배치한다.

현재 정제 규칙:

- 페이지 높이 상·하단 12% 영역에서 반복되는 텍스트를 머리말·꼬리말 후보로 본다.
- 전체 페이지의 50% 이상에서 반복되고 최소 2회 나타나는 문구를 제거한다.
- 숫자만 있는 페이지 번호 블록을 제거한다.
- 블록 내부 공백을 정규화하되 원본 문자열도 보존한다.

### 3.4 정규화 문서

파일:

```text
processed\pilot_100\office_documents_normalized.jsonl
```

PDF 한 개당 한 행이며 청킹의 공통 입력이다.

```json
{
  "doc_id": "OC2_240927_TY3_0092",
  "source_type": "office_document",
  "title": "담수어의 세계",
  "content": "페이지별 정제 텍스트 전체",
  "embedding_text": "페이지별 정제 텍스트 전체",
  "metadata": {
    "split": "validation",
    "document_type": "발표자료",
    "publisher": "",
    "page_count": 14,
    "text_layer_pages": 14,
    "source_archive": "...zip",
    "source_member": "/OC2_240927_TY3_0092.pdf",
    "parse_error": ""
  }
}
```

필드 역할:

- `content`: BM25 검색과 RAG context에 사용한다.
- `embedding_text`: 임베딩 모델 입력이다. 일반 청크에서는 `content`와 같고 Contextual
  청크에서는 문서 context가 추가된다.
- `title`: 첫 2페이지에서 글꼴 크기가 가장 큰 200자 이하 블록을 제목 후보로 사용한다.
- `text_layer_pages`: OCR 없이 텍스트가 추출된 페이지 수다.
- `parse_error`: 개별 PDF 오류가 전체 배치를 중단하지 않도록 기록한다.

## 4. 파싱 과정에서 보존되는 정보와 손실 가능성

### 보존 정보

- PDF 문서 ID와 원본 ZIP 위치
- 페이지 번호와 페이지 크기
- 텍스트 블록 좌표
- 원본 블록 문자열과 정제 문자열
- 블록 글꼴 크기
- 추정 읽기 순서와 제목 여부
- 문서 유형, split, 페이지 수

### 현재 손실 또는 불확실 정보

- PDF-only 경로에서는 라벨의 발행처와 기관 유형을 사용하지 않으므로 `publisher`가 비어 있다.
- 제목과 heading은 정답이 아니라 글꼴 크기 휴리스틱이다.
- 복잡한 표의 행·열 구조는 평문으로 완전히 복원되지 않는다.
- 슬라이드처럼 짧은 라벨이 많이 배치된 페이지는 heading 후보가 과다 생성될 수 있다.
- 다단 문서가 3단 이상이거나 비정형 배치인 경우 현재 2단 읽기 순서가 틀릴 수 있다.
- 이미지에 포함된 글자와 텍스트 레이어가 없는 페이지는 1차 범위에서 OCR하지 않는다.
- 줄 단위 추출 때문에 원문 단어가 중간에서 분리될 수 있다.

Pilot 100의 Oracle 비교 결과:

| 지표 | 결과 |
| --- | ---: |
| 페이지 추출 성공률 | 1.0000 |
| 문자 precision | 0.6696 |
| 문자 recall | 0.7421 |
| normalized edit similarity | 0.6933 |

문자 품질은 PDF 텍스트와 직접 비교할 수 있는 Oracle 265페이지만 대상으로 한다. 이미지
설명 또는 다른 annotation JSON 참조만 있는 379페이지는 검색·Golden Set용 의미 정보에는
포함하지만 문자 단위 파싱 정확도 계산에서는 제외한다.

따라서 현재 파서는 모든 페이지에서 텍스트를 얻지만, 읽기 순서·중복·줄 연결·표 구조에는
개선 여지가 있다.

## 5. 청킹 공통 스키마

모든 검색 청크는 동일한 `RagDocument` 형태를 사용한다.

```json
{
  "doc_id": "OC2_...__structure_0000",
  "source_type": "office_document",
  "title": "문서 제목",
  "content": "검색 및 RAG에 사용할 청크 내용",
  "embedding_text": "임베딩 모델에 입력할 내용",
  "metadata": {
    "parent_doc_id": "OC2_...",
    "page_start": 1,
    "page_end": 3,
    "section_path": "상위 제목 > 하위 제목",
    "chunk_index": 0,
    "chunking_strategy": "structure",
    "split": "validation",
    "document_type": "보고서(설명형)",
    "publisher": "",
    "page_count": 7,
    "source_archive": "...",
    "source_member": "...",
    "parse_error": ""
  }
}
```

### 식별자 전략

```text
{parent_doc_id}__{chunking_strategy}_{chunk_index:04d}
```

예:

```text
OC2_240927_TY3_0092__page_0000
OC2_240927_TY3_0092__structure_0001
```

검색 평가는 청크 ID와 부모 문서 ID를 모두 사용한다.

- Chunk 평가: 실제 반환된 `doc_id`
- Document 평가: `metadata.parent_doc_id`
- 근거 페이지 평가: `page_start`부터 `page_end`

## 6. 청킹 전략

### 6.1 Fixed

설정:

- 512 pseudo tokens
- 64 tokens overlap
- 현재 tokenizer는 `\w+` 또는 문장부호 단위 정규식이다.

목적:

- 구조를 사용하지 않는 기준선
- 구현과 인덱싱 비용이 낮다.
- 문서 유형에 독립적이다.

페이지 텍스트의 문자 범위와 청크 범위를 비교하여 `page_start`, `page_end`를 계산한다.

한계:

- 제목과 본문이 분리될 수 있다.
- 표나 문단 경계를 무시한다.
- 임베딩 모델의 실제 subword token 수와 정확히 일치하지 않는다.

### 6.2 Page

설정:

- PDF 한 페이지를 청크 하나로 사용한다.
- `page_start == page_end`

목적:

- PDF citation과 Gold page 연결이 가장 단순하다.
- 오피스 문서는 페이지 단위 의미 구성이 비교적 강하다는 가설을 검증한다.
- 발표자료와 짧은 보도자료에 적합하다.

한계:

- 표지처럼 너무 짧은 페이지가 별도 청크가 된다.
- 보고서의 긴 페이지는 하나의 청크가 지나치게 길 수 있다.
- 문단이 다음 페이지로 이어지면 의미가 끊어진다.

Pilot에서는 Page Vector가 가장 높은 실용 코퍼스 성능을 기록했다.

### 6.3 Structure

설정:

- 정제 블록을 `page_num`, `reading_order`로 정렬한다.
- `is_heading` 블록에서 section 후보를 나눈다.
- 짧은 section은 다음 section과 병합한다.
- 목표 범위는 350~700 pseudo tokens다.
- 연결된 heading은 `section_path`에 `>` 구분자로 저장한다.

목적:

- 제목과 관련 본문을 함께 보존한다.
- 지나치게 짧은 페이지나 문단을 의미 단위로 병합한다.
- 페이지를 넘는 하나의 section을 표현할 수 있다.

한계:

- heading 휴리스틱이 틀리면 section 경계도 틀린다.
- 발표자료에서는 여러 짧은 라벨이 하나의 긴 `section_path`가 될 수 있다.
- 현재 구조 병합은 의미 유사도보다 글꼴과 길이를 우선한다.

### 6.4 Contextual

Structure 청크 앞에 다음 정보를 추가한다.

```text
문서명: ...
문서유형: ...
발행처: ...
섹션: ...
```

목적:

- 청크 본문만으로 부족한 상위 문맥을 임베딩에 공급한다.
- 같은 표현이 여러 문서에 존재할 때 문서·section 맥락으로 구분한다.

`content`와 `embedding_text` 모두 context가 포함된 문자열을 사용한다.

Pilot에서는 Structure보다 성능이 낮았다. 원인 후보:

- 빈 `publisher` 필드
- 과도하게 긴 `section_path`
- 본문보다 context가 임베딩 방향을 불필요하게 바꾸는 현상

따라서 전체 확장 전에 context 필드 선택과 길이 제한을 재조정해야 한다.

### 6.5 Oracle

라벨의 `document_description` 또는 `plain_text`를 페이지 단위로 재조립한다.

목적:

- 실제 운영용 코퍼스가 아니라 파싱·청킹 성능 상한선 측정
- PDF-only 검색 결과가 Oracle 성능과 얼마나 차이나는지 계산
- 검색 실패 원인이 파싱인지 retriever인지 구분

Oracle은 반드시 별도 인덱스에 저장하고 최종 운영 후보로 선택하지 않는다.

## 7. Vector DB 적재 스키마

### 7.1 Qdrant collection 분리

| 전략 | Collection |
| --- | --- |
| Fixed | `ko_unstructured_pdf_fixed` |
| Page | `ko_unstructured_pdf_page` |
| Structure | `ko_unstructured_pdf_structure` |
| Contextual | `ko_unstructured_pdf_contextual` |
| Oracle | `ko_unstructured_pdf_oracle` |

각 collection은 하나의 청킹 전략과 하나의 임베딩 모델 조합만 가진다. 전략이나 모델이
바뀌면 같은 collection을 혼합 사용하지 않고 별도 namespace를 만든다.

### 7.2 Qdrant point 구조

```json
{
  "id": 0,
  "vector": [0.012, -0.031, "..."],
  "payload": {
    "doc_id": "OC2_...__page_0000",
    "source_type": "office_document",
    "title": "문서 제목",
    "content": "청크 원문",
    "embedding_text": "임베딩 입력",
    "metadata": {
      "parent_doc_id": "OC2_...",
      "page_start": 1,
      "page_end": 1,
      "section_path": "",
      "chunk_index": 0,
      "chunking_strategy": "page",
      "split": "validation",
      "document_type": "발표자료"
    }
  }
}
```

현재 구성:

- 모델: `intfloat/multilingual-e5-small`
- device: CPU
- batch size: 64
- 거리 함수: Cosine
- 벡터 입력: `embedding_text`, 없으면 `content`
- payload: 전체 청크 JSON

현재 내부 Qdrant point ID는 순차 정수다. 사용자와 평가 코드에서는 point ID가 아니라
payload의 문자열 `doc_id`를 식별자로 사용한다.

### 7.3 Qdrant metadata 전략

필터와 분석에 필요한 항목은 payload의 `metadata`에 둔다.

필수:

- `parent_doc_id`
- `page_start`, `page_end`
- `chunk_index`
- `chunking_strategy`
- `split`
- `document_type`

선택:

- `section_path`
- `publisher`
- `source_archive`, `source_member`
- `page_count`

검색 결과를 PDF 화면이나 원본 파일로 연결하려면 다음 연결을 사용한다.

```text
검색 청크
 -> metadata.parent_doc_id
 -> manifest.doc_id
 -> source_archive + source_member
 -> metadata.page_start/page_end
```

## 8. OpenSearch 적재 스키마

Qdrant와 동일한 JSON 문서를 OpenSearch에도 저장한다.

현재 mapping:

```json
{
  "doc_id": {"type": "keyword"},
  "source_type": {"type": "keyword"},
  "title": {"type": "text"},
  "content": {"type": "text"},
  "metadata": {"type": "object", "enabled": true}
}
```

OpenSearch document `_id`는 청크의 문자열 `doc_id`다.

BM25는 현재 `content` 필드만 검색한다. 향후 개선 후보:

- `title^2~4` 필드 boost
- `section_path` 전용 text field
- `document_type`, `split`, `publisher`를 keyword로 명시
- 한국어 형태소 분석기 또는 nori analyzer 비교
- `content.raw` 또는 exact keyword 보조 필드

현재 `metadata`가 동적 object이므로 실험 규모에서는 동작하지만, 전체 9,491문서 확장 전에는
필터 대상 필드를 명시적 mapping으로 고정하는 편이 안전하다.

## 9. 인덱스 설계 원칙

### 전략별 분리

청킹 전략이 달라지면 문서 수, 텍스트 길이, 검색 후보 수가 달라진다. 하나의 collection에
여러 전략을 섞으면 전략별 latency와 품질을 공정하게 비교할 수 없으므로 별도 인덱스를 쓴다.

### 부모 문서 추적

하나의 PDF가 여러 청크로 분리되므로 검색 결과를 부모 기준으로 중복 제거할 수 있어야 한다.
`parent_doc_id`가 이 역할을 담당한다.

### 페이지 근거 보존

RAG 답변에서 PDF 페이지를 인용하고 Golden Set의 `gold_pages`와 비교하기 위해
`page_start`, `page_end`를 필수로 저장한다.

### 검색 텍스트와 표시 텍스트 분리 가능성

현재는 `content`와 `embedding_text`가 대부분 동일하다. 이 구조를 분리해 둔 이유는 다음
실험을 가능하게 하기 위해서다.

- 사용자 표시용 원문은 `content`에 유지
- 제목·section·query instruction이 추가된 임베딩 입력은 `embedding_text`에 저장
- OpenSearch BM25에는 원문을 사용하고 Qdrant에는 임베딩 최적화 텍스트를 사용

### Oracle 격리

Oracle collection은 성능 상한선 측정 전용이다. 실제 PDF-only corpus와 동일한 결과표에
표시하되 운영 후보에서는 제외한다.

## 10. Pilot 100 적재 현황

| 전략 | JSONL 청크 | Qdrant | OpenSearch |
| --- | ---: | ---: | ---: |
| Fixed | 184 | 184 | 184 |
| Page | 644 | 644 | 644 |
| Structure | 168 | 168 | 168 |
| Contextual | 168 | 168 | 168 |
| Oracle | 644 | 644 | 644 |

기존 v1 collection/index count는 변경되지 않았다.

## 11. 현재 전략 평가

30개 review-pending 질문 기준 잠정 결과:

| 전략 | Vector Recall@10 | MRR | nDCG@10 |
| --- | ---: | ---: | ---: |
| Fixed | 0.900 | 0.850 | 0.863 |
| Page | 0.933 | 0.856 | 0.875 |
| Structure | 0.933 | 0.848 | 0.868 |
| Contextual | 0.900 | 0.828 | 0.846 |
| Oracle | 0.967 | 0.825 | 0.861 |

1차 판단:

- Page는 단순하지만 현재 가장 높은 실용 성능을 보였다.
- Structure는 Page와 Recall이 같고 의미 단위 청크라는 운영상 장점이 있다.
- Contextual은 현재 context 품질 문제로 개선 효과가 없다.
- Fixed도 강한 기준선이지만 페이지와 section 근거 추적이 상대적으로 약하다.
- Oracle과 Page/Structure의 차이가 작아 보이지만 질문 수가 적어 확정할 수 없다.

## 12. 다음 보강 항목

1. Golden Set 30개를 수동 검수해 잘못된 질문·근거를 제거한다.
2. `evidence_text`가 시각 요소 파일 참조만 포함하는 질문을 제외하거나 텍스트 근거로 교체한다.
3. 1,000문서 층화 pilot에서 Page와 Structure를 우선 비교한다.
4. heading 판정에 글꼴 크기뿐 아니라 길이·문장 종결·좌표·번호 패턴을 추가한다.
5. Contextual `section_path` 길이를 제한하고 빈 metadata는 context에서 제외한다.
6. OpenSearch에 제목 boost와 한국어 analyzer 실험을 추가한다.
7. Qdrant payload index를 `parent_doc_id`, `document_type`, `split`에 생성한다.
8. 임베딩 모델의 실제 tokenizer로 청크 길이를 계산하는 실험을 추가한다.
9. PDF text layer가 없는 문서를 위한 OCR fallback은 별도 단계로 분리한다.
10. 최종 선택은 Recall@10, nDCG@10, MRR, latency, 근거 페이지 정확도를 함께 비교한다.

## 13. 결론

현재 구조는 PDF에서 추출한 원문을 페이지·블록·문서 단계로 보존한 뒤, 동일한 공통 청크
스키마로 여러 전략을 생성하고 Qdrant와 OpenSearch에 병렬 적재하는 방식이다.

가장 중요한 설계 선택은 다음 세 가지다.

- 라벨을 검색 코퍼스가 아닌 평가용 Oracle로 격리한다.
- 모든 청크에 부모 문서와 페이지 위치를 저장한다.
- 청킹 전략별 인덱스를 분리하여 품질과 비용을 독립적으로 측정한다.

현재 Pilot 결과에서는 Page와 Structure가 주 후보이며, 다음 단계에서는 Golden Set 검수와
1,000문서 실험을 통해 두 전략의 차이를 확정한다.
