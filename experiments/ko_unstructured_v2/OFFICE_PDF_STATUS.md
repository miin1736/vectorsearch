# Office PDF Hybrid RAG Status

Last updated: 2026-06-27

## Objective

Improve Korean office PDF retrieval while keeping label JSON evaluation-only. Compare Fixed,
Page, Structure, Contextual, and Oracle chunk corpora.

## Dataset

- [x] PDF inventory verified: 9,491
- [x] Label document inventory verified: 9,491
- [x] PDF/label ID mismatch: 0
- [x] Full manifest generated
- [x] Stratified Validation pilot manifest generated: 100 documents
- [x] Full 9,491-document corpus parsed

## Implemented

- [x] ZIP-streamed inventory and PyMuPDF parser
- [x] page blocks, font metadata, reading-order heuristic, header/footer cleanup
- [x] PDF-only normalized documents and evaluation-only Oracle documents
- [x] Fixed, Page, Structure, Contextual, and Oracle chunks
- [x] Ollama Golden Set candidate generator
- [x] parsing and chunking quality evaluators
- [x] parent/page-aware retrieval evaluator with bootstrap confidence intervals
- [x] grounded RAG evaluator and Korean character-bigram F1 proxy
- [x] isolated Qdrant/OpenSearch configs for all corpus variants

## Pilot 100 Results

- Parsed PDFs: 100
- Parsed/Oracle pages: 644
- Page extraction success: 1.0000
- Character precision: 0.6696
- Character recall: 0.7421
- Normalized edit similarity: 0.6933
- Parsing-comparable Oracle pages: 265
- Non-text/image-description Oracle pages excluded from character scoring: 379
- Fixed chunks: 184
- Page chunks: 644
- Structure chunks: 168
- Contextual chunks: 168
- Oracle chunks: 644
- Ollama Golden Set smoke: 30 questions generated, one fallback pending revision
- [x] Five pilot Qdrant collections and OpenSearch indexes created
- [x] Pilot retrieval evaluation completed

## Provisional Retrieval Results

These results use 30 review-pending questions and are not final.

| Corpus | Method | Recall@10 | MRR | nDCG@10 |
| --- | --- | ---: | ---: | ---: |
| Fixed | Vector | 0.900 | 0.850 | 0.863 |
| Page | Vector | 0.933 | 0.856 | 0.875 |
| Structure | Vector | 0.933 | 0.848 | 0.868 |
| Contextual | Vector | 0.900 | 0.828 | 0.846 |
| Oracle | Vector | 0.967 | 0.825 | 0.861 |
| Page | RRF Hybrid | 0.900 | 0.666 | 0.724 |
| Oracle | RRF Hybrid | 0.933 | 0.698 | 0.754 |

Vector retrieval currently leads BM25 and Hybrid. BM25-heavy weighting is harmful on this pilot.
Page and Structure are the strongest practical variants; manual QA review and the 1,000-document
pilot are required before selecting a winner.

## Full Retrieval Results

- Parsed PDFs: 9,491
- Parsed pages: 43,614
- Page chunks: 42,676
- Structure chunks: 18,789
- Golden questions: 300 generated, 294 auto-approved, 6 auto-rejected
- Full parsing normalized edit similarity: 0.7037
- Full parsing page extraction success: 0.9734

Reviewed Golden Set artifacts:

- Reviewed JSONL: `C:\vectorsearch-data\ko-unstructured\eval\full\golden_questions_reviewed.jsonl`
- Review CSV: `C:\vectorsearch-data\ko-unstructured\eval\full\golden_questions_review.csv`
- Review report: `C:\vectorsearch-data\ko-unstructured\reports\full_golden_set_review.md`

| Corpus | Method | Recall@10 | MRR | nDCG@10 | P50 ms |
| --- | --- | ---: | ---: | ---: | ---: |
| Page | Vector | 0.4626 | 0.3181 | 0.3527 | 38.12 |
| Page | RRF Hybrid | 0.4558 | 0.2781 | 0.3206 | 75.92 |
| Structure | Vector | **0.5680** | **0.3899** | **0.4323** | **36.14** |
| Structure | RRF Hybrid | 0.5578 | 0.3102 | 0.3695 | 75.21 |

Structure Vector improved over Page Vector by `+0.1054` Recall@10 on the reviewed set. The paired
bootstrap 95% confidence interval is `+0.0476` to `+0.1633`, so Structure is the current winner.
The result is now suitable as a portfolio-facing retrieval conclusion, with the caveat that rows
with manual-review flags should still be inspected before calling the benchmark final.

## Full RAG Results

- RAG sample: 200 approved/revised reviewed Golden questions
- Retriever/generator setup: Structure Vector top-5 + local Ollama
- Output: `C:\vectorsearch-data\ko-unstructured\eval\full\rag_structure_vector_200.csv`
- Summary: `C:\vectorsearch-data\ko-unstructured\eval\full\rag_structure_vector_200_summary.csv`

| Metric | Value |
| --- | ---: |
| Gold doc/page in retrieved context | 0.525 |
| Cites retrieved context | 1.000 |
| Unsupported / abstained answer rate | 0.070 |
| Korean token/bigram F1 proxy | 0.0291 |
| P50 latency | 10.32 s |
| P95 latency | 17.95 s |

RAG quality is currently retrieval-limited: gold doc/page coverage at top-5 is 52.5%. Source
citations are now appended deterministically by the application layer rather than left to the LLM.

## Remaining

- [ ] Manually review and approve pilot Golden questions
- [x] Start Docker Desktop Linux engine
- [x] Index five pilot corpora in isolated collections/indexes
- [x] Run BM25, Vector, RRF, and weighted Hybrid pilot evaluation
- [x] Supersede the planned 1,000-document pilot with the full 9,491-document run
- [x] Auto-review the final 300-question Golden Set
- [ ] Manually inspect flagged Golden questions
- [x] Parse and index all 9,491 documents
- [x] Run full retrieval comparison and select the provisional winner
- [x] Run 200-question RAG evaluation
- [ ] Complete final reports and failure analysis

## Artifact Paths

- Full manifest: `C:\vectorsearch-data\ko-unstructured\processed\office_manifest.jsonl`
- Pilot processed data: `C:\vectorsearch-data\ko-unstructured\processed\pilot_100`
- Pilot evaluation: `C:\vectorsearch-data\ko-unstructured\eval\pilot_100`
- Pilot reports: `C:\vectorsearch-data\ko-unstructured\reports`
- Full processed data: `C:\vectorsearch-data\ko-unstructured\processed\full`
- Full evaluation: `C:\vectorsearch-data\ko-unstructured\eval\full`
- Full report: `reports/ko_unstructured_v2/full_retrieval_experiment.md`
