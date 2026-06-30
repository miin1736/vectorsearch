# 한국어 조밀 기술문서 Hybrid RAG 3차 실험 제안서

작성일: 2026-06-25  
프로젝트명: `ko_dense_technical_v3`  
추천 데이터: AIHub 학술논문 이해 데이터 PDF

## 0. 2026-06-28 데이터 교체 결정

기존 V3 제안서는 한국 특허 명세서를 주 데이터로 가정했으나, 특허 데이터 확보에 비용이
발생하므로 해당 가정은 폐기한다. V3 실험 구조, namespace, case matrix, profile registry,
runner는 유지하고 **주 데이터만 AIHub `학술논문 이해 데이터`의 한국어 학술논문 PDF**로
교체한다.

현재 유효한 데이터 매핑은 다음과 같다.

| 기존 특허 계획 | 변경 후 학술논문 계획 |
| --- | --- |
| 특허 명세서 PDF | AIHub 학술논문 PDF |
| patent section | paper section |
| claim | abstract / introduction / method / result / conclusion / evidence paragraph |
| IPC/CPC | research_field / paper_topic / keyword / publication_year |
| claim support edge | section_transition / citation_or_keyword_related / same_topic_related |
| 같은 IPC/CPC hard negative | 같은 연구분야·유사 키워드 hard negative |

따라서 아래 문서에서 특허, IPC/CPC, claim이라는 표현이 남아 있더라도 구현 기준은 이
교체 결정과 `experiments/ko_dense_technical_v3/TEST_CASE_MANAGEMENT.md`를 우선한다.

## 1. 제안 배경

2차 오피스 PDF 실험에서는 Page Vector가 높은 검색 성능을 기록했다. 그러나 실제 E5
tokenizer로 확인한 결과, 전체 페이지의 상당수가 512 tokens 이하였고 발표자료는 페이지당
텍스트가 특히 짧았다.

이러한 데이터에서는 한 페이지가 이미 적절한 검색 청크에 가까우므로 다음 문제를 충분히
검증하기 어렵다.

- 페이지 안에 여러 의미 단위가 섞여 있는 경우
- 한 section이 여러 페이지에 걸쳐 이어지는 경우
- 임베딩 모델 최대 길이로 인해 문서 후반부가 잘리는 경우
- 유사한 전문용어를 사용하는 문서가 다수 존재하는 경우
- 질문의 근거가 문서 중간이나 후반에 숨어 있는 경우

3차 실험은 이러한 한계를 보완하기 위해 **전체 내용이 여러 페이지에 걸쳐 이어지고,
페이지당 텍스트가 조밀한 한국어 기술문서**를 대상으로 한다.

## 2. 추천 데이터: 한국 특허 명세서

한국 특허·실용신안 명세서 PDF를 3차 실험의 주 데이터로 추천한다.

일반적인 특허 명세서는 다음 구조를 가진다.

- 발명의 명칭
- 기술 분야
- 배경 기술
- 해결하려는 과제
- 과제 해결 수단
- 발명의 효과
- 도면의 간단한 설명
- 발명을 실시하기 위한 구체적인 내용
- 실시예
- 청구범위

이 구조는 기술문서의 section을 명확하게 제공하면서도 각 section 내부가 길고 조밀하여
청킹 전략의 차이를 검증하기에 적합하다.

공식 데이터 후보:

- KIPRISPlus 한국 특허·실용신안 공개·등록공보
- KIPRISPlus REST API의 서지·초록·청구범위·전문 다운로드 정보
- AI Hub 논문자료 요약 데이터의 특허 명세서 부분

## 3. 특허 명세서가 적합한 이유

### 3.1 문서가 길고 페이지가 조밀하다

특허 명세서는 기술 배경, 구성요소, 동작 원리, 실시예와 청구항을 상세하게 설명한다.
한 페이지 안에 다수의 문단과 전문용어가 들어가므로 단순 Page 청킹의 한계를 확인할 수 있다.

검증할 수 있는 내용:

- 한 페이지를 여러 청크로 나누는 것이 필요한가
- 페이지 경계보다 section 경계가 더 좋은가
- 너무 긴 청크가 임베딩 성능을 저하하는가
- 긴 문서에서 청크 크기와 overlap의 적절한 값은 무엇인가

