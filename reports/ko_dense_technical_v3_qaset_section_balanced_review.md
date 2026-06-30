# V3 Pilot QASET Review

- Source: `C:\vectorsearch-data\ko-dense-technical\eval\pilot_1000\qaset_protocols\qaset_section_balanced.jsonl`
- Reviewed JSONL: `C:\vectorsearch-data\ko-dense-technical\eval\pilot_1000\qaset_protocol_reviews\qaset_section_balanced.reviewed.jsonl`
- Questions reviewed: 120
- Approved automatically: 70
- Manual review queue: 50
- Rejected: 0
- Lexical overlap mean: 0.1832
- Lexical overlap median: 0.1667
- Avg hard negatives: 10.00

## Status Distribution

- approved_auto_review: 70
- manual_review: 50

## Question Type Distribution

- conclusion: 17
- method: 17
- purpose: 17
- result: 34
- section: 18
- summary: 17

## Difficulty Distribution

- adversarial: 77
- hard: 43

## Manual Review Flags

- low_lexical_overlap: 33
- abstract_based: 17

## Auto Reject Reasons

- None

## Recommended Use

- Use rows marked `approved_auto_review` and `manual_review` for pilot analysis.
- Do not call this a final benchmark until `manual_review` rows are inspected.
- Low lexical overlap is a review flag, not an automatic defect.
- Encoding noise should be revised or rejected during manual review.
