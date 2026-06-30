# V3 Canonical QASET Finalization

- Source: `C:\vectorsearch-data\ko-dense-technical\eval\pilot_1000\qaset_canonical_candidate.jsonl`
- Output: `C:\vectorsearch-data\ko-dense-technical\eval\pilot_1000\qaset_canonical_reviewed.jsonl`
- Questions: 120
- Auto-approved: 70
- Provisional human-review rows: 50

## Review Status

- approved_auto_review: 70
- approved_provisional_review: 50

## Question Types

- conclusion: 17
- method: 17
- purpose: 17
- result: 34
- section: 18
- summary: 17

## Difficulty

- adversarial: 77
- hard: 43

## Preserved Review Flags

- low_lexical_overlap: 33
- abstract_based: 17

## Use

- Use this file for pilot technique comparison.
- Rows with `requires_human_review=true` are valid for pilot comparison but should be inspected before a final public benchmark.
- Do not regenerate the QASET while comparing chunking/retrieval/reranking techniques.
