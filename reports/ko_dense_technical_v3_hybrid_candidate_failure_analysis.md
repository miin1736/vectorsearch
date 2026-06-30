# V3 Hybrid Candidate Failure Analysis

## Summary

Canonical QASET 120 questions 기준으로 FULL 후보 3개를 slice/failure 관점에서 비교했다.

분석 파일:

- `C:\vectorsearch-data\ko-dense-technical\eval\pilot_1000\hybrid_candidate_slice_summary.csv`
- `C:\vectorsearch-data\ko-dense-technical\eval\pilot_1000\hybrid_candidate_question_details.csv`
- `C:\vectorsearch-data\ko-dense-technical\eval\pilot_1000\hybrid_candidate_failure_overlap.csv`

## Candidate Summary

| Candidate | Recall@10 | MRR | nDCG@10 | P95 ms | Failures |
|---|---:|---:|---:|---:|---:|
| `fixed_512 + weighted + ck100 + bw3` | 0.792 | 0.480 | 0.554 | 120.9 | 25 |
| `fixed_512 + weighted + ck30 + bw2` | 0.775 | 0.511 | 0.574 | 100.7 | 27 |
| `passage + rrf + ck50` | 0.750 | 0.566 | 0.610 | 94.7 | 30 |

## Slice Findings

- `fixed_512 + weighted + ck100 + bw3` is the best Recall@10 candidate, especially on `hard` questions: Recall@10 0.860.
- `fixed_512 + weighted + ck30 + bw2` is a better operating point than ck100/bw3 when latency and ranking quality matter: lower P95 and higher MRR/nDCG.
- `passage + rrf + ck50` is strongest for ranking quality and adversarial ordering: adversarial MRR 0.575 and nDCG@10 0.618.
- `passage + rrf + ck50` is particularly strong on `purpose` and `result` ranking quality, but weaker on `method` and `summary` Recall@10.
- `fixed_512` candidates are stronger on `method`, `summary`, and `hard` Recall@10.

## Failure Overlap

| Pair | Shared failures | A-only | B-only | Interpretation |
|---|---:|---:|---:|---|
| `fixed_recall_winner` vs `fixed_cost_quality` | 24 | 1 | 3 | Mostly same failure set |
| `fixed_recall_winner` vs `passage_ranking_winner` | 19 | 6 | 11 | Meaningful complementarity |
| `fixed_cost_quality` vs `passage_ranking_winner` | 20 | 7 | 10 | Meaningful complementarity |

The failure union across the 3 candidates is 38 questions. `fixed_512` and `passage` fail on partially different questions, so both should remain in the final pilot shortlist.

## Recommendation

Do not choose a single FULL strategy yet.

Keep 2 candidates for the final pre-FULL check:

1. `fixed_512 + weighted + ck30 + bm25_weight=2`
   - Best cost-quality balance.
   - Uses fewer candidates than ck100 and improves ranking metrics over the raw Recall winner.
2. `passage + rrf + ck50`
   - Best ranking quality.
   - Better for RAG context ordering and answer generation.

Use `fixed_512 + weighted + ck100 + bm25_weight=3` only if the final objective is maximum Recall@10 regardless of latency and ordering quality.

