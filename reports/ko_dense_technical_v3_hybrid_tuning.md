# V3 Hybrid Tuning Results

## Summary

Canonical QASET 120 questions 기준으로 현재 winner 후보인 `fixed_512`와 `passage`에 대해 hybrid parameter grid를 평가했다. 새 인덱싱 없이 기존 OpenSearch/Qdrant index를 재사용했다.

평가 대상:

- `fixed_512`
- `passage`
- `hybrid_weighted`: `candidate_k` 30/50/100, `bm25_weight` 1/2/3
- `hybrid_rrf`: corrected candidate-k adapter 기준 `candidate_k` 30/50/100

집계 파일:

- `C:\vectorsearch-data\ko-dense-technical\eval\pilot_1000\hybrid_tuning_summary.csv`
- raw grid: `C:\vectorsearch-data\ko-dense-technical\eval\pilot_1000\hybrid_grid`
- corrected RRF grid: `C:\vectorsearch-data\ko-dense-technical\eval\pilot_1000\hybrid_grid_rrf_fixed`

## Top Results

| Rank | Case | Method | candidate_k | BM25 weight | Recall@10 | MRR | nDCG@10 | P95 ms | Interpretation |
|---:|---|---|---:|---:|---:|---:|---:|---:|---|
| 1 | `fixed_512` | `hybrid_weighted` | 100 | 3 | 0.792 | 0.480 | 0.554 | 120.9 | Highest Recall@10 |
| 2 | `fixed_512` | `hybrid_weighted` | 50 | 3 | 0.783 | 0.493 | 0.562 | 107.4 | Recall-focused but cheaper than ck100 |
| 3 | `fixed_512` | `hybrid_weighted` | 30 | 2 | 0.775 | 0.511 | 0.574 | 100.7 | Best fixed_512 balance |
| 4 | `passage` | `hybrid_weighted` | 100 | 2 | 0.758 | 0.555 | 0.604 | 102.3 | Strong balanced passage setting |
| 5 | `passage` | `hybrid_rrf` | 50 | n/a | 0.750 | 0.566 | 0.610 | 94.7 | Best ranking quality |
| 6 | `passage` | `hybrid_weighted` | 50 | 1 | 0.750 | 0.566 | 0.610 | 108.7 | Same ranking quality, slightly slower |

## Interpretation

- Recall@10 우선이면 `fixed_512 + hybrid_weighted + candidate_k=100 + bm25_weight=3`이 현재 최고다.
- 운영 균형점은 `fixed_512 + hybrid_weighted + candidate_k=30 + bm25_weight=2`가 더 낫다. Recall@10은 0.775로 유지하면서 MRR/nDCG가 ck100/bw3보다 좋고 latency도 낮다.
- RAG answer context 순서까지 고려하면 `passage + hybrid_rrf + candidate_k=50`이 가장 매력적이다. Recall@10은 0.750이지만 MRR 0.566, nDCG@10 0.610으로 ranking 품질이 가장 높다.
- `passage + hybrid_weighted + candidate_k=100 + bm25_weight=2`는 Recall@10 0.758, nDCG@10 0.604로 passage 계열의 Recall을 조금 끌어올린 절충안이다.

## Decision For Next Pilot Stage

다음 pilot 비교에서는 세 후보를 유지한다.

1. Recall winner: `fixed_512 + weighted + ck100 + bm25_weight=3`
2. Cost-quality winner: `fixed_512 + weighted + ck30 + bm25_weight=2`
3. Ranking winner: `passage + rrf + ck50`

FULL 확장 전에는 이 세 후보를 기준으로 failure analysis와 question-type/difficulty slice를 비교한다.

