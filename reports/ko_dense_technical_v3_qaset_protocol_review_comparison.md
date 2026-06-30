# V3 QASET Protocol Comparison

This report compares QASET generation protocols before selecting the canonical pilot/full evaluation set.

| Protocol | Questions | Avg lexical overlap | Avg hard negatives | Hard/adversarial | Late evidence | Abstract | Manual review | Rejected |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| qaset_balanced | 120 | 0.184 | 10.00 | 1.000 | 0.383 | 0.167 | 0.450 | 0.008 |
| qaset_hard_negative | 120 | 0.019 | 10.00 | 1.000 | 0.333 | 0.167 | 1.000 | 0.000 |
| qaset_late_evidence | 120 | 0.196 | 10.00 | 1.000 | 0.825 | 0.167 | 0.417 | 0.000 |
| qaset_low_lexical_overlap | 120 | 0.005 | 10.00 | 1.000 | 0.333 | 0.167 | 1.000 | 0.000 |
| qaset_section_balanced | 120 | 0.183 | 10.00 | 1.000 | 0.417 | 0.142 | 0.417 | 0.000 |

## Selection Rule

- Do not select the protocol with the highest retrieval score.
- Select the protocol that keeps gold evidence clear while exposing ranking differences.
- Prefer sufficient hard negatives, lower lexical overlap, non-abstract evidence, and late-document evidence.
- After deterministic review, freeze one protocol as `qaset_canonical_reviewed` for technique comparison.
