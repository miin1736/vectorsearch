# V3 Pilot QASET Review

- Source: `C:\vectorsearch-data\ko-dense-technical\eval\pilot_1000\qaset_protocols\qaset_hard_negative.jsonl`
- Reviewed JSONL: `C:\vectorsearch-data\ko-dense-technical\eval\pilot_1000\qaset_protocol_reviews\qaset_hard_negative.reviewed.jsonl`
- Questions reviewed: 120
- Approved automatically: 0
- Manual review queue: 120
- Rejected: 0
- Lexical overlap mean: 0.0186
- Lexical overlap median: 0.0000
- Avg hard negatives: 10.00

## Status Distribution

- manual_review: 120

## Question Type Distribution

- conclusion: 20
- method: 20
- purpose: 20
- result: 20
- section: 20
- summary: 20

## Difficulty Distribution

- adversarial: 120

## Manual Review Flags

- low_lexical_overlap: 111
- abstract_based: 20

## Auto Reject Reasons

- None

## Recommended Use

- Use rows marked `approved_auto_review` and `manual_review` for pilot analysis.
- Do not call this a final benchmark until `manual_review` rows are inspected.
- Low lexical overlap is a review flag, not an automatic defect.
- Encoding noise should be revised or rejected during manual review.