### 3.2 유사한 전문용어가 여러 문서에서 반복된다

같은 기술분류의 특허는 비슷한 용어와 표현을 반복한다. 예를 들어 배터리 특허에는 전극,
전해질, 충전, 방전, 셀, 모듈 같은 표현이 여러 문서에서 공통으로 나타난다.

따라서 단순 키워드 일치만으로 정답 문서를 찾기 어렵고 다음 능력을 평가할 수 있다.

- 문서의 구체적인 기술적 차이를 구분하는 능력
- BM25와 Vector 검색의 역할 차이
- Hybrid 검색이 유사 문서 사이에서 정답 순위를 높이는지
- Reranker가 hard negative를 구분하는지

### 3.3 핵심 근거가 문서 중간·후반에 존재한다

특허의 제목과 초록만으로는 구체적인 실시 방법이나 청구 조건을 알 수 없다. 실제 질문의
근거는 실시예, 상세한 설명, 청구항처럼 문서 중간과 후반에 존재할 가능성이 높다.

이를 이용해 다음 문제를 측정한다.

- 문서 앞부분만 임베딩했을 때 발생하는 정보 손실
- 문서 후반의 정답 청크 검색 성공률
- section 위치에 따른 검색 성능 차이
- 부모 문서가 검색됐지만 정확한 근거 청크는 찾지 못하는 경우

### 3.4 Section 기반 청킹이 자연스럽다

특허 문서는 법정 문서 구조가 비교적 명확하다. 따라서 단순 글꼴 크기 휴리스틱보다
문서의 논리적 section을 이용한 청킹이 가능하다.

예:

```text
[기술분야]
...

[배경기술]
...

[발명의 내용]
  [해결하려는 과제]
  [과제의 해결 수단]
  [발명의 효과]

[발명을 실시하기 위한 구체적인 내용]
...

[청구범위]
...
```

이를 이용해 Fixed, Page, Section, Contextual Section, Parent-Child 검색을 공정하게
비교할 수 있다.

### 3.5 512-token truncation 문제를 직접 검증할 수 있다

`intfloat/multilingual-e5-small`의 최대 입력 길이는 512 tokens다. 2차 실험에서는
Structure와 Contextual 청크 대부분이 512 tokens를 초과했지만, 질문과 관련된 정보가 청크
앞부분에 있어 높은 Recall이 유지됐을 가능성이 있다.

특허 명세서에서는 정답을 청크 중간·후반에 배치한 질문을 별도로 구성할 수 있다.

비교 대상:

- truncation을 허용한 긴 청크
- 실제 tokenizer 기준 384-token 청크
- 480-token 이하 section 청크
- Parent-Child 검색
- Late chunking

이를 통해 긴 청크의 성능이 실제로 좋은지, 앞부분만으로 문서를 식별한 것인지 구분한다.

### 3.6 IPC/CPC 분류로 Hard Negative를 구성할 수 있다

특허에는 IPC 또는 CPC 기술분류가 존재한다. 같은 분류의 다른 특허는 정답 문서와
전문용어가 유사하므로 좋은 hard negative가 된다.

예:

```text
질문 정답: 특정 배터리 열관리 방식 특허
Easy negative: 통신 장비 특허
Hard negative: 같은 배터리 냉각 분야의 다른 특허
```

평가에서는 무작위 negative뿐 아니라 다음 조건의 hard negative를 사용한다.

- 동일 IPC/CPC 분류
- 유사한 발명의 명칭
- 공통 핵심 키워드
- 유사한 청구항 표현
- 다른 해결 수단 또는 실시예

## 4. 프로젝트 목표

### 최종 목표

조밀한 한국어 기술문서에서 파싱·청킹·임베딩·검색 방식이 정확한 근거 청크 검색 성능에
미치는 영향을 측정하고, 실무에 적용 가능한 최적 Hybrid RAG 구성을 도출한다.

### 핵심 연구 질문

1. 실제 임베딩 tokenizer 기준 청킹이 pseudo token 청킹보다 우수한가
2. Page보다 Patent Section 청킹이 정확한 근거 검색에 유리한가
3. Contextual Section은 긴 문서에서 검색 성능을 높이는가
4. Parent-Child 검색은 문서 Recall과 근거 Recall을 동시에 개선하는가
5. Late chunking은 일반 chunk embedding보다 의미 보존에 유리한가
6. BM25, Vector, Hybrid, Reranker는 동일 기술분류의 hard negative를 얼마나 구분하는가
7. 문서 중간·후반 근거에서 truncation 손실이 얼마나 발생하는가

