# Validation Evaluation Report

Date: 2026-06-07

## Dataset And QA Ratio

- Full RAG documents: 22,000
- OpenSearch indexed documents: 22,000
- Qdrant points: 22,000
- Validation QA set: 440
- QA/document ratio: 2.0%

Validation set composition:

- Tickets: 400
- Logs: 40

The validation questions were generated deterministically from sampled gold documents. This is
useful for a scalable retrieval smoke/validation benchmark, but it is easier than a human-written
incident query set and can favor lexical BM25 matching.

## Retrieval Metrics

File:

```text
C:\vectorsearch-data\eval\retrieval_metrics_validation.csv
```

| method | questions | recall@5 | recall@10 | mrr | ndcg@10 | p50 latency ms | p95 latency ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| bm25 | 440 | 1.0000 | 1.0000 | 0.9943 | 0.9958 | 47.30 | 51.21 |
| vector | 440 | 0.9750 | 0.9864 | 0.9264 | 0.9414 | 30.72 | 46.98 |
| hybrid | 440 | 0.9977 | 1.0000 | 0.9795 | 0.9846 | 83.43 | 94.28 |

## Hybrid RAG Quality Proxy

File:

```text
C:\vectorsearch-data\eval\rag_quality_hybrid_30.csv
```

Sample size: 30 validation questions.

| metric | value |
| --- | ---: |
| gold document in top-5 context | 30/30, 100.00% |
| non-empty answer | 30/30, 100.00% |
| cites any retrieved context doc_id | 18/30, 60.00% |
| cites gold doc_id | 5/30, 16.67% |
| p50 RAG latency | 10,587.18 ms |
| p95 RAG latency | 17,509.61 ms |
| average answer length | 904 chars |

This is not a full RAGAS evaluation. It measures whether the hybrid retriever supplied the gold
document to the answer generator and whether the local LLM answer cited retrieved document IDs.
The low exact gold citation rate indicates that the prompt should be tightened to require exact
`doc_id` citations from the provided context.

## Interpretation

- BM25 performed best on this validation set because the generated questions preserve many words
  from the gold documents.
- Vector retrieval was faster at p50 and p95 than BM25, but slightly lower on recall and ranking.
- Hybrid achieved perfect Recall@10 and stronger ranking than vector, but did not beat BM25 on
  this synthetic validation set.
- Hybrid RAG successfully generated answers for all sampled questions, but citation discipline
  needs improvement before using the answers as evidence-grade outputs.
