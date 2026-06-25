from koreanops_rag.office.evaluate_chunking import evaluate_golden_evidence
from koreanops_rag.office.evaluate_parsing import _character_scores


def test_character_scores_detect_missing_text():
    precision, recall, similarity = _character_scores("한국은행 기준금리", "한국은행 기준금리 결정")

    assert precision == 1.0
    assert 0 < recall < 1
    assert 0 < similarity < 1


def test_chunk_evaluation_matches_parent_page_and_evidence():
    chunks = [
        {
            "doc_id": "doc__fixed_0000",
            "content": "기준금리는 연 3.5퍼센트로 유지되었다.",
            "metadata": {"parent_doc_id": "doc", "page_start": 2, "page_end": 2},
        }
    ]
    questions = [
        {
            "gold_doc_ids": ["doc"],
            "gold_pages": [2],
            "evidence_text": "기준금리는 연 3.5퍼센트로 유지되었다.",
        }
    ]

    metrics = evaluate_golden_evidence(chunks, questions)

    assert metrics["gold_containment_rate"] == 1.0
    assert metrics["gold_page_coverage"] == 1.0
