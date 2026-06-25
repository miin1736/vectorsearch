# KoreanOps-RAG Progress And Next Plan

Last updated: 2026-06-08

## Current Objective

Build a CPU-first, reproducible Hybrid RAG experiment platform for IT support tickets and system
logs. The current technical focus is explaining and improving why vector retrieval is faster but
has weaker ranking quality than BM25/Hybrid.

## Current Data And Index State

| Asset | Location | Count | Status |
| --- | --- | ---: | --- |
| Normalized tickets | `C:\vectorsearch-data\processed\tickets_full.jsonl` | 20,000 | Ready |
| Normalized logs | `C:\vectorsearch-data\processed\logs_full.jsonl` | 2,000 | Ready |
| Baseline RAG documents | `C:\vectorsearch-data\processed\documents_full.jsonl` | 22,000 | Ready |
| Validation QA set | `C:\vectorsearch-data\eval\validation_questions.jsonl` | 440 | Ready |
| Field chunks | `C:\vectorsearch-data\processed\documents_field_chunks.jsonl` | 82,019 | Ready |
| Embedding-aware documents | `C:\vectorsearch-data\processed\documents_embedding_aware.jsonl` | 22,000 | Ready |
| Baseline Qdrant collection | `koreanops_documents` | 22,000 | Ready |
| Field-chunk Qdrant collection | `koreanops_documents_field_chunks` | 82,019 | Ready |
| E5-prefix Qdrant collection | `koreanops_documents_e5_prefix` | 22,000 | Ready |
| Embedding-aware Qdrant collection | `koreanops_documents_embedding_aware` | 22,000 | Ready |
| Baseline OpenSearch index | `koreanops_documents` | 22,000 | Ready |
| Field-chunk OpenSearch index | `koreanops_documents_field_chunks` | 82,019 | Ready |

## Completed Work

- [x] Environment stabilized with `uv`, Python 3.11, Docker Compose, Qdrant, OpenSearch, and Ollama.
- [x] Large artifacts and model/cache paths are kept under `C:\vectorsearch-data`.
- [x] Ticket/log ingestion and normalized JSONL pipeline implemented.
- [x] Baseline document builder implemented.
- [x] Qdrant vector indexing implemented.
- [x] OpenSearch BM25 indexing implemented.
- [x] BM25, vector, and Hybrid RRF retrievers implemented.
- [x] Validation QA set with 440 questions generated.
- [x] Retrieval evaluation implemented with Recall@5, Recall@10, MRR, nDCG@10, P50 latency, and P95 latency.
- [x] Vector quality diagnostic script implemented.
- [x] Field-aware chunking experiment implemented and evaluated.
- [x] Parent-aware retrieval evaluation added for chunked documents.
- [x] Qdrant indexing resume support added.
- [x] E5 `passage:` / `query:` prefix experiment implemented and evaluated.
- [x] Data-stage `embedding_text` support implemented and evaluated.
- [x] Query-type diagnostic CLI implemented and evaluated.
- [x] Weighted Hybrid evaluation CLI implemented and evaluated.
- [x] Unit tests and ruff checks pass.

## Retrieval Experiment Results

