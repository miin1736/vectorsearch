# V3 Pilot-to-FULL Execution Status

## Summary

V3 FULL 확장 전에 `pilot_1000`에서 QASET 생성 프로토콜을 별도 실험 축으로 분리했다. 같은 parsed/normalized 문서와 같은 검색 인덱스 조건에서 5개 QASET 후보를 생성하고, 기존 3개 기준 청킹 전략으로 retrieval discrimination을 비교했다.

현재 결론은 `qaset_section_balanced`를 **canonical candidate**로 사용하는 것이다. 아직 `manual_review` 50건이 남아 있으므로 최종 `qaset_canonical_reviewed`가 아니라 `qaset_canonical_candidate`로 고정했다.

## Artifacts

| Artifact | Path |
|---|---|
| QASET protocol candidates | `C:\vectorsearch-data\ko-dense-technical\eval\pilot_1000\qaset_protocols` |
| Deterministic review outputs | `C:\vectorsearch-data\ko-dense-technical\eval\pilot_1000\qaset_protocol_reviews` |
| Protocol quality summary | `C:\vectorsearch-data\ko-dense-technical\eval\pilot_1000\qaset_protocol_review_summary.csv` |
| Protocol retrieval summary | `C:\vectorsearch-data\ko-dense-technical\eval\pilot_1000\qaset_protocol_retrieval_summary.csv` |
| Canonical candidate JSONL | `C:\vectorsearch-data\ko-dense-technical\eval\pilot_1000\qaset_canonical_candidate.jsonl` |
| Manual review CSV | `C:\vectorsearch-data\ko-dense-technical\eval\pilot_1000\qaset_canonical_manual_review.csv` |
| Quality report | `reports/ko_dense_technical_v3_qaset_protocol_review_comparison.md` |
| Retrieval discrimination report | `reports/ko_dense_technical_v3_qaset_protocol_retrieval_comparison.md` |

## Protocol Results

| Protocol | Spread R@10 | Avg R@10 | Avg BM25 R@10 | Avg Vector R@10 | Manual Review | Note |
|---|---:|---:|---:|---:|---:|---|
| `qaset_section_balanced` | 0.392 | 0.642 | 0.700 | 0.425 | 0.417 | Best discrimination with lower abstract ratio |
| `qaset_balanced` | 0.361 | 0.658 | 0.717 | 0.445 | 0.450 | Strong baseline, but slightly more abstract-heavy |
| `qaset_late_evidence` | 0.300 | 0.611 | 0.633 | 0.506 | 0.417 | Best late-page coverage, lower method spread |
| `qaset_hard_negative` | 0.275 | 0.706 | 0.653 | 0.619 | 1.000 | Too review-heavy and less BM25/vector separation |
| `qaset_low_lexical_overlap` | 0.025 | 0.012 | 0.014 | 0.003 | 1.000 | Too difficult or under-specified for canonical use |

## Implemented Interfaces

- `koreanops-v3-qaset-protocols build`
  - Builds `qaset_balanced`, `qaset_hard_negative`, `qaset_low_lexical_overlap`, `qaset_late_evidence`, and `qaset_section_balanced`.
- `koreanops-v3-qaset-protocols summarize`
  - Summarizes QASET quality: lexical overlap, hard negatives, late evidence, abstract ratio, manual review ratio, rejected ratio.
- `koreanops-v3-qaset-protocols summarize-retrieval`
  - Summarizes how much each QASET protocol separates the baseline chunking/retrieval results.
- `SentenceTransformerEmbedder`
  - Now sets default model cache env vars under `DATA_ROOT` when the shell did not load `scripts/project-env.ps1`.

## Repro Commands

```powershell
. .\scripts\project-env.ps1

uv run koreanops-v3-qaset-protocols build --limit 120

uv run koreanops-v3-qaset-protocols summarize

uv run koreanops-v3-review-qaset `
  C:\vectorsearch-data\ko-dense-technical\eval\pilot_1000\qaset_protocols\qaset_section_balanced.jsonl `
  C:\vectorsearch-data\ko-dense-technical\eval\pilot_1000\qaset_protocol_reviews\qaset_section_balanced.reviewed.jsonl `
  C:\vectorsearch-data\ko-dense-technical\eval\pilot_1000\qaset_protocol_reviews\qaset_section_balanced.review.csv `
  reports\ko_dense_technical_v3_qaset_section_balanced_review.md

uv run koreanops-v3-qaset-protocols summarize-retrieval
```

## Next Steps

1. `qaset_canonical_manual_review.csv`에서 `manual_review` 50건을 사람이 검수한다.
2. 검수 완료본을 `qaset_canonical_reviewed.jsonl`로 저장한다.
3. `qaset_canonical_reviewed.jsonl` 기준으로 아직 실행하지 않은 pilot 기법을 평가한다.
4. 청킹이 바뀌는 기법은 새 chunk JSONL, OpenSearch index, Qdrant collection을 만든다.
5. retrieval/rerank만 바뀌는 기법은 기존 인덱스를 재사용한다.
6. pilot winner를 선정한 뒤 FULL parse/chunk/index/eval로 확장한다.

## 2026-06-29 Update

