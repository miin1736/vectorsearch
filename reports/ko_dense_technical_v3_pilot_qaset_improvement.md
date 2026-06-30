# Ko Dense Technical V3 Pilot QASET Improvement

## Summary

pilot_1000 평가용 QASET을 기존 자동 생성 방식에서 balanced candidate 방식으로 개선했다.

기존 QASET은 `summary` 질문이 92%라 BM25가 과도하게 유리했다. 개선본은 질문 유형을
균형화하고, low lexical overlap 및 hard negative 조건을 명시해 검색 난이도가 실제로 올라가도록
구성했다.

## Artifacts

- Previous QASET: `C:\vectorsearch-data\ko-dense-technical\eval\pilot_1000\golden_questions_auto.jsonl`
- Improved QASET: `C:\vectorsearch-data\ko-dense-technical\eval\pilot_1000\golden_questions_balanced.jsonl`
- Previous summary: `C:\vectorsearch-data\ko-dense-technical\eval\pilot_1000\retrieval_case_summary.csv`
- Improved summary: `C:\vectorsearch-data\ko-dense-technical\eval\pilot_1000\retrieval_case_summary_balanced.csv`
- Improved details: `C:\vectorsearch-data\ko-dense-technical\eval\pilot_1000\retrieval_case_details_balanced.csv`

## What Changed

| Item | Previous | Improved |
|---|---:|---:|
| Questions | 100 | 120 |
| Summary questions | 92 | 24 |
| Purpose questions | 5 | 24 |
| Method questions | 0 | 24 |
| Result questions | 0 | 24 |
| Conclusion questions | 0 | 12 |
| Section questions | 3 | 12 |
| Avg lexical overlap | 0.3755 | 0.1962 |
| Low-overlap questions | 5 | 70 |
| Avg hard negatives | not controlled | 10.0 |

The improved QASET adds these fields:

- `qaset_version`
- `difficulty`
- `review_flags`
- `negative_reason`

All rows are marked `candidate`, not final approved questions. This keeps the benchmark honest:
the set is better for pilot analysis, but still needs manual review before being used as a final
portfolio benchmark.

## Retrieval Impact

The improved QASET reduced inflated BM25 scores and exposed more useful differences between methods.

| QASET | Best Recall@10 | Best Method |
|---|---:|---|
| Previous auto | 1.000 | tokenizer_fixed BM25 |
| Improved balanced | 0.775 | fixed_512 BM25 |

Overall top results on the improved QASET:

| Case | Method | Recall@10 | MRR | nDCG@10 | P50 ms |
|---|---|---:|---:|---:|---:|
| fixed_512 | BM25 | 0.775 | 0.543 | 0.597 | 48.0 |
| tokenizer_fixed | hybrid_weighted | 0.767 | 0.531 | 0.586 | 83.8 |
| fixed_512 | hybrid_weighted | 0.767 | 0.499 | 0.563 | 90.8 |
| tokenizer_fixed | BM25 | 0.742 | 0.525 | 0.575 | 47.9 |
| page_subchunk | hybrid_weighted | 0.742 | 0.522 | 0.574 | 84.0 |

## Difficulty Slices

Hard questions:

| Case | Method | Recall@10 | MRR | nDCG@10 |
|---|---|---:|---:|---:|
| fixed_512 | BM25 | 0.880 | 0.627 | 0.686 |
| section | BM25 | 0.880 | 0.582 | 0.652 |
| tokenizer_fixed | BM25 | 0.860 | 0.636 | 0.689 |

Adversarial questions:

| Case | Method | Recall@10 | MRR | nDCG@10 |
|---|---|---:|---:|---:|
| fixed_512 | hybrid_weighted | 0.729 | 0.536 | 0.582 |
| fixed_512 | hybrid_rrf | 0.729 | 0.510 | 0.562 |
| tokenizer_fixed | hybrid_weighted | 0.700 | 0.552 | 0.586 |
| fixed_512 | BM25 | 0.700 | 0.483 | 0.534 |

This is the first V3 result where Hybrid starts to matter in the harder slice. In the previous
auto QASET, BM25 was too easy to beat because the question set was too lexical and too abstract-heavy.

## Remaining Issues

- The QASET is still automatic and marked `candidate`.
- 24 questions are `abstract_based`; these are useful for baseline checks but should not dominate the final set.
- 33 questions have `low_lexical_overlap`; they should be manually checked rather than rejected automatically.
- Some source text still has encoding noise, so final manual review must flag or revise noisy questions.

## Decision

Use `golden_questions_balanced.jsonl` for the next pilot retrieval analysis instead of
`golden_questions_auto.jsonl`.

Do not use it as the final benchmark yet. The next quality step is manual review:

1. Inspect `low_lexical_overlap` rows.
2. Inspect `abstract_based` rows.
3. Revise or reject questions with encoding noise.
4. Keep roughly 100 manually approved pilot questions.
5. Then decide which strategies should be promoted to FULL indexing/evaluation.