| Variant | Method | Recall@10 | MRR | nDCG@10 | P50 latency ms | P95 latency ms | Metrics file |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| Baseline document | BM25 | 1.0000 | 0.9943 | 0.9958 | 47.30 | 51.21 | `retrieval_metrics_validation.csv` |
| Baseline document | Vector | 0.9864 | 0.9264 | 0.9414 | 30.72 | 46.98 | `retrieval_metrics_validation.csv` |
| Baseline document | Hybrid | 1.0000 | 0.9795 | 0.9846 | 83.43 | 94.28 | `retrieval_metrics_validation.csv` |
| Field chunks | Vector | 0.9682 | 0.8489 | 0.8775 | 46.64 | 47.82 | `retrieval_metrics_field_chunks.csv` |
| Field chunks | Hybrid | 0.9955 | 0.9527 | 0.9630 | 94.06 | 97.04 | `retrieval_metrics_field_chunks.csv` |
| Contextual chunks | BM25 | 1.0000 | 0.9966 | 0.9975 | 48.17 | 54.77 | `retrieval_metrics_contextual_chunks.csv` |
| Contextual chunks | Vector | 0.9909 | 0.9468 | 0.9577 | 43.75 | 50.21 | `retrieval_metrics_contextual_chunks.csv` |
| Contextual chunks | Hybrid | 0.9977 | 0.9835 | 0.9870 | 86.61 | 95.71 | `retrieval_metrics_contextual_chunks.csv` |
| E5 prefix | Vector | 0.9659 | 0.8686 | 0.8928 | 46.73 | 47.69 | `retrieval_metrics_e5_prefix.csv` |
| E5 prefix | Hybrid | 0.9977 | 0.9588 | 0.9683 | 93.91 | 95.33 | `retrieval_metrics_e5_prefix.csv` |
| Embedding-aware text | Vector | 0.9864 | 0.9207 | 0.9370 | 46.57 | 47.58 | `retrieval_metrics_embedding_aware.csv` |
| Embedding-aware text | Hybrid | 1.0000 | 0.9769 | 0.9827 | 93.83 | 95.15 | `retrieval_metrics_embedding_aware.csv` |

## Query-Type Diagnosis Results

Artifacts:

- `C:\vectorsearch-data\eval\query_type_diagnostics\query_type_summary.json`
- `C:\vectorsearch-data\eval\query_type_diagnostics\query_type_details.csv`

| Query group | Questions | Vector Recall@10 | Vector MRR | Hybrid Recall@10 | Hybrid MRR | Vector miss@10 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| log_pattern_severity | 40 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 0 |
| issue_symptom | 106 | 0.9906 | 0.9238 | 1.0000 | 0.9830 | 1 |
| resolution_action | 294 | 0.9830 | 0.9185 | 1.0000 | 0.9754 | 5 |
| ticket source type | 400 | 0.9850 | 0.9199 | 1.0000 | 0.9774 | 6 |

Interpretation:

- Vector retrieval is not failing on logs.
- Most vector misses are ticket resolution/action questions.
- BM25 ranks every vector miss at rank 1.
- Hybrid recovers every vector miss into top 10.
- The next tuning step should be BM25-heavy Hybrid or field boosting, not more naive chunking.

## Weighted Hybrid Results

Artifact:

- `C:\vectorsearch-data\eval\weighted_hybrid_metrics.csv`

| BM25 weight | Vector weight | Recall@10 | MRR | nDCG@10 | P50 latency ms | P95 latency ms |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 0.6 | 1.0 | 0.9977 | 0.9512 | 0.9629 | 93.83 | 95.13 |
| 0.7 | 1.0 | 0.9977 | 0.9533 | 0.9646 | 93.69 | 94.96 |
| 0.8 | 1.0 | 0.9977 | 0.9534 | 0.9646 | 93.65 | 94.95 |
| 0.9 | 1.0 | 0.9977 | 0.9539 | 0.9651 | 93.62 | 95.16 |
| 1.2 | 1.0 | 1.0000 | 0.9797 | 0.9848 | 93.62 | 95.06 |
| 1.5 | 1.0 | 1.0000 | 0.9821 | 0.9866 | 93.75 | 95.16 |
| 2.0 | 1.0 | 1.0000 | 0.9837 | 0.9878 | 93.72 | 95.23 |

Best current retrieval setting:

- Weighted Hybrid with BM25 weight `2.0` and vector weight `1.0`
- It improves over baseline Hybrid:
  - MRR: `0.9795` -> `0.9837`
  - nDCG@10: `0.9846` -> `0.9878`
  - Recall@10 remains `1.0000`

## Contextual Chunking Results

Implemented:

- `koreanops-build-contextual-chunks`
- `configs/contextual_chunks.yaml`
- Qdrant collection: `koreanops_documents_contextual_chunks`
- OpenSearch index: `koreanops_documents_contextual_chunks`

Artifacts:

- `C:\vectorsearch-data\processed\documents_contextual_chunks.jsonl`
- `C:\vectorsearch-data\eval\retrieval_metrics_contextual_chunks.csv`
- `C:\vectorsearch-data\eval\weighted_hybrid_contextual_chunks_metrics.csv`

Corpus size:

- Original documents: 22,000
- Contextual chunks: 82,019

Contextual chunking improved vector ranking over the baseline document index:

- Vector MRR: `0.9264` -> `0.9468`
- Vector nDCG@10: `0.9414` -> `0.9577`
- Vector Recall@10: `0.9864` -> `0.9909`

The strongest result was contextual BM25:

- BM25 MRR: `0.9966`
- BM25 nDCG@10: `0.9975`
- BM25 Recall@10: `1.0000`

Contextual weighted Hybrid also improved ranking, but gave up a small amount of Recall@10:

| BM25 weight | Vector weight | Recall@10 | MRR | nDCG@10 | P50 latency ms | P95 latency ms |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 0.9 | 1.0 | 0.9977 | 0.9696 | 0.9768 | 89.52 | 95.11 |
| 1.0 | 1.0 | 0.9977 | 0.9835 | 0.9870 | 93.13 | 95.04 |
| 1.2 | 1.0 | 0.9977 | 0.9854 | 0.9884 | 93.09 | 95.09 |
| 1.5 | 1.0 | 0.9977 | 0.9873 | 0.9899 | 93.68 | 95.09 |
| 2.0 | 1.0 | 0.9977 | 0.9899 | 0.9919 | 86.59 | 95.11 |

## Current Findings

1. Baseline Hybrid remains the best overall retrieval configuration.
2. Baseline vector retrieval is fastest, but weaker than BM25/Hybrid in rank placement.
3. Naive field chunking made vector ranking worse.
4. E5 prefix indexing made vector ranking worse on the current validation set.
5. The first embedding-aware document text keeps Recall@10 stable but does not improve MRR.
6. The current validation set has strong lexical overlap with gold documents, so BM25 is naturally favored.
7. Query-type diagnosis shows the vector weakness is concentrated in ticket resolution/action cases.
8. BM25-heavy weighted Hybrid improves ranking quality over equal-weight RRF on the current validation set.
9. Contextual chunking is the first chunking strategy that improves vector ranking.
10. Contextual BM25 is currently the strongest pure retriever on this validation set.

## Implemented Code Changes For Current Phase

- `src/koreanops_rag/documents/chunk_documents.py`
  - Creates field-aware ticket chunks while preserving `metadata.parent_doc_id`.
- `src/koreanops_rag/documents/contextual_chunks.py`
  - Creates contextual chunks with parent ticket metadata repeated in every chunk.
- `src/koreanops_rag/evaluation/run_retrieval_eval.py`
  - Adds parent-aware evaluation and duplicate parent collapse.
- `src/koreanops_rag/indexing/qdrant_index.py`
  - Adds `--resume`.
  - Embeds `embedding_text` when present.
- `src/koreanops_rag/retrieval/vector_qdrant.py`
  - Adds configurable document/query prefixes.
- `src/koreanops_rag/documents/build_documents.py`
  - Adds embedding-aware text generation.
- `src/koreanops_rag/schemas.py`
  - Adds `RagDocument.embedding_text`.

## Remaining Plan

### Phase A: Query-Type Diagnosis

- [x] Add heuristic query type labels to validation questions:
  - exact entity/product/version
  - issue symptom
  - resolution/action
  - metadata-like
  - log pattern/severity
- [x] Generate per-query-type metrics for BM25, vector, and Hybrid.
- [x] Identify which query types actually need vector improvement.

### Phase B: Weighted Hybrid Tuning

- [x] Implement weighted RRF or weighted score fusion.
- [x] Test BM25-heavy settings:
  - BM25 1.2 / vector 1.0
  - BM25 1.5 / vector 1.0
  - BM25 2.0 / vector 1.0
- [x] Compare Recall@10, MRR, nDCG@10, and latency against baseline Hybrid.

### Phase C: BM25 Field Boost

- [ ] Add OpenSearch mapping/query variant for title/content field boosting.
- [ ] Test subject/title boost for ticket queries.
- [ ] Compare against current BM25 and Hybrid.

