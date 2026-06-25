# OpenSearch Index 및 Qdrant Collection 현황·운영 문서

작성일: 2026-06-25  
대상 저장소: `vectorsearch`  
기준: 실행 중인 OpenSearch/Qdrant API 실시간 조회

## 1. 문서 목적

현재 프로젝트에는 과거 KoreanOps v1 실험과 새로운 한국어 오피스 PDF v2 실험의
인덱스가 함께 존재한다. 이 문서는 각 OpenSearch index와 Qdrant collection의 목적,
데이터 규모, 설정, 연관 config, 보존·삭제 기준을 정리한다.

핵심 원칙:

- `koreanops_*`는 기존 티켓·로그 v1 실험 자산이다.
- `ko_unstructured_pdf_*`는 현재 오피스 PDF v2 실험 자산이다.
- v1과 v2 이름을 교차 사용하거나 같은 인덱스에 데이터를 혼합하지 않는다.
- `oracle`은 성능 상한선 평가용이며 실제 서비스 코퍼스로 사용하지 않는다.
- 청킹 전략 또는 임베딩 모델이 바뀌면 별도 namespace를 사용한다.

## 2. 서비스 구성

| 서비스 | 버전 | 주소 | 저장 경로 |
| --- | --- | --- | --- |
| Qdrant | `v1.18.0` | `http://localhost:6333` | `C:\vectorsearch-data\index\qdrant` |
| OpenSearch | `2.17.1` | `http://localhost:9200` | `C:\vectorsearch-data\index\opensearch` |
| OpenSearch Dashboards | `2.17.1` | `http://localhost:5601` | 선택 실행 |

현재 디스크 사용량:

| 저장소 | 사용량 |
| --- | ---: |
| Qdrant 전체 저장소 | 약 6.886 GiB |
| OpenSearch 전체 저장소 | 약 0.105 GiB |

OpenSearch는 단일 노드이며 heap은 `2GB`로 제한되어 있다. 보안 플러그인은 로컬 실험을
위해 비활성화되어 있다.

## 3. 현재 오피스 PDF v2 자산

### 3.1 먼저 이해할 개념

하나의 PDF 문서는 그대로 Vector DB에 저장하지 않는다. PDF 전체가 너무 길면 질문과 관련
없는 내용까지 하나의 벡터에 섞이고, 검색 결과로 전달하기에도 너무 크기 때문이다.

따라서 다음 순서로 처리한다.

```text
PDF 파일
  -> 페이지별 텍스트 추출
  -> 텍스트 블록의 읽기 순서 복원
  -> 반복 머리말·꼬리말·페이지 번호 제거
  -> 문서 전체 정규화 텍스트 생성
  -> 전략별로 여러 개의 작은 청크 생성
  -> 청크마다 임베딩 벡터 생성
  -> Qdrant와 OpenSearch에 같은 청크 저장
```

여기서 Fixed, Page, Structure, Contextual은 **동일한 PDF를 어떤 기준으로 나눌 것인가**에
대한 서로 다른 답이다. Oracle은 PDF 파싱 결과가 아니라 사람이 만든 라벨 정답을 이용한
비교 기준이다.

예를 들어 14페이지짜리 발표자료 한 개가 있을 때 다음처럼 달라질 수 있다.

| 전략 | 생성 방식 | 예상 결과 |
| --- | --- | --- |
| Fixed | 512 token마다 자름 | 약 4~8개 청크 |
| Page | 페이지마다 자름 | 14개 청크 |
| Structure | 제목과 관련 본문을 묶음 | 약 3~7개 청크 |
| Contextual | Structure 청크에 문서 정보를 붙임 | Structure와 같은 개수 |
| Oracle | 라벨이 제공한 페이지 정답 텍스트 사용 | 14개 평가용 청크 |

각 전략은 별도 OpenSearch index와 Qdrant collection에 저장한다. 그래야 같은 질문을
각 전략에 독립적으로 검색하여 어떤 청킹 방식이 좋은지 비교할 수 있다.

### 3.2 전략별 대응 관계

