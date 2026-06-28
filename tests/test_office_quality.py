from koreanops_rag.office.evaluate_chunking import evaluate_golden_evidence
from koreanops_rag.office.evaluate_parsing import _character_scores
from koreanops_rag.office.build_oracle import _page_texts


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


def test_oracle_reference_list_uses_visual_text_but_not_for_parser_scoring():
    content, parsing_reference, text_type = _page_texts(
        [
            {
                "class_name": "D01",
                "plain_text": "",
                "visual_description": "",
                "document_description": "[&]page_001_V04.json\n[&]page_002_V04.json",
            },
            {
                "class_name": "V04",
                "plain_text": "",
                "visual_description": "로마의 확장과 문화적 영향을 설명하는 이미지다.",
                "document_description": "",
            },
        ]
    )

    assert content == "로마의 확장과 문화적 영향을 설명하는 이미지다."
    assert parsing_reference == ""
    assert text_type == "visual_description"
