# Ko Dense Technical V3 Smoke Retrieval Evaluation

## Summary

2026-06-29 기준 V3 AIHub 학술논문 smoke 100문서에서 자동 생성 golden set 50개를 만들고,
4개 청킹 전략별 BM25, Vector, Hybrid 검색을 평가했다.

이 결과는 파이프라인 검증용 smoke 평가다. 자동 질문이 근거 문단에서 주제어를 추출하므로
BM25에 유리한 lexical overlap이 포함된다. 따라서 아래 수치는 최종 검색 품질 결론이 아니라
"인덱싱과 평가 루프가 정상 동작하는지"를 확인하는 기준선으로 해석해야 한다.

## Artifacts

- Golden set: `C:\vectorsearch-data\ko-dense-technical\eval\smoke_100\golden_questions_auto.jsonl`
- Detail metrics: `C:\vectorsearch-data\ko-dense-technical\eval\smoke_100\retrieval_case_details.csv`
- Summary metrics: `C:\vectorsearch-data\ko-dense-technical\eval\smoke_100\retrieval_case_summary.csv`

## Indexed Cases

| Case | OpenSearch / Qdrant namespace | Chunks |
|---|---:|---:|
| Fixed 512 | `ko_dense_technical_v3_fixed_512` | 2,295 |
| Page subchunk | `ko_dense_technical_v3_page_subchunk` | 4,566 |
| Section | `ko_dense_technical_v3_section` | 4,107 |
| Tokenizer-aware fixed 512 | `ko_dense_technical_v3_tokenizer_fixed` | 3,701 |

## Overall Result

| Case | Method | Recall@5 | Recall@10 | MRR | nDCG@10 | P50 latency ms |
|---|---|---:|---:|---:|---:|---:|
| page_subchunk | bm25 | 1.00 | 1.00 | 1.000 | 1.000 | 44.36 |
| tokenizer_fixed | bm25 | 1.00 | 1.00 | 1.000 | 1.000 | 44.67 |
| section | bm25 | 1.00 | 1.00 | 1.000 | 1.000 | 44.37 |
| fixed_512 | bm25 | 1.00 | 1.00 | 1.000 | 1.000 | 47.90 |
| section | hybrid_weighted | 0.94 | 1.00 | 0.880 | 0.909 | 77.34 |
| page_subchunk | hybrid_weighted | 0.98 | 1.00 | 0.830 | 0.871 | 77.34 |
| tokenizer_fixed | hybrid_weighted | 0.98 | 1.00 | 0.817 | 0.862 | 76.09 |
| tokenizer_fixed | hybrid_rrf | 0.98 | 1.00 | 0.809 | 0.856 | 77.89 |
| section | vector | 0.80 | 0.86 | 0.707 | 0.744 | 30.22 |
| page_subchunk | vector | 0.76 | 0.86 | 0.587 | 0.652 | 29.59 |
| fixed_512 | vector | 0.72 | 0.82 | 0.582 | 0.638 | 30.65 |
| tokenizer_fixed | vector | 0.74 | 0.76 | 0.577 | 0.623 | 29.35 |

## Interpretation

현재 smoke set에서는 BM25가 모든 청킹 전략에서 Recall@10, MRR, nDCG@10 모두 1.0에 도달했다.
이는 BM25가 실제로 항상 우월하다는 뜻이 아니라, 자동 질문이 evidence의 표면 어휘를 상당 부분
공유하기 때문이다.

Vector 검색은 latency가 가장 낮지만 ranking 품질은 낮다. 특히 tokenizer-aware fixed가 Vector에서
가장 낮은 Recall@10을 보였고, section과 page_subchunk가 상대적으로 나았다. 긴 학술문서에서는
의미 단위가 보존되는 section/page 기반 청킹이 dense retriever에 더 유리할 가능성이 있다.

Hybrid는 Recall@10 기준으로 BM25에 근접하지만 MRR/nDCG는 BM25보다 낮았다. 이는 RRF가 vector 후보를
섞으면서 gold parent의 rank를 BM25 단독보다 뒤로 밀었기 때문이다. 현재처럼 lexical query가 강한
조건에서는 Hybrid가 BM25를 이기기 어렵다.

## Limitations

- Golden set은 `approved_auto_smoke`이며 사람이 검수한 최종 golden set이 아니다.
- 질문은 근거 문단에서 추출한 주제어를 포함하므로 BM25 친화적이다.
- 일부 PDF 텍스트/제목에는 인코딩 품질 문제가 보여 질문과 문서 메타데이터 정제가 필요하다.
- 현재 평가는 parent document hit 기준이다. chunk-level evidence containment 평가는 다음 단계에서 추가해야 한다.
- smoke 100문서/50질문 기준이므로 전체 18,000 manifest 또는 pilot 1,000문서 결과로 일반화하면 안 된다.

## Next Steps

1. Low lexical overlap 질문 세트를 별도로 생성한다.
2. 사람이 50개 smoke 질문을 검수해 `approved_manual_smoke` 버전을 만든다.
3. Chunk-level evidence containment 평가를 추가한다.
4. Pilot 1,000문서로 확장하고 hard negative가 많은 질문 유형을 늘린다.
5. Section, page_subchunk, tokenizer-aware fixed를 중심으로 Vector/Hybrid 개선 실험을 이어간다.