| 전략 | OpenSearch index | Qdrant collection | 현재 행/point |
| --- | --- | --- | ---: |
| Fixed | `ko_unstructured_pdf_fixed` | `ko_unstructured_pdf_fixed` | 184 |
| Page | `ko_unstructured_pdf_page` | `ko_unstructured_pdf_page` | 644 |
| Structure | `ko_unstructured_pdf_structure` | `ko_unstructured_pdf_structure` | 168 |
| Contextual | `ko_unstructured_pdf_contextual` | `ko_unstructured_pdf_contextual` | 168 |
| Oracle | `ko_unstructured_pdf_oracle` | `ko_unstructured_pdf_oracle` | 644 |

모든 count는 Pilot 100 문서에서 생성된 JSONL 청크 수와 일치한다.

### 3.3 Fixed: 일정한 길이로 자르는 기준선

#### 무엇인가

문서 구조나 페이지를 고려하지 않고 텍스트를 일정한 길이로 자르는 가장 단순한 방식이다.

현재 설정:

- 청크 크기: 512 pseudo tokens
- 중복 구간: 64 pseudo tokens
- token 계산: 한글·영문 단어와 문장부호를 정규식으로 세는 방식

예:

```text
문서 전체:
[토큰 1 ................................................ 토큰 900]

청크 1: 토큰   1 ~ 512
청크 2: 토큰 449 ~ 900
             ^ 64 token 중복
```

#### 왜 구성했는가

Fixed는 다른 복잡한 전략이 정말 효과가 있는지 판단하기 위한 기준선이다.

- 구현이 단순하다.
- 모든 문서 유형에 같은 규칙을 적용할 수 있다.
- 제목이나 레이아웃 분석이 틀려도 청크를 생성할 수 있다.
- Structure가 Fixed보다 좋아야 구조 분석의 가치가 있다고 설명할 수 있다.

64 token overlap은 청크 경계에서 문장이 잘렸을 때 다음 청크에도 일부 문맥이 남도록 하기
위한 것이다.

#### 어떻게 구성했는가

1. 페이지별 `clean_text`를 페이지 순서대로 연결한다.
2. 전체 연결 텍스트를 정규식 token으로 나눈다.
3. 512 token을 하나의 청크로 만든다.
4. 다음 청크는 이전 청크 마지막 64 token부터 다시 시작한다.
5. 청크의 문자 범위와 원래 페이지 문자 범위를 비교한다.
6. 청크가 걸쳐 있는 첫 페이지와 마지막 페이지를 `page_start`, `page_end`로 저장한다.

생성 ID:

```text
OC2_240927_TY3_0092__fixed_0000
```

#### 저장 목적

- OpenSearch: 구조를 사용하지 않은 BM25 기준 성능
- Qdrant: 구조를 사용하지 않은 Vector 기준 성능

#### 장단점

장점:

- 빠르고 재현하기 쉽다.
- 문서 구조 분석에 실패해도 동작한다.
- 청크 길이가 비교적 일정하다.

단점:

- 제목과 설명이 서로 다른 청크로 분리될 수 있다.
- 표, 문단, 목록, 페이지 경계를 무시한다.
- 실제 임베딩 모델 tokenizer와 pseudo token 계산이 완전히 같지는 않다.

- 입력: `chunks_fixed.jsonl`
- 기준: 512 pseudo tokens, overlap 64
- 목적: 문서 구조를 사용하지 않는 baseline
- 장점: 단순하고 문서 유형에 독립적
- 단점: 제목·문단·페이지 경계를 자를 수 있음
- config: `experiments/ko_unstructured_v2/configs/pdf_fixed.yaml`

### 3.4 Page: PDF 페이지를 그대로 검색 단위로 사용

#### 무엇인가

PDF 한 페이지를 하나의 청크로 만드는 방식이다.

```text
PDF 14페이지
  -> page 청크 14개
```

각 청크는 하나의 페이지에만 대응하므로 다음 값이 같다.

```json
{
  "page_start": 3,
  "page_end": 3
}
```

#### 왜 구성했는가

오피스 문서는 페이지가 자연스러운 정보 단위인 경우가 많다.

- 발표자료는 슬라이드 한 장에 하나의 주제가 담긴다.
- 보도자료는 페이지별 본문 흐름이 비교적 명확하다.
- 계약서와 보고서는 답변 근거 페이지를 바로 표시할 수 있다.
- Golden Set의 `gold_pages`와 가장 직접적으로 비교할 수 있다.

