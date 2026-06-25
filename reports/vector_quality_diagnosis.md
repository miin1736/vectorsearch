# Vector Retrieval Quality Diagnosis

Run date: 2026-06-08

## Scope

This diagnosis explains why vector retrieval has the best latency but weaker ranking quality than
BM25 and Hybrid retrieval on the current KoreanOps-RAG validation set.

- Documents: 22,000
- Validation questions: 440
- Diagnostic artifacts:
  - `C:\vectorsearch-data\eval\vector_diagnostics\vector_quality_summary.json`
  - `C:\vectorsearch-data\eval\vector_diagnostics\vector_quality_details.csv`

## Current Baseline

| Method | Recall@10 | MRR | P50 latency ms | P95 latency ms |
| --- | ---: | ---: | ---: | ---: |
| BM25 | 1.0000 | 0.9943 | 47.30 | 51.21 |
| Vector | 0.9864 | 0.9264 | 30.72 | 46.98 |
| Hybrid RRF | 1.0000 | 0.9795 | 83.43 | 94.28 |

Vector search is fast, but it places the gold document lower than BM25 in a small number of ticket
queries. Hybrid recovers these cases through BM25.

## Diagnostic Framework

### 1. Embedding Model Or Usage

Question: is the vector ranking drop caused by the embedding model or the way the model is used?

Checks:

- Compare the current vector query against an E5-style `query: ` prefixed query.
- Track Recall@5, Recall@10, MRR, and miss@10.
- If prefixing improves rank, model usage is likely a problem.
- If prefixing worsens rank, the current index/query text mismatch is not fixed by query prefix alone.

Result:

| Variant | Recall@5 | Recall@10 | MRR | Miss@10 |
| --- | ---: | ---: | ---: | ---: |
| Current vector | 0.9750 | 0.9864 | 0.9272 | 6 |
| Query prefix only | 0.9591 | 0.9727 | 0.8764 | 12 |

Interpretation:

Query prefixing alone made results worse. This does not prove that the model is optimal, but it
shows the immediate regression is not solved by adding `query: ` only at search time. If E5 prefixes
are tested seriously, documents should be re-indexed with `passage: ` and queries should use
`query: ` together.

### 2. Chunking Or Document Shape

Question: is vector retrieval losing quality because one embedding represents too much mixed ticket
content?

Current implementation:

- `ticket_to_document()` builds one document from subject, description, resolution, and tags.
- `log_to_document()` builds one document from the log message.
- Qdrant indexes `row["content"]` directly.
- There is no semantic chunking, field-level embedding, or parent-child retrieval yet.

Length bucket result:

| Gold content length | Questions | Vector Recall@10 | Vector MRR | Vector miss@10 | Hybrid MRR |
| --- | ---: | ---: | ---: | ---: | ---: |
| <250 | 40 | 1.0000 | 1.0000 | 0 | 1.0000 |
| 250-499 | 32 | 1.0000 | 1.0000 | 0 | 1.0000 |
| 500-999 | 186 | 0.9946 | 0.9636 | 1 | 0.9841 |
| 1000-1999 | 177 | 0.9718 | 0.8628 | 5 | 0.9657 |
| >=2000 | 5 | 1.0000 | 0.8000 | 0 | 1.0000 |

Interpretation:

The strongest signal is document shape. Vector misses are concentrated in longer ticket documents,
especially 1000-1999 characters. One embedding for subject + description + resolution + tags is
probably diluting the query-relevant part.

### 3. Retriever Method Or Data

Question: is the vector retriever disadvantaged by query/data characteristics?

Source type result:

| Source type | Questions | BM25 MRR | Vector MRR | Hybrid MRR | Vector miss@10 |
| --- | ---: | ---: | ---: | ---: | ---: |
| log | 40 | 1.0000 | 1.0000 | 1.0000 | 0 |
| ticket | 400 | 0.9938 | 0.9199 | 0.9774 | 6 |

Interpretation:

Logs are not the problem in the current validation set. The drop is ticket-specific. The validation
questions are deterministic questions generated from the gold document text, so lexical overlap is
high. That gives BM25 a natural advantage. Hybrid works because it keeps vector recall while allowing
BM25 to rescue exact-token and entity-heavy cases.

## Failure Examples

All vector miss@10 cases are tickets. BM25 ranked every one of these at rank 1, and Hybrid recovered
each into the top 10.

