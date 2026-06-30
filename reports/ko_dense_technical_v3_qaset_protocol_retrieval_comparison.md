# V3 QASET Protocol Retrieval Discrimination

This report compares how strongly each QASET protocol separates the three pilot baseline chunking strategies.

| Protocol | Spread R@10 | Avg R@10 | Avg BM25 R@10 | Avg Vector R@10 | BM25-Vector gap | Avg MRR | Avg nDCG@10 |
|---|---:|---:|---:|---:|---:|---:|---:|
| qaset_section_balanced | 0.392 | 0.642 | 0.700 | 0.425 | 0.275 | 0.440 | 0.488 |
| qaset_balanced | 0.361 | 0.658 | 0.717 | 0.445 | 0.272 | 0.453 | 0.502 |
| qaset_late_evidence | 0.300 | 0.611 | 0.633 | 0.506 | 0.128 | 0.444 | 0.484 |
| qaset_hard_negative | 0.275 | 0.706 | 0.653 | 0.619 | 0.033 | 0.512 | 0.559 |
| qaset_low_lexical_overlap | 0.025 | 0.012 | 0.014 | 0.003 | 0.011 | 0.003 | 0.005 |

## Interpretation Rule

- Very low average recall means the QASET may be too difficult or under-specified.
- Very high average recall means the QASET may be too easy.
- Higher spread helps reveal differences between chunking/retrieval choices.
- A canonical QASET should balance spread, answerability, review burden, and hard-negative coverage.