또한 Page는 Fixed보다 구조를 보존하면서도 별도의 복잡한 heading 판정이 필요하지 않은
중간 수준의 전략이다.

#### 어떻게 구성했는가

1. PyMuPDF로 페이지 안의 텍스트 블록을 추출한다.
2. 좌표를 이용해 블록 읽기 순서를 정한다.
3. 반복 머리말·꼬리말과 페이지 번호를 제거한다.
4. 남은 블록을 빈 줄로 연결해 해당 페이지의 `clean_text`를 만든다.
5. `clean_text`가 비어 있지 않은 페이지마다 청크 하나를 생성한다.

생성 ID:

```text
OC2_240927_TY3_0092__page_0000
```

#### 저장 목적

- 검색 결과를 원본 PDF 페이지로 정확하게 연결
- Page 단위 Vector와 BM25 품질 측정
- RAG 답변에 `PDF ID + 페이지 번호`를 근거로 제공

#### 장단점

장점:

- 구현과 해석이 쉽다.
- 근거 페이지가 명확하다.
- 현재 Pilot에서 가장 높은 실용 Vector 성능을 기록했다.

단점:

- 표지처럼 글자가 거의 없는 페이지도 짧은 청크가 된다.
- 한 페이지가 매우 길면 임베딩 입력이 지나치게 길어질 수 있다.
- 문장이 다음 페이지로 이어질 경우 의미가 분리된다.

- 입력: `chunks_page.jsonl`
- 기준: PDF 한 페이지당 한 청크
- 목적: 페이지 citation과 Golden page 평가를 단순화
- 현재 Pilot에서 가장 높은 실용 Vector 성능
- config: `experiments/ko_unstructured_v2/configs/pdf_page.yaml`

### 3.5 Structure: 제목과 본문 관계를 보존하는 구조 기반 방식

#### 무엇인가

PDF에서 추출한 글꼴 크기, 블록 위치, 읽기 순서를 이용해 제목 후보와 본문을 구분하고,
관련된 블록을 하나의 의미 단위로 묶는 방식이다.

목표 청크 길이:

- 최소 목표: 350 pseudo tokens
- 최대 목표: 700 pseudo tokens

예:

```text
2. 정부 정책 현황        <- heading
정책의 주요 내용은 ...   <- body
지원 대상은 ...          <- body

3. 향후 과제             <- 다음 heading
향후 개선할 사항은 ...   <- body
```

위 문서는 제목 `2. 정부 정책 현황`과 그 아래 본문을 하나의 section으로 만들고,
`3. 향후 과제`부터 다음 section을 시작한다.

#### 왜 구성했는가

Fixed는 의미 경계를 무시하고 Page는 페이지 경계에 종속된다. Structure는 실제 독자가
문서를 읽는 방식에 더 가까운 청크를 만들기 위해 구성했다.

- 제목과 설명을 한 청크에 유지한다.
- 하나의 section이 여러 페이지에 걸쳐 있어도 함께 묶을 수 있다.
- 짧은 section은 인접 section과 합쳐 지나치게 작은 청크를 줄인다.
- 검색 결과가 어떤 section에 해당하는지 설명할 수 있다.

#### 어떻게 구성했는가

1. 페이지별 텍스트 블록을 `page_num`, `reading_order` 순서로 정렬한다.
2. 각 페이지 블록의 글꼴 크기 중앙값을 구한다.
3. 중앙값보다 1.25배 이상 큰 글꼴 블록을 `is_heading=true` 후보로 정한다.
4. heading 후보가 나타나면 이전 section을 마감한다.
5. heading과 뒤따르는 본문 블록을 하나의 raw section으로 만든다.
6. 350 token보다 짧은 section은 다음 section과 합친다.
7. 합쳤을 때 700 token을 넘으면 별도 청크로 유지한다.
8. 포함된 페이지들의 최솟값과 최댓값을 페이지 범위로 저장한다.
9. 병합된 heading을 `section_path`에 `>`로 연결한다.

예:

```json
{
  "section_path": "경제 현황 > 물가 전망",
  "page_start": 2,
  "page_end": 4
}
```

#### 저장 목적

