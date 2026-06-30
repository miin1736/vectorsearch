# V3 Pilot QASET Review

- Source: `C:\vectorsearch-data\ko-dense-technical\eval\pilot_1000\golden_questions_balanced.jsonl`
- Reviewed JSONL: `C:\vectorsearch-data\ko-dense-technical\eval\pilot_1000\golden_questions_balanced_reviewed.jsonl`
- Questions reviewed: 120
- Approved automatically: 63
- Manual review queue: 57
- Rejected: 0
- Lexical overlap mean: 0.1962
- Lexical overlap median: 0.1667
- Avg hard negatives: 10.00

## Status Distribution

- approved_auto_review: 63
- manual_review: 57

## Question Type Distribution

- conclusion: 12
- method: 24
- purpose: 24
- result: 24
- section: 12
- summary: 24

## Difficulty Distribution

- adversarial: 70
- hard: 50

## Manual Review Flags

- low_lexical_overlap: 33
- abstract_based: 24

## Auto Reject Reasons

- None

## Recommended Use

- Use rows marked `approved_auto_review` and `manual_review` for pilot analysis.
- Do not call this a final benchmark until `manual_review` rows are inspected.
- Low lexical overlap is a review flag, not an automatic defect.
- Encoding noise should be revised or rejected during manual review.