## 5. 3차 실험 격리 전략

같은 Git 저장소를 사용하되 프로젝트 자산은 완전히 분리한다.

### 저장소 폴더

```text
experiments/ko_dense_technical_v3/
  configs/
  PROJECT_PLAN.md
  STATUS.md
```

### 데이터 루트

```text
C:\vectorsearch-data\ko-dense-technical\
  raw\
  processed\
  eval\
  reports\
  index\
```

### Qdrant Collection

```text
ko_dense_technical_v3_fixed
ko_dense_technical_v3_page
ko_dense_technical_v3_section
ko_dense_technical_v3_contextual
ko_dense_technical_v3_parent_child
ko_dense_technical_v3_late
ko_dense_technical_v3_oracle
```

### OpenSearch Index

```text
ko_dense_technical_v3_fixed
ko_dense_technical_v3_page
ko_dense_technical_v3_section
ko_dense_technical_v3_contextual
ko_dense_technical_v3_parent_child
ko_dense_technical_v3_oracle
```

기존 `koreanops_*`와 `ko_unstructured_pdf_*` index 및 collection은 보존한다.

## 6. 데이터 선정 기준

1차 Pilot은 특허 1,000건을 목표로 한다.

필수 조건:

- 한국어 본문 포함
- 최소 5페이지
- 문서 전체 E5 token 3,000 이상
- 512 tokens 초과 페이지 최소 3개
- 발명의 상세한 설명 또는 실시예 존재
- 청구항 존재
- IPC 또는 CPC 분류 존재
- 텍스트 추출 가능 PDF

층화 기준:

- IPC/CPC 대분류
- 문서 길이
- 페이지당 token 밀도
- 청구항 수
- 표·도면 포함 여부
- 공개특허·등록특허 구분

## 7. 파싱 파이프라인

```text
특허 PDF/API/XML
  -> 문서 inventory
  -> PDF text block 추출
  -> 페이지 읽기 순서 복원
  -> 반복 header/footer 제거
  -> 특허 section 제목 탐지
  -> section hierarchy 복원
  -> 문단·청구항·실시예 구조화
  -> tokenizer-aware chunk 생성
```

보존 metadata:

- 출원번호·공개번호·등록번호
- 발명의 명칭
- IPC/CPC
- 출원일·공개일
- 출원인
- section type
- 청구항 번호
- 페이지 범위
- 문서 내 section 순서
- 부모 문서 ID

## 8. 청킹 전략

### Fixed

- E5 tokenizer 기준 384 tokens
- overlap 64 tokens
- 구조를 사용하지 않는 baseline

### Page

- PDF 한 페이지를 하나의 기본 단위로 사용
- 512 tokens 초과 페이지는 별도 subchunk 처리 여부 비교

### Patent Section

- 기술분야, 배경기술, 해결수단, 효과, 실시예, 청구항 경계 사용
- 긴 section은 384~480 token 범위로 하위 분할
- section 제목을 metadata로 보존

### Contextual Section

본문 token 예산과 context 예산을 분리한다.

```text
Context: 최대 64~80 tokens
Body: 최대 400~416 tokens
전체: 특수 token 포함 480 tokens 이하
```

Context 후보:

- 발명의 명칭
- IPC/CPC
- 현재 section
- 상위 section
- 청구항 번호

### Parent-Child

- 작은 child 청크로 검색
- 검색된 child의 parent section을 RAG context로 반환
- 정확한 검색과 충분한 답변 문맥을 분리

### Late Chunking

- 긴 section을 한 번에 token embedding
- 청크 경계에 따라 token embedding을 pooling
- 가능한 모델과 CPU 비용을 subset에서 먼저 검증

## 8.1 `chunking_list` 기반 적용 기술 선정

`chunking_list`의 2026-06-09~2026-06-25 Retrieval/RAG 조사 자료를 검토하여 V3 특허
명세서 실험에 적용할 기술을 다음 세 단계로 분류한다.

### A. 필수 적용 기술

#### 1. Multi-Granularity Hierarchical Retrieval

