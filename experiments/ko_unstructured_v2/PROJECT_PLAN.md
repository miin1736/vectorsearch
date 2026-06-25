# Korean Office PDF Hybrid RAG v2

This experiment is isolated from KoreanOps v1 by data root, index names, reports, and metrics.

## Data Root

`C:\vectorsearch-data\ko-unstructured`

## Active Dataset

- AI Hub `18.오피스 문서 생성 데이터`
- 9,491 PDF documents with 9,491 matching labeled documents
- Labels are evaluation-only Oracle data and never build the production corpus

## Index Namespace

All v2 Qdrant collections and OpenSearch indexes start with `ko_unstructured_pdf_`.

## Corpus Variants

- `pdf_fixed`: 512-token chunks with 64-token overlap
- `pdf_page`: one chunk per PDF page
- `pdf_structure`: heading and paragraph aware 350-700-token chunks
- `pdf_contextual`: structure chunks with document context
- `pdf_oracle`: label-derived evaluation ceiling

## Required Configs

Do not use `configs/default.yaml`. Use one of:

- `experiments/ko_unstructured_v2/configs/pdf_fixed.yaml`
- `experiments/ko_unstructured_v2/configs/pdf_page.yaml`
- `experiments/ko_unstructured_v2/configs/pdf_structure.yaml`
- `experiments/ko_unstructured_v2/configs/pdf_contextual.yaml`
- `experiments/ko_unstructured_v2/configs/pdf_oracle.yaml`
