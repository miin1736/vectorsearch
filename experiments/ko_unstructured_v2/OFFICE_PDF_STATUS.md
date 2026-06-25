# Office PDF Hybrid RAG Status

Last updated: 2026-06-25

## Objective

Improve Korean office PDF retrieval while keeping label JSON evaluation-only. Compare Fixed,
Page, Structure, Contextual, and Oracle chunk corpora.

## Dataset

- [x] PDF inventory verified: 9,491
- [x] Label document inventory verified: 9,491
- [x] PDF/label ID mismatch: 0
- [x] Full manifest generated
- [x] Stratified Validation pilot manifest generated: 100 documents

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
- Character precision: 0.7782
- Character recall: 0.8596
- Normalized edit similarity: 0.8090
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

## Remaining

- [ ] Manually review and approve pilot Golden questions
- [x] Start Docker Desktop Linux engine
- [x] Index five pilot corpora in isolated collections/indexes
- [x] Run BM25, Vector, RRF, and weighted Hybrid pilot evaluation
- [ ] Run the 1,000-document pilot
- [ ] Generate and manually review the final 300-question Golden Set
- [ ] Parse and index all 9,491 documents
- [ ] Run final retrieval comparison and select the winner
- [ ] Run 200-question RAG evaluation
- [ ] Complete final reports and failure analysis

## Artifact Paths

- Full manifest: `C:\vectorsearch-data\ko-unstructured\processed\office_manifest.jsonl`
- Pilot processed data: `C:\vectorsearch-data\ko-unstructured\processed\pilot_100`
- Pilot evaluation: `C:\vectorsearch-data\ko-unstructured\eval\pilot_100`
- Pilot reports: `C:\vectorsearch-data\ko-unstructured\reports`