참고 기술:

- SproutRAG
- Multi-Granularity RAG Benchmark
- Chunking Methods on Retrieval-Augmented Generation

적용 이유:

특허 질문마다 필요한 근거 크기가 다르다. 구성요소 명칭 질문은 짧은 문단으로 충분하지만,
동작 원리나 발명의 효과 질문은 여러 문단 또는 section 전체가 필요하다. 하나의 고정 청크
크기로 모든 질문을 처리하면 작은 청크의 문맥 부족과 큰 청크의 잡음 문제가 동시에 발생한다.

구성:

```text
Level 0: 문장 또는 짧은 문단, 96~192 E5 tokens
Level 1: passage, 320~384 E5 tokens
Level 2: patent section, 최대 480 E5 tokens
Level 3: parent section 또는 section summary
```

각 level은 다음 metadata로 연결한다.

```text
parent_doc_id
parent_section_id
parent_chunk_id
granularity_level
child_chunk_ids
```

검색 방식:

1. 작은 child passage에서 넓게 후보를 검색한다.
2. 같은 parent section에 속한 child 점수를 집계한다.
3. 질문 유형과 점수 분포에 따라 passage 또는 section을 최종 근거로 선택한다.
4. Fixed/Page/Section과 별도로 `hierarchical` 실험군을 만든다.

평가:

- granularity별 Recall@5/10
- parent section Recall
- 정확한 evidence span Recall
- 검색 context token 수
- 정보 효율: 정답 근거 token / 반환 context token

#### 2. Chunk-Page/Section Graph Reranking

참고 기술:

- EviProp
- GraphER
- Chunk-Page Graph RAG 미니 벤치마크

적용 이유:

특허의 정답 근거는 한 청크에 완전히 존재하지 않을 수 있다. 기술적 과제, 해결 수단, 실시예,
청구항이 서로 다른 section에 있지만 같은 발명을 설명하므로 인접·부모·참조 관계가 검색
신호가 될 수 있다.

V3 graph node:

- document
- section
- page
- child passage
- claim

V3 graph edge:

- document → section
- section → page
- section → child passage
- section → next/previous section
- claim → supporting description
- document → IPC/CPC
- patent → cited patent

초기 구현은 별도 Graph DB 없이 Python adjacency table과 JSONL/SQLite edge table로
구현한다.

온라인 처리:

1. BM25와 Vector로 seed 청크를 검색한다.
2. seed의 parent section과 인접 section을 확장한다.
3. seed rank, edge type, 거리, 동일 IPC/CPC 여부로 graph score를 계산한다.
4. 검색 점수와 graph score를 결합하여 parent section 또는 evidence page를 재정렬한다.

비교:

- 단순 chunk top-k
- parent section score aggregation
- 1-hop graph expansion
- graph diffusion reranking

#### 3. Hybrid Retrieval + Reranker Pairing

참고 기술:

- A Hybrid Retrieval and Reranking Framework for Evidence-Grounded RAG
- Evaluating Retriever-Reranker Pairings in RAG
- CompRank
- Reranker Cost-Quality Frontier

적용 이유:

특허에는 정확한 부품명·수치·청구항 표현과 의미적으로 유사한 설명이 함께 존재한다.
따라서 BM25, Dense Vector, Hybrid와 reranker 조합을 독립적으로 평가해야 한다.

1차 후보 생성:

- OpenSearch BM25 top 100
- Qdrant Dense Vector top 100
- RRF 또는 weighted fusion top 100

2차 정렬:

- CPU-friendly cross-encoder top 50
- late-interaction reranker top 50
- 비용이 큰 listwise/LLM reranker는 top 10~20 subset에서만 수행

측정:

- Recall@100: 후보 생성 능력
- nDCG@10, MRR: reranking 능력
- reranker 입력 token
- P50/P95 latency
- query당 CPU 시간
- 품질-비용 Pareto frontier

#### 4. Query-Adaptive `k`

참고 기술:

- Tail-Aware Adaptive-k
- Adaptive-k RAG Context Selection
- Cost-Aware Query Routing

적용 이유:

모든 질문에 고정 top-k를 사용하면 단순 질문에는 잡음과 비용이 증가하고, 복잡한 질문에는
근거가 부족할 수 있다.

구성:

1. 후보 점수 곡선의 감소 폭을 계산한다.
2. relevance-to-noise 전환점 후보를 찾는다.
3. 최소 `k=3`, 최대 `k=20` 범위에서 질문별 k를 정한다.
4. multi-section 또는 비교 질문은 최소 k를 높인다.
5. evidence sufficiency가 부족하면 추가 검색을 한 번 허용한다.

비교:

- fixed k: 5, 10, 20
- adaptive-k
- question-type routed k

평가:

- Recall 및 answer accuracy
- 반환 context token
- RAG latency
- unsupported answer와 hallucination 비율

#### 5. IPC/CPC 기반 Domain-Scoped Retrieval

참고 기술:

- MASDR-RAG
- Topic Is Not Agenda
- Domain-Scoped Retrieval 실험

적용 이유:

전체 특허 corpus가 커지면 비슷한 용어를 쓰는 다른 기술분야 문서가 검색 결과를 희석한다.
반대로 IPC/CPC를 너무 엄격하게 필터링하면 정답을 제거할 수 있다.

비교:

- 전체 corpus 검색
- query에서 예측한 IPC/CPC를 hard filter
- IPC/CPC를 soft boost
- IPC/CPC별 collection 또는 partition routing

권장 기본값은 hard filter가 아니라 soft boost다. Golden Set의 실제 IPC/CPC를 이용해
router 정확도와 잘못된 routing에 따른 Recall 손실을 별도로 계산한다.

#### 6. Evidence Position 및 Context Size 평가

참고 기술:

- Lost in the Evidence?
- AGORA

적용 이유:

V3의 핵심 가설은 문서 중간·후반 근거와 긴 context에서 검색 손실이 발생한다는 것이다.
따라서 일반 Recall 외에 근거 위치와 context 크기에 따른 결과를 반드시 분리한다.

평가 그룹:

```text
문서 앞부분: 0~25%
중간 앞부분: 25~50%
중간 뒷부분: 50~75%
문서 후반: 75~100%
```

추가 실험:

- 동일한 정답 청크를 context 앞·중간·뒤에 배치
- 반환 context를 2K, 4K, 8K tokens로 변경
- top-k 순서 유지와 score-based reorder 비교

#### 7. RAG Pipeline Search

참고 기술:

- RAGSmith
- RAG Pipeline Search Mini Lab

적용 이유:

청킹, retriever, fusion, reranker, top-k를 각각 독립적으로 최적화하면 조합 간 상호작용을
놓칠 수 있다. 다만 46,000개 이상의 전체 조합 탐색은 현재 CPU 환경에 맞지 않으므로
제한된 search space를 사용한다.

탐색 축:

```text
chunking: fixed / page-subchunk / section / hierarchical
retriever: BM25 / vector / RRF
candidate_k: 20 / 50 / 100
reranker: none / cross-encoder / late-interaction
context_k: fixed-5 / fixed-10 / adaptive
IPC/CPC: none / soft boost
```

각 실행은 다음 정보를 기록한다.

- `run_id`, config hash
- 데이터 및 Golden Set 버전
- Recall, MRR, nDCG
- latency와 context tokens
- index 크기와 처리 시간

최종 결과는 단일 최고 점수뿐 아니라 품질·latency·저장 공간의 Pareto frontier로 제시한다.

### B. 선택 적용 기술

#### 1. Late-Interaction Retrieval/Reranking

참고 기술:

- ColBERTSaR
- Hybrid + Dense + Late-Interaction 비용 곡선

token 단위 표현을 보존하므로 유사한 전문용어 사이의 세부 차이 구분에 적합하다. 하지만
인덱스 크기와 CPU 비용이 크므로 1,000문서 subset의 top-50 reranker로 먼저 검증한다.

#### 2. Corrective RAG

참고 기술:

- From BM25 to Corrective RAG

첫 검색의 evidence sufficiency가 낮거나 score tail이 평평하면 다음 중 하나를 한 번 수행한다.

- 기술 용어 query expansion
- claim/section 이름 추가
- BM25와 Vector 비중 변경
- IPC/CPC soft boost 변경

재검색은 무제한 agent loop가 아니라 최대 1회로 제한하고, 개선율과 추가 latency를 측정한다.

#### 3. ANN Search Tuning

참고 기술:

- ANN Search: Recall What Matters

전체 규모가 커진 뒤 Qdrant HNSW 후보 수와 search parameter를 조정한다. 단순 ANN ID
Recall뿐 아니라 Golden evidence Recall, latency, answer quality를 함께 측정한다.

#### 4. Clean/Misleading/Mixed Evidence 평가

참고 기술:

- Evaluating RAG Reliability under Clean, Misleading, and Mixed Retrieval

동일 IPC/CPC hard negative와 충돌 청구항을 context에 의도적으로 섞어 RAG가 잘못된
근거를 따르는지 평가한다. 이는 retriever 선정 후 RAG 신뢰성 단계에서 수행한다.

### C. 이번 V3에서 보류할 기술

| 기술 | 보류 이유 |
| --- | --- |
| DREAM retriever 학습 | retriever 자체 학습과 GPU 자원이 필요해 1차 V3 범위를 초과 |
| Embedding compression/PQ | 검색 품질 기준선 확립 후 운영 최적화 단계에서 수행 |
| Multilingual query interpolation | V3 corpus와 질문을 우선 한국어로 제한 |
| 멀티모달 reranker | 1차 목표는 텍스트 근거 검색이며 도면 이해는 별도 프로젝트 |
| Multi-agent/agent-native retrieval | 검색 기법의 원인 분석을 어렵게 하고 CPU 비용이 큼 |
| ACL·memory governance | 서비스 운영에는 중요하지만 특허 retrieval 품질과 직접 관계가 낮음 |
| MCP server | 검색 성능 검증이 완료된 뒤 노출 계층으로 검토 |

## 9. Golden Set 전략

목표: 수동 검수된 질문 300개

질문 유형:

- 기술 구성요소
- 동작 원리
- 해결하려는 기술적 과제
- 해결 수단
- 발명의 효과
- 실시 조건
- 수치와 범위
- 청구항 조건
- 비교 질문
- 문서 중간·후반 근거 질문

각 질문에 저장할 정보:

```text
question
reference_answer
gold_document_id
gold_section
gold_pages
gold_chunk_span
evidence_text
question_type
evidence_position
hard_negative_document_ids
ipc_cpc
review_status
```

질문 생성 시 제목과 초록만으로 답할 수 있는 질문은 제한한다. 실시예와 청구항에서 질문을
우선 생성하여 긴 문서 검색 능력을 평가한다.

## 10. 검색 실험

비교 대상:

- BM25
- Dense Vector
- RRF Hybrid
- Weighted Hybrid
- Cross-encoder reranker
- Parent-Child
- Late chunking

평가 지표:

- Document Recall@5/10
- Exact Chunk Recall@5/10
- Gold Section Recall@5/10
- Gold Page Recall@5/10
- MRR
- nDCG@10
- Context precision·recall
- Hard-negative rejection rate
- 문서 위치별 Recall
- P50/P95 latency
- 인덱싱 시간과 저장 공간

문서 위치별 평가는 근거 위치를 다음처럼 나눈다.

- 문서 앞부분: 0~25%
- 중간 앞부분: 25~50%
- 중간 뒷부분: 50~75%
- 문서 후반: 75~100%

## 11. 단계별 로드맵

### Phase 1: 데이터 확보와 100문서 Smoke

- KIPRISPlus 데이터 획득 방식 확정
- PDF/API/XML schema 분석
- 100문서 다운로드
- 실제 E5 tokenizer 길이 분석
- 특허 section parser 구현
- Fixed/Page/Section 청킹 smoke
- `experiments/ko_dense_technical_v3/test_cases.yaml` 기반 테스트 케이스 registry 검증
- `koreanops-v3-cases` CLI로 case manifest와 결과 matrix 생성
- 문장·passage·section multi-granularity ID와 parent 관계 생성
- evidence 위치와 IPC/CPC metadata 검증

### Phase 2: 1,000문서 Pilot

- IPC/CPC 층화 1,000문서 선정
- Fixed, Page-subchunk, Section, Contextual, Hierarchical 청킹 생성
- Qdrant/OpenSearch 별도 적재
- Golden 후보 100개 생성 및 검수
- BM25, Vector, RRF 후보 생성 비교
- Parent-Child와 1-hop Chunk-Section Graph reranking
- CPU cross-encoder reranker와 late-interaction subset 비교
- fixed-k와 adaptive-k 비교
- 근거 위치별 검색 성능과 truncation 영향 분석

