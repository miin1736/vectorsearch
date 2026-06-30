# Ko Dense Technical V3 QASET Generation Strategy

## Purpose

이 문서는 V3 학술논문 PDF 전체 데이터 평가에서 사용할 QASET, 즉 Golden QA Set 생성 방식을
정의한다.

Smoke 100문서 평가에서는 BM25가 너무 쉽게 정답 문서를 찾았다. 원인은 크게 두 가지였다.

1. 질문이 정답 근거 문단의 표면 키워드를 많이 포함했다.
2. 같은 키워드와 유사 주제를 공유하는 hard negative 문서가 검색 공간에 충분히 들어있지 않았다.

따라서 FULL 데이터 평가는 단순히 질문 수를 늘리는 방식이 아니라, 검색 난이도를 설계하고
측정하는 방식으로 진행해야 한다.

## Core Principle

FULL QASET의 목적은 다음 질문에 답하는 것이다.

> 전체 문서 검색 공간에서 gold 문서와 헷갈릴 만한 유사 문서가 충분히 있을 때,
> BM25, Vector, Hybrid, Reranker 중 어떤 방식이 어떤 조건에서 가장 안정적으로 근거를 찾는가?

이를 위해 QASET은 다음 조건을 만족해야 한다.

- Gold 문서와 evidence가 명확해야 한다.
- 같은 연구분야, 유사 제목, 유사 키워드, 유사 초록을 가진 hard negative가 있어야 한다.
- 질문의 lexical overlap 난이도를 측정하고 분리해야 한다.
- document-level 정답과 chunk-level 근거를 모두 평가할 수 있어야 한다.
- 자동 생성 질문과 수동 검수 질문을 구분해야 한다.

## QASET Schema

QASET은 JSONL로 저장한다. 기본 경로는 다음을 사용한다.

- Smoke: `C:\vectorsearch-data\ko-dense-technical\eval\smoke_100\golden_questions_auto.jsonl`
- Pilot: `C:\vectorsearch-data\ko-dense-technical\eval\pilot_1000\golden_questions_candidates.jsonl`
- Full reviewed: `C:\vectorsearch-data\ko-dense-technical\eval\full\golden_questions_reviewed.jsonl`

필수 필드는 다음과 같다.

| Field | Meaning |
|---|---|
| `question_id` | 질문 고유 ID |
| `question` | 검색 평가에 사용할 질문 |
| `reference_answer` | 근거 기반 기준 답변 |
| `gold_doc_ids` | 정답 논문 문서 ID |
| `gold_pages` | 정답 근거 페이지 |
| `gold_section` | 정답 근거 섹션 |
| `evidence_text` | 정답 근거 원문 |
| `evidence_position` | section/page/chunk 연결 정보 |
| `question_type` | 질문 유형 |
| `lexical_overlap` | 질문과 evidence의 표면 어휘 겹침 정도 |
| `difficulty` | `easy`, `medium`, `hard`, `adversarial` |
| `hard_negative_doc_ids` | gold와 헷갈릴 수 있는 문서 ID 목록 |
| `negative_reason` | hard negative 선정 이유 |
| `review_status` | `candidate`, `approved_auto`, `approved_manual`, `rejected`, `revised` |
| `review_flags` | 검수 경고 목록 |

## Generation Pipeline

### 1. Full Corpus Preparation

먼저 전체 PDF를 파싱하고, 문서별 메타데이터를 구축한다.

필요한 입력:

- `documents_normalized.jsonl`
- `pages.jsonl`
- `sections.jsonl`
- 각 청킹 전략별 chunks JSONL
- 전체 OpenSearch index
- 전체 Qdrant collection

문서별로 다음 정보를 계산한다.

- `doc_id`
- 제목 후보
- 연구분야 또는 AIHub 하위 폴더
- 초록/서론/방법/결과/결론 섹션
- 페이지 수
- 섹션별 token length
- 문서 전체 embedding
- 제목/초록 BM25 후보
- 유사 문서 후보

### 2. Gold Document Stratified Sampling

Gold 문서는 무작위로만 뽑지 않는다. 다음 기준으로 층화 추출한다.

