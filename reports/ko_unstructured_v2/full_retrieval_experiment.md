# 한국어 오피스 PDF Full Retrieval 실험

실행일: 2026-06-26

## 실험 범위

- 원본 PDF: 9,491개
- 전체 페이지: 43,614개
- Page 청크: 42,676개
- Structure 청크: 18,789개
- 평가 질문: 300개
- 검색 방식: BM25, Vector, RRF Hybrid, BM25-heavy Hybrid
- 임베딩: `intfloat/multilingual-e5-small`, CPU
- 검색 인프라: OpenSearch, Qdrant

PDF 검색 코퍼스와 라벨 기반 Oracle은 분리했다. 라벨은 파싱 품질 측정, Golden 질문
생성, 정답 문서·페이지 판정에만 사용했다. 검색 적중은 정답 부모 문서뿐 아니라 정답
페이지 범위까지 일치해야 인정했다.

## 전체 파싱 품질

문자 단위 비교가 가능한 Oracle 35,078페이지를 평가했다. 이미지 설명만 존재하는
8,536페이지는 검색 평가용 의미 정보에는 포함하지만 문자 파싱 정확도에서는 제외했다.

| 지표 | 결과 |
| --- | ---: |
| Character precision | 0.6647 |
| Character recall | 0.7885 |
| Normalized edit similarity | 0.7037 |
| Page extraction success | 0.9734 |
| Duplicate ratio | 0.0026 |

9,491개 PDF의 파싱 예외는 0건이었다. 텍스트가 비어 있는 문서는 141개였다.

## Retrieval 결과

| Corpus | Method | Recall@10 | 95% CI | MRR | nDCG@10 | P50 ms | P95 ms |
| --- | --- | ---: | --- | ---: | ---: | ---: | ---: |
| Page | BM25 | 0.2500 | 0.2000–0.3000 | 0.1693 | 0.1886 | 50.58 | 66.20 |
| Page | Vector | 0.4533 | 0.4000–0.5100 | 0.3118 | 0.3457 | 30.47 | 50.88 |
| Page | RRF Hybrid | 0.4467 | 0.3933–0.4967 | 0.2717 | 0.3135 | 79.34 | 98.80 |
| Page | Weighted Hybrid | 0.3000 | 0.2500–0.3533 | 0.2300 | 0.2469 | 77.52 | 95.60 |
| Structure | BM25 | 0.3133 | 0.2600–0.3667 | 0.1978 | 0.2256 | 49.11 | 63.15 |
| Structure | Vector | **0.5567** | **0.5033–0.6133** | **0.3731** | **0.4167** | **30.97** | **52.06** |
| Structure | RRF Hybrid | 0.5500 | 0.4900–0.6033 | 0.3041 | 0.3629 | 82.22 | 103.46 |
| Structure | Weighted Hybrid | 0.3767 | 0.3233–0.4300 | 0.2589 | 0.2878 | 80.29 | 112.06 |

## Page와 Structure의 직접 비교

동일 질문에 대한 paired bootstrap 10,000회 결과:

| Metric | Structure Vector - Page Vector | 95% CI |
| --- | ---: | --- |
| Recall@10 | +0.1033 | +0.0467–+0.1600 |
| MRR | +0.0613 | +0.0212–+0.1021 |
| nDCG@10 | +0.0710 | +0.0296–+0.1132 |

- Structure만 Top 10에 성공한 질문: 57개
- Page만 Top 10에 성공한 질문: 26개
- Structure가 더 높은 reciprocal rank를 기록한 질문: 85개
- Page가 더 높은 reciprocal rank를 기록한 질문: 43개

Structure의 개선 폭은 세 지표 모두 paired bootstrap 신뢰구간이 0을 넘으므로 현재
300문항에서는 일관된 우위로 볼 수 있다.

## 질문 유형별 Vector Recall@10

| Question type | Page | Structure |
| --- | ---: | ---: |
| fact | 0.48 | 0.50 |
| procedure | **0.58** | 0.50 |
| comparison | 0.36 | **0.56** |
| numeric | 0.48 | **0.56** |
| condition | 0.46 | **0.62** |
| summary | 0.36 | **0.60** |

Page는 procedure 질문에서만 더 좋았다. Structure는 특히 comparison, condition,
summary 질문에서 큰 개선을 보였다.

## 결론

1. Full 데이터에서는 Structure Vector가 가장 좋은 품질과 가장 낮은 계열의 지연시간을
   함께 기록했다.
2. Vector는 두 코퍼스 모두 BM25보다 크게 우수했다.
3. RRF Hybrid는 Recall@10이 Vector와 비슷했지만 MRR과 nDCG가 낮고 지연시간은 약
   2.7배였다.
4. 파일럿에서 사용한 BM25-heavy 가중치는 Full semantic 질문에서 명확히 부적합했다.
5. 배포 후보는 Structure Vector이며, Page Vector를 procedure 질문용 비교 기준으로
   유지하는 것이 타당하다.

## 제한사항

- 300개 질문은 Ollama 생성 후 아직 모두 `pending` 상태다.
- 질문은 299개가 고유하며, 2개는 JSON 생성 실패로 deterministic fallback을 사용했다.
- 일부 질문은 문장형이거나 표현이 어색하므로 최종 수치 확정 전 수동 검수가 필요하다.
- 현재 결과는 retrieval 평가이며, 최종 grounded RAG 답변 평가는 별도로 남아 있다.

따라서 청킹·retriever 선택 결론은 파일럿보다 훨씬 뚜렷하지만, 대외 공개용 최종
수치는 Golden Set 수동 검수 후 다시 계산해야 한다.
