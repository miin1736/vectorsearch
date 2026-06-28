from koreanops_rag.office.review_golden import review_row


def _row(question: str, **overrides):
    row = {
        "question_id": "office_q_0001",
        "question": question,
        "reference_answer": "answer",
        "gold_doc_ids": ["doc-1"],
        "gold_pages": [3],
        "evidence_text": "evidence " * 20,
        "question_type": "fact",
        "lexical_overlap": 0.2,
        "review_status": "pending",
    }
    row.update(overrides)
    return row


def test_review_row_approves_clean_candidate():
    reviewed = review_row(_row("What does the document explain?"), set())

    assert reviewed["review_status"] == "approved"
    assert reviewed["auto_reject_reasons"] == []


def test_review_row_rejects_duplicate_question():
    seen = set()
    first = review_row(_row("What does the document explain?"), seen)
    second = review_row(_row("What does the document explain?", question_id="q2"), seen)

    assert first["review_status"] == "approved"
    assert second["review_status"] == "rejected"
    assert "duplicate_question" in second["auto_reject_reasons"]


def test_review_row_flags_soft_quality_without_rejecting():
    reviewed = review_row(
        _row(
            "문서 핵심 내용 요약",
            reference_answer="Y",
            lexical_overlap=0.0,
        ),
        set(),
    )

    assert reviewed["review_status"] == "approved"
    assert "question_mark_missing" in reviewed["review_flags"]
    assert "low_lexical_overlap" in reviewed["review_flags"]
