# Full RAG Evaluation

Run date: 2026-06-27

## Scope

- Corpus: Structure chunks over the full 9,491-document office PDF corpus
- Retriever: Structure Vector
- Generator: local Ollama `llama3.1:8b-instruct-q4_K_M`
- Golden Set: reviewed full Golden Set, first 200 approved/revised questions
- Retrieval depth for generation: top_k=5
- Output rows: `C:\vectorsearch-data\ko-unstructured\eval\full\rag_structure_vector_200.csv`
- Summary: `C:\vectorsearch-data\ko-unstructured\eval\full\rag_structure_vector_200_summary.csv`

The answer generator now appends source citations deterministically from retrieved contexts instead
of relying on the LLM to follow citation formatting instructions.

## Summary metrics

| Metric | Value |
| --- | ---: |
| Questions | 200 |
| Gold doc/page in retrieved context | 0.525 |
| Cites retrieved context | 1.000 |
| Unsupported / abstained answer rate | 0.070 |
| Korean token/bigram F1 proxy | 0.0291 |
| P50 latency | 10.32 s |
| P95 latency | 17.95 s |
| Generation errors | 0 |

Token-F1 is intentionally treated as a weak proxy here. The generated reference answers are often
short, while the RAG answers are longer and source-cited, so lexical overlap underestimates answer
usefulness. The stronger operational signals are whether the gold doc/page appears in context,
whether sources are cited, latency, and abstention behavior.

## Retrieval-grounding breakdown

| Group | Questions | Token-F1 proxy | Unsupported rate |
| --- | ---: | ---: | ---: |
| Gold doc/page retrieved | 105 | 0.0328 | 0.0476 |
| Gold doc/page not retrieved | 95 | 0.0250 | 0.0947 |

The RAG result confirms that final answer quality is mostly gated by retrieval coverage. When the
gold doc/page is retrieved, unsupported answers are roughly half as frequent. The next meaningful
quality improvement is therefore to improve recall at the generation depth, not to tune the answer
prompt first.

## Engineering conclusions

1. Structure Vector remains the best production-facing baseline for this dataset.
2. Source citations should be appended by the application layer, not delegated to the LLM.
3. Top-5 retrieval gives usable latency on CPU/local Ollama, but gold-context coverage is only 52.5%.
4. The next experiment should compare `top_k=10` and optional reranking before investing more in
   answer-generation prompt tuning.

## Portfolio interpretation

This RAG stage is valuable because it moves the project from retrieval metrics into an operational
question: "Does the system retrieve the right evidence and produce a source-cited answer?" The
answer is mixed but useful:

- Citation plumbing is now robust.
- The current bottleneck is evidence retrieval at generation depth.
- The experiment gives a concrete next optimization target: improve context recall while preserving
  latency.