| Dimension | Reason |
|---|---|
| 연구분야 | 특정 분야에 치우친 평가 방지 |
| 문서 길이 | 짧은 논문과 긴 논문 난이도 분리 |
| 섹션 유형 | 초록 중심 평가로 쏠림 방지 |
| 페이지 위치 | 문서 후반 근거 검색 능력 측정 |
| OCR/텍스트 품질 | 파싱 품질이 검색 성능에 미치는 영향 확인 |

권장 수량:

- Smoke: 50 questions
- Pilot: 100~150 questions
- Full: 300 reviewed questions

Full 300개는 다음처럼 배분한다.

| Group | Count |
|---|---:|
| 쉬운 사실/요약 질문 | 60 |
| 방법론/절차 질문 | 60 |
| 실험/결과/수치 질문 | 60 |
| 비교/차이점 질문 | 50 |
| low lexical overlap paraphrase 질문 | 50 |
| multi-section evidence 질문 | 20 |

### 3. Evidence Selection

질문은 문서 전체가 아니라 명확한 evidence span에서 만든다.

우선순위:

1. 초록: baseline smoke용으로만 제한 사용
2. 서론: 연구 목적, 문제 정의
3. 방법론: 모델, 절차, 실험 설계
4. 실험/결과: 수치, 비교, 성능, 관찰
5. 결론: 기여, 한계, 향후 연구

FULL 평가에서는 초록 질문 비중을 낮춘다. 초록은 BM25가 쉽게 맞히는 경우가 많기 때문이다.

Evidence 선택 기준:

- 너무 짧지 않아야 한다.
- 문서 고유 제목만으로 답이 결정되면 안 된다.
- 같은 분야 다른 문서에도 유사 키워드가 등장해야 한다.
- 가능한 경우 문서 중간 또는 후반 근거를 포함한다.
- 표/그림/수식만 봐야 하는 질문은 1차 텍스트 검색 평가에서 제외하거나 별도 그룹으로 둔다.

### 4. Hard Negative Construction

Hard negative는 QASET 난이도의 핵심이다.

각 gold 문서마다 최소 5개, 가능하면 10~20개의 hard negative 후보를 붙인다.

선정 방법:

| Negative Type | Construction |
|---|---|
| Same field | 같은 연구분야 또는 같은 AIHub 하위 폴더 |
| Similar title | 제목 BM25 top-k에서 gold 제외 |
| Similar abstract | 초록 embedding top-k에서 gold 제외 |
| Shared keywords | 주요 키워드/전문용어가 겹치는 문서 |
| Same method | 같은 방법론, 모델명, 실험 용어 포함 |
| Same metric | 같은 평가 지표나 수치 표현 포함 |

Hard negative는 검색 코퍼스에 실제로 존재해야 한다. QASET에 적어두기만 하고 인덱스에 없으면
평가 난이도를 만들 수 없다.

### 5. Question Generation Modes

질문은 난이도별로 다르게 만든다.

#### Easy

Evidence에 있는 핵심 단어를 일부 유지한다.

목적:

- 파이프라인 정상 동작 확인
- BM25 baseline sanity check

주의:

- 최종 성능 결론에는 큰 비중을 두지 않는다.

#### Medium

핵심 의미는 유지하되 표현을 약간 바꾼다.

예:

- evidence: "smart learning acceptance"
- question: "중소기업 교육 혁신에서 모바일 기반 학습 도입 의도는 어떻게 분석되었는가?"

목적:

- BM25와 Vector가 모두 경쟁하는 기본 평가

#### Hard

Gold 문서와 hard negative가 같은 키워드를 많이 공유하도록 만든다.

예:

- gold와 negative 모두 "기술사업화 실패 요인"을 포함
- 질문은 특정 연구의 분석 대상, 조건, 결론을 물음

목적:

- ranking 품질 측정
- MRR/nDCG 차이 확인

#### Adversarial / Low Lexical Overlap

Evidence의 고유 표현을 피하고 의미를 바꿔 묻는다.

목적:

- Dense vector와 reranker의 의미 이해 능력 확인
- BM25에 유리한 평가 편향 완화

주의:

- 너무 추상화하면 정답 근거가 모호해진다.
- 반드시 사람이 검수해야 한다.

### 6. Review Workflow

QASET은 자동 생성 후 바로 최종 benchmark로 쓰지 않는다.

검수 상태:

| Status | Meaning |
|---|---|
| `candidate` | 자동 생성 후보 |
| `approved_auto` | 규칙 기반 자동 통과 |
| `approved_manual` | 사람이 검수해 승인 |
| `revised` | 사람이 질문/답변/근거를 수정 |
| `rejected` | 평가에 부적합 |

자동 검수 flag:

- `empty_question`
- `empty_evidence`
- `too_short_evidence`
- `too_high_lexical_overlap`
- `too_low_lexical_overlap`
- `missing_gold_doc`
- `missing_gold_page`
- `no_hard_negative`
- `ambiguous_answer`
- `title_leakage`
- `encoding_noise`

`too_low_lexical_overlap`는 자동 탈락 사유가 아니다. 의미 기반 질문일 수 있으므로 수동 검수 queue로 보낸다.

### 7. Evaluation Slices

최종 보고서는 전체 평균만 제시하지 않는다.

반드시 다음 단면으로 나눠 평가한다.

| Slice | Why |
|---|---|
| 전체 평균 | 전체 경향 확인 |
| question_type별 | 방법론/결과/비교 질문 차이 확인 |
| difficulty별 | 쉬운 문제와 어려운 문제 분리 |
| lexical_overlap별 | BM25 편향 확인 |
| hard_negative_count별 | 경쟁 문서 밀도 영향 확인 |
| 문서 길이별 | 긴 문서에서 청킹 효과 확인 |
| evidence 위치별 | 문서 후반 근거 검색 성능 확인 |
| 청킹 전략별 | Fixed/Page/Section/Tokenizer-aware 비교 |
| retriever별 | BM25/Vector/Hybrid/Reranker 비교 |

## Metrics

Document-level:

- Document Recall@5
- Document Recall@10
- MRR
- nDCG@10

Chunk-level:

- Chunk Recall@5
- Chunk Recall@10
- Evidence containment ratio
- Gold evidence split count
- Context precision@10

Operational:

- P50 latency
- P95 latency
- index size
- indexing time

RAG 단계:

- Faithfulness
- Answer relevancy
- Citation correctness
- Unsupported answer rate
- Abstain correctness

## Anti-Patterns

피해야 할 QASET 생성 방식:

- Gold 문서 제목을 질문에 그대로 넣는다.
- Evidence 문장을 거의 복사해 질문을 만든다.
- Smoke subset에 gold 문서만 있고 유사 negative가 없다.
- 초록 질문만으로 전체 retrieval 성능을 판단한다.
- 전체 평균만 보고 청킹 전략을 선택한다.
- 자동 생성 QASET을 수동 검수 없이 최종 benchmark로 사용한다.

## Recommended FULL Evaluation Flow

```text
FULL PDF parsing
→ document/section metadata build
→ full corpus indexing by chunking strategy
→ gold document stratified sampling
→ hard negative mining
→ difficulty-controlled QASET generation
→ auto review and flags
→ manual review for 300 questions
→ BM25 / Vector / Hybrid / Reranker evaluation
→ document-level + chunk-level metrics
→ difficulty/slice analysis
→ final strategy selection
```

## Current Decision

V3 smoke 결과는 다음 결론을 남긴다.

> QASET 난이도 설계 없이 retrieval 성능을 비교하면 BM25가 과도하게 좋아 보일 수 있다.

따라서 FULL 데이터 평가는 다음 원칙으로 진행한다.

1. 전체 corpus를 검색 공간으로 사용한다.
2. QASET은 hard negative 중심으로 만든다.
3. 질문은 lexical overlap 난이도별로 분리한다.
4. 자동 생성 결과는 smoke/pilot 기준선으로만 사용한다.
5. 최종 결론은 수동 검수된 300개 QASET에서만 낸다.