- 의미 단위 청크의 Vector/BM25 품질 평가
- 검색된 근거의 section 제목 제공
- 페이지보다 유연하고 Fixed보다 설명 가능한 RAG context 구성

#### 장단점

장점:

- 제목과 본문 관계를 보존한다.
- 짧은 section을 합쳐 임베딩 정보량을 확보한다.
- 페이지를 넘어가는 section을 표현할 수 있다.

단점:

- heading 판정이 틀리면 청크 경계도 틀린다.
- 발표자료에서는 여러 짧은 라벨이 모두 heading으로 인식될 수 있다.
- 현재는 의미 유사도보다 글꼴 크기와 길이를 우선한다.

- 입력: `chunks_structure.jsonl`
- 기준: 제목 후보와 본문 블록을 350~700 pseudo token 범위로 병합
- 목적: section 의미 단위 보존
- Page와 함께 현재 최종 후보
- config: `experiments/ko_unstructured_v2/configs/pdf_structure.yaml`

### 3.6 Contextual: Structure 청크에 상위 문맥을 추가

#### 무엇인가

Structure 청크 앞에 문서 전체를 설명하는 context를 붙인 방식이다. 청크 개수와 본문 경계는
Structure와 같지만 `content`와 `embedding_text`가 달라진다.

현재 prefix:

```text
문서명: 담수어의 세계
문서유형: 발표자료
발행처:
섹션: 담수어의 주요 서식지 > 잉어목 물고기

[실제 section 본문]
```

#### 왜 구성했는가

청크 본문만 보면 어느 문서나 section에서 나온 내용인지 알기 어려울 수 있다.

예를 들어 본문이 `증가율은 5%이다`뿐이라면 무엇의 증가율인지 불명확하다. 여기에
`문서명: 지역경제 보고서`, `섹션: 관광객 현황`을 붙이면 임베딩이 질문 의도를 더 잘
구분할 수 있다는 가설이다.

기존 v1 티켓 데이터에서는 parent context 추가가 Vector 검색을 개선했기 때문에 PDF에서도
같은 효과가 있는지 확인하기 위해 포함했다.

#### 어떻게 구성했는가

1. Structure 전략으로 section 청크를 먼저 만든다.
2. 정규화 문서의 `title`을 문서명으로 가져온다.
3. metadata의 `document_type`, `publisher`를 가져온다.
4. Structure에서 만든 `section_path`를 가져온다.
5. 네 정보를 텍스트 prefix로 직렬화한다.
6. prefix와 원래 section 본문을 연결한다.
7. 연결된 전체 문자열을 `content`와 `embedding_text`에 저장한다.

#### 저장 목적

- 상위 문맥을 포함한 Dense Vector 검색 실험
- 제목·문서유형·section이 검색 품질에 미치는 영향 측정
- 청크 단독으로 RAG context에 전달돼도 출처를 이해할 수 있게 함

#### 현재 결과와 문제점

Pilot에서는 Structure보다 성능이 낮았다.

가능한 원인:

- PDF-only 경로에서 `publisher`가 비어 있다.
- 발표자료의 heading 과다 인식으로 `section_path`가 지나치게 길다.
- 긴 prefix가 실제 본문의 임베딩 신호를 희석할 수 있다.
- 질문에 필요하지 않은 문서유형 정보가 잡음으로 작용할 수 있다.

따라서 Contextual 전략은 폐기 대상이 아니라 prefix 길이와 필드를 조정할 실험 대상이다.

- 입력: `chunks_contextual.jsonl`
- 기준: Structure 청크에 문서명·문서유형·발행처·section context 추가
- 목적: 청크 단독 의미를 강화해 Vector 검색 개선
- 현재 Pilot에서는 Structure보다 낮아 context 구성 조정 필요
- config: `experiments/ko_unstructured_v2/configs/pdf_contextual.yaml`

### 3.7 Oracle: 사람이 만든 라벨을 이용한 평가 상한선

#### 무엇인가

PDF parser가 추출한 텍스트 대신 AI Hub 라벨의 `plain_text`, `document_description`을
재조립해 만든 평가용 청크다.

Oracle은 실제 실무 파이프라인이 아니다. 사람이 검수한 정답 구조가 있을 때 검색 성능이
어디까지 올라갈 수 있는지 측정하는 기준이다.