### Phase 3: 본 실험

- 데이터 규모 확대 여부 결정
- Golden Set 300개 완성
- 임베딩 모델 비교
- IPC/CPC soft boost와 domain routing 실험
- 제한된 RAG pipeline search 수행
- Corrective RAG 1회 재검색 실험
- ANN HNSW 품질·latency 조정
- clean/misleading/mixed evidence 신뢰성 평가
- 최종 검색·RAG 평가

## 12. 2차 데이터의 활용

현재 오피스 PDF 데이터는 폐기하지 않는다. 다음 조건의 Dense Hard Subset을 생성하여
3차 파이프라인의 회귀 테스트로 활용한다.

```text
- 실제 E5 tokenizer 기준 전체 3,000 tokens 이상
- 512 tokens 초과 페이지 3개 이상
- 발표자료 제외
- 설명형 보고서 또는 계약형 행정문서
```

현재 Pilot 100 기준:

- 512 tokens 초과 페이지가 있는 문서: 46개
- 초과 페이지가 3개 이상인 문서: 15개
- 설명형 보고서 초과 페이지 비율: 67.1%
- 계약형 문서 초과 페이지 비율: 64.3%

이 subset은 tokenizer-aware chunking 구현을 빠르게 검증하는 용도로 사용하고, 3차 본 실험의
최종 성능 근거로는 사용하지 않는다.

## 13. 성공 기준

- 모든 청크가 E5 최대 입력 길이를 초과하지 않음
- 문서 후반 근거 질문의 Recall을 별도로 보고
- 동일 IPC/CPC hard negative 포함
- Page 대비 Section 또는 Parent-Child의 근거 Recall 개선
- 고정 granularity 대비 Hierarchical retrieval 성능 비교
- 단순 top-k 대비 Chunk-Section Graph reranking 성능 비교
- fixed-k 대비 adaptive-k의 품질·context token·latency 비교
- retriever+reranker 조합별 품질-비용 Pareto frontier 생성
- IPC/CPC routing 실패에 따른 Recall 손실 보고
- Oracle 또는 구조화 원문 대비 파싱 손실 정량화
- 1,000문서에서 재현 가능한 인덱싱·평가 파이프라인 확보
- 기존 v1/v2 index와 collection count 불변 확인

## 14. 최종 제안

3차 실험은 현재 저장소에서 진행하되 데이터, config, index, collection, 평가 파일과 보고서를
`ko_dense_technical_v3` namespace로 완전히 분리한다.

주 데이터는 한국 특허 명세서 PDF로 선정한다. 특허 명세서는 긴 문서, 조밀한 페이지,
반복되는 전문용어, 명확한 section 구조, 문서 후반 근거와 IPC/CPC hard negative를 모두
제공하므로 장문 기술문서 RAG 성능을 검증하기에 가장 적합하다.

2차 데이터의 조밀 보고서·계약서 subset은 3차 tokenizer-aware 파이프라인의 사전 회귀
테스트로 사용한다.

## 참고 자료

- [KIPRISPlus 특허·실용신안 등록공보](https://www.data.go.kr/data/15053796/fileData.do?recommendDataYn=Y)
- [KIPRISPlus 특허 REST API](https://www.data.go.kr/data/15065437/openapi.do?recommendDataYn=Y)
- [AI Hub 논문자료 요약](https://aihub.or.kr/aihubdata/data/view.do?aihubDataSe=data&currMenu=511&dataSetSn=90&topMenu=100)

내부 기술 조사 근거:

- `chunking_list/2026-06-09.md`: Hybrid retrieval, reranker pairing, Corrective RAG
- `chunking_list/2026-06-10.md`: graph reranking, ANN 평가, position/context 효과
- `chunking_list/2026-06-11.md`: Chunk-Page graph, late interaction, mixed evidence
- `chunking_list/2026-06-12.md`: reranker compression, adaptive-k
- `chunking_list/2026-06-13.md`: dense failure audit, pipeline search
- `chunking_list/2026-06-18.md`: domain-scoped retrieval, query-time graph
- `chunking_list/2026-06-25.md`: SproutRAG multi-granularity retrieval, AGORA 평가 설계
