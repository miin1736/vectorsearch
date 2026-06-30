from koreanops_rag.v3.qaset_review import review_qaset_row


def _row(**overrides):
    row = {
        "question_id": "v3_balanced_0001",
        "question": "For smart factory adoption, what method does the paper use?",
        "reference_answer": "The paper uses case analysis and literature review to study adoption factors.",
        "gold_doc_ids": ["paper_a"],
        "gold_pages": [2],
        "gold_section": "method",
        "evidence_text": "The paper uses case analysis and literature review to study smart factory adoption factors. "
        * 6,
        "question_type": "method",
        "difficulty": "hard",
        "lexical_overlap": 0.32,
        "hard_negative_doc_ids": [f"paper_n_{idx}" for idx in range(10)],
        "review_status": "candidate",
        "review_flags": [],
    }
    row.update(overrides)
    return row


def test_v3_review_qaset_row_approves_clean_candidate():
    reviewed = review_qaset_row(_row(), set())

    assert reviewed["review_status"] == "approved_auto_review"
    assert reviewed["auto_reject_reasons"] == []


def test_v3_review_qaset_row_routes_soft_flags_to_manual_review():
    reviewed = review_qaset_row(
        _row(
            gold_section="abstract",
            lexical_overlap=0.05,
            review_flags=["abstract_based"],
        ),
        set(),
    )

    assert reviewed["review_status"] == "manual_review"
    assert "abstract_based" in reviewed["review_flags"]
    assert "low_lexical_overlap" in reviewed["review_flags"]


def test_v3_review_qaset_row_rejects_missing_gold_doc():
    reviewed = review_qaset_row(_row(gold_doc_ids=[]), set())

    assert reviewed["review_status"] == "rejected"
    assert "missing_gold_doc_ids" in reviewed["auto_reject_reasons"]