#### 왜 구성했는가

검색 실패의 원인을 분리하기 위해 필요하다.

```text
Oracle도 검색 실패
  -> retriever, embedding 또는 질문 자체의 문제 가능성

Oracle은 성공하지만 PDF Page/Structure는 실패
  -> PDF 파싱 또는 청킹 과정의 정보 손실 가능성
```

즉 Oracle은 “정답 텍스트를 사용했을 때의 최고 성능”이며 실제 파싱 결과가 이 성능에
얼마나 가까운지를 측정한다.

#### 어떻게 구성했는가

1. 라벨 JSON을 `source_data_name_pdf`의 PDF ID로 그룹화한다.
2. `page_num`으로 페이지를 구분한다.
3. 페이지 내부 요소를 `bounding_box`의 위·왼쪽 좌표 순으로 정렬한다.
4. `D01 document_description`이 있으면 페이지 대표 텍스트로 우선 사용한다.
5. 없으면 시각 요소를 제외한 `plain_text`를 순서대로 연결한다.
6. 한 Oracle 페이지를 청크 하나로 만든다.
7. metadata에 `oracle_only=true`를 저장한다.

#### 저장 목적

- PDF 파싱 품질의 검색 영향 측정
- 실제 청킹 전략의 성능 상한 비교
- Golden Set의 답과 근거 페이지 생성

#### 장단점

장점:

- 텍스트 누락과 읽기 순서 오류가 적은 정답 기준을 제공한다.
- 파싱 문제와 검색 문제를 분리할 수 있다.

단점:

- 일반 실무 문서에는 이런 라벨이 존재하지 않는다.
- 실제 서비스 코퍼스로 사용하면 실무 재현성이 사라진다.
- 일부 `document_description`에는 시각 요소 파일 참조가 포함될 수 있다.

- 입력: `chunks_oracle.jsonl`
- 기준: AI Hub 라벨 텍스트를 페이지 단위로 재구성
- 목적: PDF 파싱 및 청킹 성능의 상한선 측정
- 운영 검색 후보가 아니며 평가 전용
- config: `experiments/ko_unstructured_v2/configs/pdf_oracle.yaml`

## 4. Qdrant 구성

### 4.1 공통 Vector 설정

오피스 PDF collection 5개는 모두 다음 설정을 사용한다.

| 항목 | 값 |
| --- | --- |
| 임베딩 모델 | `intfloat/multilingual-e5-small` |
| Vector dimension | 384 |
| 거리 함수 | Cosine |
| shard | 1 |
| replication factor | 1 |
| write consistency | 1 |
| payload storage | on-disk |
| HNSW `m` | 16 |
| HNSW `ef_construct` | 100 |
| full scan threshold | 10,000 |
| indexing threshold | 10,000 |
| quantization | 사용하지 않음 |

현재 Pilot collection은 모두 10,000 point 미만이므로 `indexed_vectors_count=0`이다. 이는
오류가 아니라 HNSW index를 만들지 않고 exact full scan을 사용하는 현재 설정의 결과다.
전체 데이터 적재 후 point가 임계치를 넘으면 optimizer가 HNSW indexing을 수행한다.

### 4.2 Qdrant Point 구조

```json
{
  "id": 0,
  "vector": [0.01, -0.02, "... 384 dimensions"],
  "payload": {
    "doc_id": "OC2_...__page_0000",
    "source_type": "office_document",
    "title": "문서 제목",
    "content": "검색 결과와 RAG에 사용할 청크 원문",
    "embedding_text": "임베딩 모델 입력",
    "metadata": {
      "parent_doc_id": "OC2_...",
      "page_start": 1,
      "page_end": 1,
      "section_path": "",
      "chunk_index": 0,
      "chunking_strategy": "page",
      "split": "validation",
      "document_type": "발표자료",
      "publisher": ""
    }
  }
}
```

Qdrant 내부 `id`는 현재 순차 정수이며 실제 업무 식별자는 payload의 `doc_id`다.
문서 단위 평가와 중복 제거는 `metadata.parent_doc_id`를 사용한다.

### 4.3 Payload index 현황

