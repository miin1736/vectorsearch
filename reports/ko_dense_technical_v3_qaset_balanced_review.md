# V3 Pilot QASET Review

- Source: `C:\vectorsearch-data\ko-dense-technical\eval\pilot_1000\qaset_protocols\qaset_balanced.jsonl`
- Reviewed JSONL: `C:\vectorsearch-data\ko-dense-technical\eval\pilot_1000\qaset_protocol_reviews\qaset_balanced.reviewed.jsonl`
- Questions reviewed: 120
- Approved automatically: 65
- Manual review queue: 54
- Rejected: 1
- Lexical overlap mean: 0.1843
- Lexical overlap median: 0.1603
- Avg hard negatives: 10.00

## Status Distribution

- approved_auto_review: 65
- manual_review: 54
- rejected: 1

## Question Type Distribution

- conclusion: 20
- method: 20
- purpose: 20
- result: 20
- section: 20
- summary: 20

## Difficulty Distribution

- adversarial: 73
- hard: 47

## Manual Review Flags

- low_lexical_overlap: 34
- abstract_based: 20

## Auto Reject Reasons

- duplicate_question: 1

## Recommended Use

- Use rows marked `approved_auto_review` and `manual_review` for pilot analysis.
- Do not call this a final benchmark until `manual_review` rows are inspected.
- Low lexical overlap is a review flag, not an automatic defect.
- Encoding noise should be revised or rejected during manual review.
