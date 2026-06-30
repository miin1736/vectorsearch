# ko_unstructured_v2 Data Quality Report

This report is read-only: it checks JSONL artifacts and live index counts without creating, deleting, or mutating Qdrant/OpenSearch data.

## Summary

- PASS: 11
- WARN: 1
- FAIL: 0

## Checks

| Check | Status | Observed | Expected | Details |
| --- | --- | ---: | ---: | --- |
| manifest count equals normalized documents count | PASS | 9491 | 9491 |  |
| empty content document count | WARN | 141 | 0 |  |
| page duplicate chunk ids | PASS | 0 | 0 | rows=42676 |
| page chunk parent_doc_id exists | PASS | 0 | 0 | rows=42676 |
| page page_start <= page_end | PASS | 0 | 0 | rows=42676 |
| structure duplicate chunk ids | PASS | 0 | 0 | rows=18789 |
| structure chunk parent_doc_id exists | PASS | 0 | 0 | rows=18789 |
| structure page_start <= page_end | PASS | 0 | 0 | rows=18789 |
| Qdrant page points_count equals chunk input count | PASS | 42676 | 42676 |  |
| OpenSearch page _count equals chunk input count | PASS | 42676 | 42676 |  |
| Qdrant structure points_count equals chunk input count | PASS | 18789 | 18789 |  |
| OpenSearch structure _count equals chunk input count | PASS | 18789 | 18789 |  |