현재 오피스 PDF collection의 `payload_schema`는 비어 있다. 즉 다음 metadata filter가
가능하더라도 payload index가 없어 전체 scan 비용이 발생할 수 있다.

전체 9,491문서 확장 전에 다음 payload index 생성을 권장한다.

- `metadata.parent_doc_id`: keyword
- `metadata.document_type`: keyword
- `metadata.split`: keyword
- `metadata.chunking_strategy`: keyword
- `metadata.page_start`, `metadata.page_end`: integer

## 5. OpenSearch 구성

### 5.1 공통 Mapping

코드에서 생성하는 기본 mapping:

```json
{
  "doc_id": {"type": "keyword"},
  "source_type": {"type": "keyword"},
  "title": {"type": "text"},
  "content": {"type": "text"},
  "metadata": {"type": "object", "enabled": true}
}
```

추가 필드인 `embedding_text`와 metadata 하위 필드는 dynamic mapping으로 생성되었다.

현재 실제 metadata mapping 예:

- 숫자: `page_count`, `page_start`, `page_end`, `chunk_index` → `long`
- 문자열: `parent_doc_id`, `document_type`, `split`, `section_path` → `text`와 `.keyword`
- Oracle 전용: `oracle_only` → `boolean`

OpenSearch `_id`는 청크의 문자열 `doc_id`다.

### 5.2 검색 방식

현재 BM25 retriever는 `content` 필드만 검색한다.

```json
{
  "query": {
    "bool": {
      "must": [{"match": {"content": "사용자 질문"}}]
    }
  }
}
```

현재 `title`, `section_path`, `document_type`은 저장되지만 BM25 점수에 직접 boost되지 않는다.
향후 다음 mapping/query 개선을 권장한다.

- `multi_match`: `title^3`, `metadata.section_path^2`, `content`
- 한국어 `nori` analyzer 비교
- filter 대상 metadata를 명시적 `keyword`로 선언
- replica를 `0`으로 설정해 단일 노드 yellow 상태 제거

### 5.3 Yellow 상태 해석

현재 사용자 index의 health는 모두 `yellow`다. 원인은 단일 노드에서 primary shard는
정상 배치됐지만 기본 replica shard를 다른 노드에 배치할 수 없기 때문이다.

- `status=open`
- 문서 검색·적재 정상
- primary 데이터 정상
- replica만 미할당

로컬 단일 노드 실험에서는 장애가 아니다. 상태를 green으로 만들려면 index 설정의
`number_of_replicas`를 `0`으로 명시해야 한다.

## 6. 기존 KoreanOps v1 자산

### 6.1 OpenSearch v1 Index

| Index | 문서 수 | 용도 |
| --- | ---: | --- |
| `koreanops_documents` | 22,000 | 티켓·로그 baseline 및 일부 Vector 변형의 공통 BM25 |
| `koreanops_documents_field_chunks` | 82,019 | field-aware 청킹 BM25 |
| `koreanops_documents_contextual_chunks` | 82,019 | contextual 청킹 BM25 |
| `koreanops_documents_contextual_subset` | 10,000 | E5/BGE-M3 subset 공통 BM25 |

v1 OpenSearch index는 삭제하거나 v2 PDF 데이터를 추가하지 않는다.

### 6.2 Qdrant v1 Collection

| Collection | Point | Dimension | 용도 |
| --- | ---: | ---: | --- |
| `koreanops_documents` | 22,000 | 384 | baseline E5 |
| `koreanops_documents_field_chunks` | 82,019 | 384 | field chunks |
| `koreanops_documents_contextual_chunks` | 82,019 | 384 | contextual chunks |
| `koreanops_documents_e5_prefix` | 22,000 | 384 | E5 prefix 실험 |
| `koreanops_documents_embedding_aware` | 22,000 | 384 | embedding text 실험 |
| `koreanops_documents_contextual_subset_e5` | 10,000 | 384 | E5 subset |
| `koreanops_documents_contextual_subset_bge_m3` | 10,000 | 1,024 | BGE-M3 subset |

`contextual_subset_e5`와 `contextual_subset_bge_m3`는 동일한 10,000개 문서를 다른 임베딩
모델로 비교한다. OpenSearch는 두 실험이 `koreanops_documents_contextual_subset` 하나를
공유한다.

