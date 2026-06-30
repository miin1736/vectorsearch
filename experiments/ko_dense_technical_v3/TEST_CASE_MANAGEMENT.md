# V3 Test Case Management

This document is the operating guide for managing advanced chunking and retrieval
experiments in `ko_dense_technical_v3`.

The V3 corpus is now AIHub academic-paper PDF data, not patent data. Patent-only
terms are mapped as follows:

```text
patent section -> paper section
claim -> abstract/introduction/method/result/conclusion/evidence paragraph
IPC/CPC -> research_field / paper_topic / keyword / publication_year
claim_support edge -> section_transition / citation_or_keyword_related / same_topic_related
```

## Registry

All techniques are tracked in:

```text
experiments/ko_dense_technical_v3/test_cases.yaml
```

Each case has one `case_id`, one isolated Qdrant/OpenSearch namespace, and one
evaluation profile. Disabled or deferred techniques remain in the registry with
an explicit reason so the experiment backlog is visible.

Cases should not create separate source files per experiment. A case only selects
shared profiles:

```text
case_id
  -> chunking_profile
  -> retriever_profile
  -> reranker_profile
  -> evaluation_profile
```

The profile catalog lives in:

```text
src/koreanops_rag/v3/profiles.py
```

New algorithms should be added once as reusable profile implementations, then
referenced by one or more cases in `test_cases.yaml`.

## Commands

Use the grouped CLI:

```powershell
uv run koreanops-v3-cases validate
uv run koreanops-v3-cases list
uv run koreanops-v3-cases list --enabled-only
uv run koreanops-v3-cases manifest parent_child_child_search_section_context
uv run koreanops-v3-cases summarize
uv run koreanops-v3-runner plan parent_child_child_search_section_context
uv run koreanops-v3-runner plan-all
```

The manifest command writes the resolved case metadata under:

```text
C:\vectorsearch-data\ko-dense-technical\eval\cases\{case_id}_run_manifest.json
```

The summarize command writes the matrix:

```text
C:\vectorsearch-data\ko-dense-technical\eval\case_matrix_summary.csv
```

The runner command writes resolved execution plans. It does not run heavy parsing,
indexing, retrieval, or LLM work yet; it verifies that each case can be mapped to
the reusable profile implementations that future runners will call.

## Evaluation Flow

Run cases in stages instead of exploring every combination.

1. Smoke cases validate parsing, tokenizer-aware chunking, namespace isolation,
   and indexability on 100 documents.
2. Pilot cases compare individual techniques on 1,000 documents:
   multi-granularity, parent-child, graph reranking, hybrid reranking,
   adaptive-k, topic/keyword scoping, and late interaction.
3. Full cases expand only the strongest pilot cases and add corrective RAG,
   ANN tuning, and clean/misleading/mixed evidence reliability tests.

## Required Result Fields

Every case summary should include these comparable metrics when applicable:

```text
recall_at_10
mrr
ndcg_at_10
p50_latency_ms
p95_latency_ms
```

Detailed evaluators may add richer fields, but `koreanops-v3-cases summarize`
uses the fields above for the first project-wide matrix.