### Phase D: Embedding Model Comparison

- [x] Evaluate `BAAI/bge-m3` on a smaller contextual-chunk subset first because CPU indexing is slow.
- [x] Track index time, latency, Recall@10, MRR, and nDCG@10.
- [x] Only scale to 82,019 contextual chunks if subset results are promising.

### Phase E: Better Validation Set

- [ ] Add questions with lower lexical overlap.
- [ ] Add paraphrased semantic questions.
- [ ] Add metadata-filter questions.
- [ ] Add hard negative cases where BM25 exact match is misleading.

### Phase F: Late Chunking Research Spike

- [ ] Check whether the chosen embedding model exposes token embeddings suitable for late chunking.
- [ ] Prototype on a small subset only.
- [ ] Compare against contextual chunking before scaling.

## Next Immediate Action

The next best step is Phase E: better validation set. The BGE-M3 subset comparison is already near ceiling and does not justify full-scale CPU indexing, so the next useful work is to create lower-lexical-overlap and paraphrased questions that better separate BM25, vector, and hybrid behavior.

Recommended next command after implementation:

```powershell
. .\scripts\project-env.ps1
uv run koreanops-eval-retrieval C:\vectorsearch-data\eval\validation_questions.jsonl C:\vectorsearch-data\eval\retrieval_metrics_contextual_bge_subset.csv --config-path configs\contextual_chunks_bge_subset.yaml --match-parent
```

## Verification

Latest verification:

- `uv run ruff check .`: passed
- `uv run pytest`: 14 passed

## Embedding Model Subset Comparison Results

Run date: 2026-06-20

Implemented:

- `koreanops-build-eval-subset`
- `configs/contextual_subset_e5.yaml`
- `configs/contextual_subset_bge_m3.yaml`
- Qdrant collection: `koreanops_documents_contextual_subset_e5`
- Qdrant collection: `koreanops_documents_contextual_subset_bge_m3`
- OpenSearch index: `koreanops_documents_contextual_subset`

Artifacts:

- `C:\vectorsearch-data\processed\documents_contextual_subset_10000.jsonl`
- `C:\vectorsearch-data\eval\retrieval_metrics_contextual_subset_e5.csv`
- `C:\vectorsearch-data\eval\retrieval_metrics_contextual_subset_bge_m3.csv`

Subset design:

- 10,000 contextual chunks
- All validation gold parent documents are included
- Remaining rows are deterministic negative/context rows from the contextual chunk corpus
- This subset is for model comparison only and is easier than the full 82,019-contextual-chunk index

| Model | Method | Recall@10 | MRR | nDCG@10 | P50 latency ms | P95 latency ms |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| multilingual-e5-small | Vector | 1.0000 | 0.9861 | 0.9896 | 35.56 | 50.81 |
| BAAI/bge-m3 | Vector | 0.9977 | 0.9868 | 0.9894 | 148.48 | 175.96 |
| multilingual-e5-small | Hybrid | 1.0000 | 0.9977 | 0.9983 | 83.58 | 98.12 |
| BAAI/bge-m3 | Hybrid | 1.0000 | 0.9989 | 0.9992 | 198.67 | 219.77 |

Interpretation:

- BGE-M3 slightly improves vector MRR on the 10,000-row subset: `0.9861` -> `0.9868`.
- BGE-M3 vector Recall@10 is slightly lower: `1.0000` -> `0.9977`.
- BGE-M3 vector latency is much higher: P50 `35.56 ms` -> `148.48 ms`.
- BGE-M3 hybrid ranking is slightly higher, but latency is more than 2x the E5 hybrid latency.
- Current recommendation: do not scale BGE-M3 to all 82,019 contextual chunks yet. The quality gain is too small for the CPU latency/indexing cost.

Updated next step:

- Keep `intfloat/multilingual-e5-small` as the default embedding model for full-scale CPU experiments.
- Use contextual chunks as the best vector-improving data strategy so far.
- Move next to Phase E: better validation set with lower lexical overlap, because the current subset comparison is already near ceiling.