일부 82,019 point collection의 `indexed_vectors_count`가 point count보다 조금 적은 것은
Qdrant optimizer의 segment 상태에 따른 값이다. collection status는 모두 `green`이다.

## 7. 존재하지 않는 Config 예약 이름

다음 이름은 YAML config에는 정의되어 있지만 현재 서버에는 index/collection이 없다.

- `ko_unstructured_raw`
- `ko_unstructured_cleaned`
- `ko_unstructured_normalized`
- `ko_unstructured_contextual_chunks`

이 이름은 이전 콜센터 기반 v2 계획에서 예약했던 namespace다. 현재 오피스 PDF 실험에서는
`pdf_*.yaml`만 사용하므로 새 데이터 적재에 사용하지 않는다.

## 8. 시스템 OpenSearch Index

다음 dot-prefix index는 OpenSearch 내부 시스템 자산이다.

- `.kibana_1`
- `.opensearch-observability`
- `.plugins-ml-config`
- `.ql-datasources`

프로젝트 데이터가 아니며 직접 삭제하거나 재색인하지 않는다.

## 9. 적재 동작과 주의사항

### Qdrant

기본 실행은 target collection을 `recreate_collection`하므로 기존 내용을 삭제하고 새로 만든다.

```powershell
uv run koreanops-index-qdrant <chunks.jsonl> --config-path <pdf_config.yaml>
```

`--resume`은 현재 point count만큼 JSONL 앞부분을 건너뛴다. JSONL 순서와 기존 collection
내용이 완전히 같다는 전제가 필요하다.

### OpenSearch

index가 없으면 생성하고, 있으면 유지한 채 같은 `doc_id`를 overwrite/upsert한다.

```powershell
uv run koreanops-index-opensearch <chunks.jsonl> --config-path <pdf_config.yaml>
```

이전 실행보다 새 JSONL 청크 수가 줄어든 경우 과거의 불필요한 document가 남을 수 있다.
공정한 재실험 전에는 target index를 삭제한 뒤 다시 적재하거나 recreate 옵션을 구현해야 한다.

## 10. 삭제·보존 정책

### 반드시 보존

- 모든 `koreanops_*` v1 baseline
- 현재 `ko_unstructured_pdf_*` Pilot 결과
- `ko_unstructured_pdf_oracle` 평가 상한선

### 재생성 가능

- `ko_unstructured_pdf_fixed`
- `ko_unstructured_pdf_page`
- `ko_unstructured_pdf_structure`
- `ko_unstructured_pdf_contextual`

단, 삭제 전 대응 JSONL과 config가 존재하는지 확인한다.

### 삭제 금지

- 이름만 보고 wildcard로 `koreanops_*` 또는 `ko_unstructured_*` 전체 삭제
- OpenSearch dot-prefix 시스템 index 삭제
- v1 baseline을 v2와 동일 이름으로 recreate

## 11. 운영 확인 명령

OpenSearch index 목록:

```powershell
Invoke-RestMethod "http://localhost:9200/_cat/indices?format=json"
```

OpenSearch 개별 count:

```powershell
Invoke-RestMethod "http://localhost:9200/ko_unstructured_pdf_page/_count"
```

Qdrant collection 목록:

```powershell
(Invoke-RestMethod "http://localhost:6333/collections").result.collections
```

Qdrant 개별 상태:

```powershell
(Invoke-RestMethod `
  "http://localhost:6333/collections/ko_unstructured_pdf_page").result
```

Docker 서비스:

```powershell
docker compose ps
```

## 12. 현재 결론

현재 오피스 PDF v2의 5개 OpenSearch index와 Qdrant collection은 이름, count, 데이터 목적이
완전히 분리되어 정상 동작한다.

- OpenSearch는 BM25와 Hybrid의 lexical 후보를 담당한다.
- Qdrant는 384차원 E5 Vector 검색을 담당한다.
- Page와 Structure가 현재 실용 후보이다.
- Contextual은 context 구성 개선이 필요하다.
- Oracle은 평가 상한선이며 운영 대상이 아니다.
- 전체 확장 전 Qdrant payload index, OpenSearch 명시적 mapping, replica 0, 안전한 index
  recreate 절차를 추가하는 것이 권장된다.