`qaset_section_balanced`를 canonical candidate로 승격해 `qaset_canonical_reviewed.jsonl`을 생성했다. 이 파일은 120개 질문으로 구성되며, 70개는 deterministic auto-approved, 50개는 `approved_provisional_review`이다. provisional row는 pilot 비교에는 사용하되 최종 공개 benchmark 전에는 사람이 확인해야 한다.

추가로 `passage` granularity chunking을 구현하고 pilot_1000에 적용했다.

| Chunking | Chunk count | OpenSearch | Qdrant | Notes |
|---|---:|---|---|---|
| `sentence` | 154,444 | indexed | not indexed | Vector indexing is deferred because CPU runtime is expected to exceed 2 hours |
| `passage` | 47,516 | indexed | indexed | Fully evaluated with canonical QASET |

Canonical QASET 기준 주요 결과:

| Rank | Case | Method | Recall@10 | MRR | nDCG@10 | Note |
|---:|---|---|---:|---:|---:|---|
| 1 | `pilot_1000_fixed_512` | `hybrid_weighted` | 0.775 | 0.472 | 0.544 | Highest Recall@10 |
| 2 | `pilot_1000_passage` | `hybrid_rrf` | 0.750 | 0.566 | 0.610 | Best ranking quality among tested methods |
| 3 | `pilot_1000_passage` | `hybrid_weighted` | 0.742 | 0.557 | 0.602 | Strong cost-quality candidate |
| 4 | `pilot_1000_fixed_512` | `bm25` | 0.733 | 0.517 | 0.569 | Fast lexical baseline |
| 5 | `pilot_1000_section` | `hybrid_rrf` | 0.733 | 0.513 | 0.565 | Strong structure-aware baseline |

Current interpretation:

- If FULL selection prioritizes Recall@10 only, `fixed_512 + hybrid_weighted` remains the current winner.
- If ranking quality and answer context order matter, `passage + hybrid_rrf` is now the strongest candidate.
- `sentence` is useful as an experimental upper-granularity probe, but vector indexing cost is high on the current CPU-first PC.
- The next practical pilot cases should reuse existing indexes for hybrid/rerank experiments before attempting full sentence-vector indexing.

## 2026-06-30 Hybrid Tuning Update

기존 `fixed_512`와 `passage` index를 재사용해 hybrid parameter grid를 평가했다. 평가셋은 동일한 `qaset_canonical_reviewed.jsonl` 120 questions를 사용했다.

결과 파일:

- `C:\vectorsearch-data\ko-dense-technical\eval\pilot_1000\hybrid_tuning_summary.csv`
- `reports/ko_dense_technical_v3_hybrid_tuning.md`

주요 결과:

| Candidate | Recall@10 | MRR | nDCG@10 | P95 ms | Decision |
|---|---:|---:|---:|---:|---|
| `fixed_512 + weighted + ck100 + bm25_weight=3` | 0.792 | 0.480 | 0.554 | 120.9 | Recall winner |
| `fixed_512 + weighted + ck30 + bm25_weight=2` | 0.775 | 0.511 | 0.574 | 100.7 | Cost-quality winner |
| `passage + rrf + ck50` | 0.750 | 0.566 | 0.610 | 94.7 | Ranking winner |

Implementation note:

- `hybrid_rrf` evaluation now uses an explicit adapter so `candidate_k` is passed into the hybrid retriever correctly.
- Earlier weighted-hybrid grid results were already valid because `WeightedHybridEvalRetriever` had its own candidate-k setting.

Next action:

1. Decide whether FULL should optimize for Recall@10 or ranking quality.
2. Keep sentence vector indexing deferred unless the user explicitly wants the long CPU run.
3. Use the retained shortlist below for the final pre-FULL check.

## 2026-06-30 Failure Analysis Update

Slice and failure overlap analysis was completed for the three retained hybrid candidates.

Result files:

- `C:\vectorsearch-data\ko-dense-technical\eval\pilot_1000\hybrid_candidate_slice_summary.csv`
- `C:\vectorsearch-data\ko-dense-technical\eval\pilot_1000\hybrid_candidate_question_details.csv`
- `C:\vectorsearch-data\ko-dense-technical\eval\pilot_1000\hybrid_candidate_failure_overlap.csv`
- `reports/ko_dense_technical_v3_hybrid_candidate_failure_analysis.md`

Failure counts:

| Candidate | Failures | Note |
|---|---:|---|
| `fixed_512 + weighted + ck100 + bw3` | 25 | Highest Recall@10, slower and weaker ranking |
| `fixed_512 + weighted + ck30 + bw2` | 27 | Best fixed_512 cost-quality balance |
| `passage + rrf + ck50` | 30 | Best MRR/nDCG and fastest P95 among retained candidates |

Recommended shortlist:

1. `fixed_512 + weighted + ck30 + bm25_weight=2`
2. `passage + rrf + ck50`

Rationale:

- The two fixed_512 candidates share almost the same failure set, so keeping both is redundant.
- `fixed_512` and `passage` have meaningful failure complementarity.
- `fixed_512` is stronger for Recall@10 on method/summary/hard questions.
- `passage` is stronger for ranking quality, especially purpose/result/adversarial ordering.