| Question id | Gold length | BM25 rank | Vector rank | Hybrid rank |
| --- | ---: | ---: | ---: | ---: |
| 48 | 1755 | 1 | 37 | 5 |
| 199 | 629 | 1 | 14 | 5 |
| 208 | 1008 | 1 | not in top 50 | 7 |
| 321 | 1090 | 1 | 11 | 3 |
| 361 | 1181 | 1 | 17 | 2 |
| 426 | 1417 | 1 | 11 | 4 |

## Conclusion

Primary cause:

- Chunking/document-shape issue. Long ticket documents are represented by one dense vector, which
  weakens ranking when only part of the ticket matches the query intent.

Secondary cause:

- Retriever/data issue. The validation questions have strong lexical overlap with gold documents,
  so BM25 is favored on exact terms, product names, and ticket-specific wording.

Not confirmed as the primary cause:

- Embedding model issue. The current `intfloat/multilingual-e5-small` setup is plausible, but the
  project is not yet using the full E5 `query: `/`passage: ` convention. Query prefix only worsened
  ranking, so a fair embedding-model test requires re-indexing variants.

## Recommended Next Experiments

1. Add field-aware ticket documents:
   - subject + description chunk
   - resolution chunk
   - tags/metadata text chunk
   - keep parent `ticket_id` for result collapsing

2. Add E5 prefix indexing variant:
   - index documents as `passage: {content}`
   - search queries as `query: {question}`
   - compare against the current no-prefix baseline

3. Add embedding model comparison:
   - `intfloat/multilingual-e5-small`
   - `BAAI/bge-m3` on a limited subset first
   - evaluate Recall@10, MRR, nDCG@10, index time, and p50/p95 latency

4. Keep Hybrid as the default production candidate:
   - current Hybrid gets Recall@10 1.0000 and MRR 0.9795
   - it recovers all vector miss@10 examples in this validation run

## Follow-up Experiment Results

### Field-aware chunking

Implemented:

- `koreanops-build-field-chunks`
- `configs/field_chunks.yaml`
- Qdrant collection: `koreanops_documents_field_chunks`
- OpenSearch index: `koreanops_documents_field_chunks`
- Parent-aware evaluation using `metadata.parent_doc_id`

Artifact:

- `C:\vectorsearch-data\processed\documents_field_chunks.jsonl`
- `C:\vectorsearch-data\eval\retrieval_metrics_field_chunks.csv`

Corpus size:

- Original documents: 22,000
- Field chunks: 82,019

Result:

| Variant | Method | Recall@10 | MRR | nDCG@10 | P50 latency ms | P95 latency ms |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Original document | Vector | 0.9864 | 0.9264 | 0.9414 | 30.72 | 46.98 |
| Field chunks | Vector | 0.9682 | 0.8489 | 0.8775 | 46.64 | 47.82 |
| Original document | Hybrid | 1.0000 | 0.9795 | 0.9846 | 83.43 | 94.28 |
| Field chunks | Hybrid | 0.9955 | 0.9527 | 0.9630 | 94.06 | 97.04 |

Interpretation:

Simple field-aware chunking does not improve the current validation set. It increases the search
space and often splits the terms needed by deterministic validation questions across multiple
chunks. Parent-aware collapse fixes duplicate parent scoring, but it does not recover the ranking
loss. The earlier "long ticket document" signal is therefore not solved by naive field splitting.

### E5 prefix indexing

Implemented:

- `embedding.document_prefix`
- `embedding.query_prefix`
- `configs/e5_prefix.yaml`
- Qdrant collection: `koreanops_documents_e5_prefix`

Artifact:

- `C:\vectorsearch-data\eval\retrieval_metrics_e5_prefix.csv`

Result:

| Variant | Method | Recall@10 | MRR | nDCG@10 | P50 latency ms | P95 latency ms |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Original no-prefix | Vector | 0.9864 | 0.9264 | 0.9414 | 30.72 | 46.98 |
| E5 passage/query prefix | Vector | 0.9659 | 0.8686 | 0.8928 | 46.73 | 47.69 |
| Original no-prefix | Hybrid | 1.0000 | 0.9795 | 0.9846 | 83.43 | 94.28 |
| E5 passage/query prefix | Hybrid | 0.9977 | 0.9588 | 0.9683 | 93.91 | 95.33 |

Interpretation:

The full E5 prefix convention also does not improve this validation set. The current vector
weakness is therefore less likely to be a simple E5 usage error. The validation data is heavily
lexical and ticket-specific, and BM25 is still the strongest ranking signal.

### Embedding-aware document text

Implemented:

- `RagDocument.embedding_text`
- Qdrant indexing now embeds `embedding_text` when present and falls back to `content`
- `configs/embedding_aware.yaml`
- Qdrant collection: `koreanops_documents_embedding_aware`

Artifact:

- `C:\vectorsearch-data\processed\documents_embedding_aware.jsonl`
- `C:\vectorsearch-data\eval\retrieval_metrics_embedding_aware.csv`

Result:

| Variant | Method | Recall@10 | MRR | nDCG@10 | P50 latency ms | P95 latency ms |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Original content | Vector | 0.9864 | 0.9264 | 0.9414 | 30.72 | 46.98 |
| Embedding-aware text | Vector | 0.9864 | 0.9207 | 0.9370 | 46.57 | 47.58 |
| Original content | Hybrid | 1.0000 | 0.9795 | 0.9846 | 83.43 | 94.28 |
| Embedding-aware text | Hybrid | 1.0000 | 0.9769 | 0.9827 | 93.83 | 95.15 |

Interpretation:

Embedding-aware text keeps Recall@10 at the same level as the original vector baseline, but it does
not improve MRR or nDCG@10. The extra labels and metadata terms may help recall slightly at lower
cutoffs, but they do not improve gold-document rank placement on this validation set.

## Updated Diagnosis

Current best explanation:

1. The validation questions favor lexical overlap, exact terms, and ticket-specific wording.
2. Vector search is semantically close enough for high recall, but weaker at rank-1 placement.
3. Naive field chunking loses useful cross-field context and expands the candidate space.
4. E5 prefixing is not beneficial for this already processed text distribution.
5. Hybrid remains the best retrieval choice because BM25 rescues exact-match cases while vector
   still contributes semantic candidates.
6. Embedding-aware text is now supported by the pipeline, but the first formulation does not improve
   ranking quality.

Next recommended experiment:

- Do not continue with naive chunking.
- Query-type stratification confirms that vector misses are concentrated in ticket resolution/action
  cases:
  - resolution_action: 294 questions, vector miss@10 5
  - issue_symptom: 106 questions, vector miss@10 1
  - log_pattern_severity: 40 questions, vector miss@10 0
- Next test weighted RRF or BM25-heavy Hybrid, for example:
  - BM25 weight 0.7 / vector weight 0.3
  - BM25 top 80 + vector top 40
  - field-specific BM25 boost on title/subject

Weighted RRF follow-up result:

- Best tested setting: BM25 weight `2.0`, vector weight `1.0`
- Recall@10: `1.0000`
- MRR: `0.9837`
- nDCG@10: `0.9878`
- This improves over equal-weight baseline Hybrid MRR `0.9795` and nDCG@10 `0.9846`.

Contextual chunking follow-up result:

- Contextual chunk count: 82,019
- Contextual Vector Recall@10: `0.9909`
- Contextual Vector MRR: `0.9468`
- Contextual Vector nDCG@10: `0.9577`
- This improves over baseline Vector MRR `0.9264` and nDCG@10 `0.9414`.
- Contextual BM25 is currently strongest on this validation set:
  - Recall@10: `1.0000`
  - MRR: `0.9966`
  - nDCG@10: `0.9975`

## Embedding Model Subset Comparison

Run date: 2026-06-20

A 10,000-row contextual chunk subset was built to compare `intfloat/multilingual-e5-small` against `BAAI/bge-m3` without paying the full 82,019-row CPU indexing cost.

| Model | Method | Recall@10 | MRR | nDCG@10 | P50 latency ms | P95 latency ms |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| multilingual-e5-small | Vector | 1.0000 | 0.9861 | 0.9896 | 35.56 | 50.81 |
| BAAI/bge-m3 | Vector | 0.9977 | 0.9868 | 0.9894 | 148.48 | 175.96 |
| multilingual-e5-small | Hybrid | 1.0000 | 0.9977 | 0.9983 | 83.58 | 98.12 |
| BAAI/bge-m3 | Hybrid | 1.0000 | 0.9989 | 0.9992 | 198.67 | 219.77 |

Conclusion: BGE-M3 does not currently justify full-scale indexing on this CPU-first PC. It gives only a tiny ranking improvement on the subset and substantially worsens latency.
