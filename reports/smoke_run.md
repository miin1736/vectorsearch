# Smoke Run Report

Date: 2026-06-03

## Inputs

- Ticket data: `C:\vectorsearch-data\raw\dataset-tickets-multi-lang-4-20k.csv`
- Log data: `C:\vectorsearch-data\raw\HDFS_2k.log`

Kaggle authentication was not configured, so the ticket smoke run used the public Hugging Face
CSV mirror for the same customer-support ticket family.

## Generated Artifacts

- `C:\vectorsearch-data\processed\tickets_smoke.jsonl`: 1,000 tickets
- `C:\vectorsearch-data\processed\logs_smoke.jsonl`: 1,000 logs
- `C:\vectorsearch-data\processed\documents_smoke.jsonl`: 2,000 RAG documents

## Infrastructure

- OpenSearch: indexed 2,000 documents into `koreanops_documents`
- Qdrant: indexed 2,000 documents into `koreanops_documents`
- Qdrant image upgraded to `qdrant/qdrant:v1.18.0` to match `qdrant-client 1.18.0`
- Ollama model: `llama3.1:8b-instruct-q4_K_M`

## Retrieval Smoke Query

Query:

```text
payment API timeout error
```

BM25 top results:

- `ticket_customer_support_hf_customer_support_hf_968`: Problem with Task Sync
- `ticket_customer_support_hf_customer_support_hf_655`: Support needed
- `ticket_customer_support_hf_customer_support_hf_575`: Encountered Issue with Payment Processing

Vector top results:

- `ticket_customer_support_hf_customer_support_hf_788`: Problem with Integration Utilities
- `ticket_customer_support_hf_customer_support_hf_405`: Error throughout Task Synchronization
- `ticket_customer_support_hf_customer_support_hf_968`: Problem with Task Sync

Hybrid top results:

- `ticket_customer_support_hf_customer_support_hf_968`: Problem with Task Sync
- `ticket_customer_support_hf_customer_support_hf_655`: Support needed
- `ticket_customer_support_hf_customer_support_hf_405`: Error throughout Task Synchronization

## RAG Smoke

The Ollama-based answer generator successfully produced a grounded response from hybrid
retrieval context. Console output showed Korean text encoding artifacts in PowerShell, but the
LLM call itself completed successfully.

## Retrieval Metrics Smoke

Output:

```text
C:\vectorsearch-data\eval\retrieval_metrics_smoke.csv
```

| method | questions | recall@5 | recall@10 | mrr | ndcg@10 | p50 latency ms | p95 latency ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| bm25 | 2 | 0.50 | 0.50 | 0.25 | 0.3255 | 45.23 | 48.90 |
| vector | 2 | 0.50 | 0.50 | 0.25 | 0.3255 | 144.32 | 245.02 |
| hybrid | 2 | 0.50 | 0.50 | 0.50 | 0.5000 | 86.19 | 88.42 |

This is a tiny smoke set, not a reliable experiment result. It confirms that the evaluation
pipeline runs end to end and writes metrics.

## Next Step

Build a larger `questions.jsonl` evaluation set with gold document IDs, then run
BM25/vector/hybrid retrieval metrics at medium scale.
