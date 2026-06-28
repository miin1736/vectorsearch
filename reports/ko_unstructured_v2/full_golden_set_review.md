# Full Golden Set Review

Run date: 2026-06-27

## Scope

- Source candidates: `C:\vectorsearch-data\ko-unstructured\eval\full\golden_questions_candidates.jsonl`
- Reviewed output: `C:\vectorsearch-data\ko-unstructured\eval\full\golden_questions_reviewed.jsonl`
- Human review CSV: `C:\vectorsearch-data\ko-unstructured\eval\full\golden_questions_review.csv`
- Full review report: `C:\vectorsearch-data\ko-unstructured\reports\full_golden_set_review.md`

The review uses deterministic checks only. High-confidence defects are auto-rejected; softer
quality concerns are retained as flags for manual inspection.

## Review result

| Item | Count |
| --- | ---: |
| Questions reviewed | 300 |
| Auto-approved | 294 |
| Auto-rejected | 6 |
| Question types | 50 each across fact/procedure/comparison/numeric/condition/summary |

Auto-reject reasons:

- fallback question template: 5
- duplicate question: 1
- too-short evidence: 1

Manual-review flags:

- low lexical overlap: 98
- missing question mark: 48
- very short answer: 17

Low lexical overlap was not used as an auto-reject reason because Korean tokenization and source
encoding can make lexical overlap conservative. It should be treated as a manual-review queue, not
as proof that the question is invalid.

## Reviewed retrieval result

These metrics exclude only the 6 auto-rejected questions and keep document/page-aware scoring.

| Corpus | Method | Recall@10 | MRR | nDCG@10 | P50 ms | P95 ms |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Page | BM25 | 0.2551 | 0.1727 | 0.1924 | 49.16 | 66.02 |
| Page | Vector | 0.4626 | 0.3181 | 0.3527 | 38.12 | 59.22 |
| Page | RRF Hybrid | 0.4558 | 0.2781 | 0.3206 | 75.92 | 94.18 |
| Page | Weighted Hybrid | 0.3095 | 0.2366 | 0.2543 | 73.08 | 93.61 |
| Structure | BM25 | 0.3197 | 0.2019 | 0.2302 | 48.68 | 68.08 |
| Structure | Vector | **0.5680** | **0.3899** | **0.4323** | **36.14** | **59.94** |
| Structure | RRF Hybrid | 0.5578 | 0.3102 | 0.3695 | 75.21 | 96.63 |
| Structure | Weighted Hybrid | 0.3810 | 0.2627 | 0.2918 | 75.58 | 95.85 |

## Paired comparison

Structure Vector remains the strongest practical retriever after Golden Set review.

| Metric | Structure Vector - Page Vector | 95% bootstrap CI |
| --- | ---: | --- |
| Recall@10 | +0.1054 | +0.0476 to +0.1633 |
| MRR | +0.0718 | +0.0280 to +0.1149 |
| nDCG@10 | +0.0795 | +0.0353 to +0.1246 |

Recall@10 outcomes:

- Structure-only hits: 57
- Page-only hits: 26
- Ties: 211

## Conclusion

The full-data retrieval conclusion is now strong enough to use in a portfolio:

1. Structure-aware chunking outperforms page chunking on the full 9,491-document corpus.
2. Dense vector retrieval clearly beats BM25 for this semantic Korean PDF benchmark.
3. RRF Hybrid approaches Vector Recall@10, but loses on MRR/nDCG and roughly doubles latency.
4. BM25-heavy weighted hybrid is not appropriate for the current Golden Set.

Before calling the benchmark final, manually inspect the flagged Golden questions and rerun the
same evaluation command against the manually approved JSONL.
