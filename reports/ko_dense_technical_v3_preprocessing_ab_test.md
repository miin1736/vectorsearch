# V3 Text Preprocessing A/B Test

## Summary

FULL 확장 전 `pilot_1000`에서 raw PDF 추출 텍스트와 3개 전처리 profile을 같은 QASET로 비교했다.

결론은 **현재 canonical QASET와 shortlist 기준에서는 raw를 유지하는 것이 타당하다**.

- `fixed_512 + weighted + ck30 + bm25_weight=2`: raw가 Recall@10, nDCG@10 기준 최고.
- `passage + rrf + ck50`: cleaned profile이 Recall@10을 0.0167 올렸지만 MRR/nDCG@10은 raw보다 낮다.
- 강한 전처리는 noise를 크게 줄였지만 gold evidence containment를 손상했다.
- 따라서 FULL 후보는 기존 계획대로 유지하되, 이번 결과 기준으로는 `winner cleaning profile`을 적용하지 않고 raw baseline을 FULL 후보로 가져간다.

## Preserved FULL Shortlist

| Candidate | Status |
|---|---|
| `fixed_512 + weighted + ck30 + bm25_weight=2` | Keep, raw text preferred |
| `passage + rrf + ck50` | Keep, raw text preferred |

## Artifacts

| Artifact | Path |
|---|---|
| Raw noise profile | `C:\vectorsearch-data\ko-dense-technical\eval\pilot_1000\preprocessing\noise_profile_raw.csv` |
| Cleaning quality summary | `C:\vectorsearch-data\ko-dense-technical\eval\pilot_1000\preprocessing\cleaning_quality_summary.csv` |
| Evidence containment summary | `C:\vectorsearch-data\ko-dense-technical\eval\pilot_1000\preprocessing\evidence_containment_summary.csv` |
| Overall A/B summary | `C:\vectorsearch-data\ko-dense-technical\eval\pilot_1000\preprocessing\preprocessing_ab_overall_summary.csv` |
| Fixed retrieval summary | `C:\vectorsearch-data\ko-dense-technical\eval\pilot_1000\preprocessing\fixed_512_ab_summary.csv` |
| Passage retrieval summary | `C:\vectorsearch-data\ko-dense-technical\eval\pilot_1000\preprocessing\passage_ab_summary.csv` |
| Preprocessed data | `C:\vectorsearch-data\ko-dense-technical\processed\pilot_1000\preprocessed\{profile}` |

## Cleaning Profiles

| Profile | Intent | Main actions |
|---|---|---|
| `clean_light` | Low-risk noise removal | URL, DOI, email, provider markers, HTML/bracket markers, page-number boilerplate |
| `clean_structural` | Structural cleanup | `clean_light` plus repeated header/footer lines, short table/figure markers, references section removal |
| `clean_embedding_optimized` | Embedding text optimization | `clean_structural` plus short noise line removal, citation-marker removal, line joining, sentence-ending repair |

Implementation detail:

- `content` keeps human-readable cleaned text.
- `embedding_text` is used by chunking/indexing when present.
- Raw baseline files were not modified.

## Index And Collection Counts

| Namespace | OpenSearch | Qdrant |
|---|---:|---:|
| `ko_dense_technical_v3_pilot_1000_clean_light_fixed_512` | 14,468 | 14,468 |
| `ko_dense_technical_v3_pilot_1000_clean_structural_fixed_512` | 12,234 | 12,234 |
| `ko_dense_technical_v3_pilot_1000_clean_embedding_fixed_512` | 11,535 | 11,535 |
| `ko_dense_technical_v3_pilot_1000_clean_light_passage` | 34,358 | 34,358 |
| `ko_dense_technical_v3_pilot_1000_clean_structural_passage` | 31,152 | 31,152 |
| `ko_dense_technical_v3_pilot_1000_clean_embedding_passage` | 28,190 | 28,190 |

## Retrieval Result

### Fixed Candidate

Target condition: `fixed_512 + hybrid_weighted + candidate_k=30 + bm25_weight=2`.

| Profile | Recall@10 | Delta | MRR | Delta | nDCG@10 | Delta |
|---|---:|---:|---:|---:|---:|---:|
| raw | 0.7750 | 0.0000 | 0.5108 | 0.0000 | 0.5737 | 0.0000 |
| `clean_light` | 0.7333 | -0.0417 | 0.5116 | +0.0008 | 0.5645 | -0.0092 |
| `clean_structural` | 0.6833 | -0.0917 | 0.4267 | -0.0840 | 0.4888 | -0.0849 |
| `clean_embedding_optimized` | 0.6667 | -0.1083 | 0.4264 | -0.0844 | 0.4844 | -0.0893 |

Interpretation:

- `clean_light` preserves MRR but loses Recall@10 and nDCG@10.
- Stronger profiles materially reduce ranking quality.
- For this candidate, raw is the clear FULL input.

### Passage Candidate

Target condition: `passage + hybrid_rrf + candidate_k=50`.

| Profile | Recall@10 | Delta | MRR | Delta | nDCG@10 | Delta |
|---|---:|---:|---:|---:|---:|---:|
| raw | 0.7500 | 0.0000 | 0.5660 | 0.0000 | 0.6102 | 0.0000 |
| `clean_light` | 0.7667 | +0.0167 | 0.5213 | -0.0447 | 0.5788 | -0.0314 |
| `clean_structural` | 0.7333 | -0.0167 | 0.4749 | -0.0911 | 0.5362 | -0.0740 |
| `clean_embedding_optimized` | 0.7667 | +0.0167 | 0.5277 | -0.0383 | 0.5839 | -0.0263 |

Interpretation:

- `clean_light` and `clean_embedding_optimized` recover slightly more documents by top-10.
- They rank the gold document worse than raw, so MRR and nDCG@10 drop.
- Since the project winner rule prioritizes Recall@10 first, this is a borderline case. However, the delta is small and ranking quality loss is consistent.
- For FULL, raw is safer unless we explicitly decide that Recall-only is more important than early-rank quality.

## Data Quality Result

### Noise Reduction

Document-level cleaning summary:

| Profile | Char reduction | Noise before | Noise after | Sentence break before | Sentence break after |
|---|---:|---:|---:|---:|---:|
| `clean_light` | 2.38% | 0.02753 | 0.005832 | 0.330548 | 0.346820 |
| `clean_structural` | 17.67% | 0.02753 | 0.000031 | 0.330548 | 0.328867 |
| `clean_embedding_optimized` | 21.80% | 0.02753 | 0.000023 | 0.330548 | 0.223000 |

Noise removal worked. The problem is not that cleaning failed. The problem is that aggressive cleaning changed or removed retrieval evidence and lexical anchors.

### Evidence Containment

This measures whether the QASET gold evidence remains available inside the chunk corpus for the gold document.

| Case | Chunk count | Full evidence containment | Partial overlap >= 0.5 | Avg evidence token overlap |
|---|---:|---:|---:|---:|
| `raw_fixed_512` | 14,909 | 0.7083 | 1.0000 | 0.9573 |
| `clean_light_fixed_512` | 14,468 | 0.5417 | 1.0000 | 0.9541 |
| `clean_structural_fixed_512` | 12,234 | 0.4500 | 0.8917 | 0.8545 |
| `clean_embedding_fixed_512` | 11,535 | 0.0000 | 0.8500 | 0.7654 |
| `raw_passage` | 47,516 | 0.4000 | 1.0000 | 0.8633 |
| `clean_light_passage` | 34,358 | 0.4917 | 1.0000 | 0.9495 |
| `clean_structural_passage` | 31,152 | 0.4417 | 1.0000 | 0.9372 |
| `clean_embedding_passage` | 28,190 | 0.0000 | 0.9583 | 0.8334 |

Interpretation:

- `clean_embedding_optimized` is too destructive for evidence-faithful retrieval evaluation because full-string evidence containment collapses to 0.
- `clean_light` is the only profile that keeps partial evidence coverage intact while reducing noise.
- For passage, `clean_light` improves evidence overlap and Recall@10, but not ranking quality.

## BM25 Keyword Change Analysis

BM25 was directly affected by preprocessing:

- Fixed raw BM25 Recall@10: 0.7333.
- Fixed `clean_light` BM25 Recall@10: 0.7083.
- Fixed `clean_structural` BM25 Recall@10: 0.6417.
- Fixed `clean_embedding_optimized` BM25 Recall@10: 0.6250.

This shows that preprocessing removed or altered lexical anchors BM25 relied on. The hybrid degradation is therefore not just a vector embedding issue. It is partly a keyword-index issue.

Vector-only behavior:

- Fixed vector Recall@10 changed from raw 0.3833 to `clean_light` 0.3750, `clean_structural` 0.4167, `clean_embedding_optimized` 0.3917.
- Passage vector Recall@10 changed from raw 0.4750 to `clean_light` 0.4917, `clean_structural` 0.5000, `clean_embedding_optimized` 0.5500.

This suggests cleaned text can help dense retrieval, especially passage chunks, but the improvement is not enough to offset BM25/ranking degradation in the target hybrid settings.

## Decision

Do not apply a cleaning winner to FULL yet.

FULL should proceed with:

1. `raw fixed_512 + weighted + ck30 + bm25_weight=2`
2. `raw passage + rrf + ck50`

Keep `clean_light passage` as a secondary diagnostic option only if FULL Recall@10 is insufficient and ranking-quality loss is acceptable.

## Repro Commands

```powershell
. .\scripts\project-env.ps1

uv run koreanops-v3-preprocess profile-noise
uv run koreanops-v3-preprocess build

uv run koreanops-v3-chunks build --strategy fixed --token-budget 512 --overlap 64 ...
uv run koreanops-v3-chunks build --strategy passage --token-budget 512 --overlap 64 ...

uv run koreanops-index-opensearch <chunks.jsonl> --config-path <clean_config.yaml>
uv run koreanops-index-qdrant <chunks.jsonl> --config-path <clean_config.yaml> --resume

uv run koreanops-v3-retrieval eval-cases `
  --questions-jsonl C:\vectorsearch-data\ko-dense-technical\eval\pilot_1000\qaset_canonical_reviewed.jsonl `
  --summary-csv C:\vectorsearch-data\ko-dense-technical\eval\pilot_1000\preprocessing\fixed_512_ab_summary.csv `
  --details-csv C:\vectorsearch-data\ko-dense-technical\eval\pilot_1000\preprocessing\fixed_512_ab_details.csv `
  --config-path experiments/ko_dense_technical_v3/configs/pilot_1000/clean_light_fixed_512.yaml `
  --config-path experiments/ko_dense_technical_v3/configs/pilot_1000/clean_structural_fixed_512.yaml `
  --config-path experiments/ko_dense_technical_v3/configs/pilot_1000/clean_embedding_optimized_fixed_512.yaml `
  --top-k 10 `
  --candidate-k 30 `
  --bm25-weight 2.0 `
  --vector-weight 1.0
```

## Caveat

Current retrieval detail CSV stores per-question rank and metrics, but not the actual retrieved chunk IDs/text. Therefore evidence containment here is measured against the chunk corpus for the gold document, not against the exact retrieved top-k context. For stricter future analysis, add retrieved IDs and snippets to `retrieval_case_details.csv`.
