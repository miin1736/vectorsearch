from koreanops_rag.office.evaluate_rag import cites_context, gold_in_context, token_f1
from koreanops_rag.rag.answer_generator import build_prompt, format_sources
from koreanops_rag.schemas import SearchResult


def test_token_f1_rewards_supported_overlap():
    assert token_f1("기준금리는 3.5 퍼센트입니다", "기준금리 3.5 퍼센트") > 0.7


def test_gold_in_context_requires_parent_and_page_overlap():
    contexts = [
        SearchResult(
            doc_id="doc-1__structure_0001",
            score=1.0,
            rank=1,
            metadata={"parent_doc_id": "doc-1", "page_start": 3, "page_end": 4},
        )
    ]

    assert gold_in_context(contexts, {"gold_doc_ids": ["doc-1"], "gold_pages": [4]}) == 1.0
    assert gold_in_context(contexts, {"gold_doc_ids": ["doc-1"], "gold_pages": [8]}) == 0.0


def test_prompt_and_citation_use_parent_doc_id_and_pages():
    contexts = [
        SearchResult(
            doc_id="doc-1__structure_0001",
            score=1.0,
            rank=1,
            metadata={"parent_doc_id": "doc-1", "page_start": 3, "page_end": 4},
        )
    ]

    prompt = build_prompt("질문", contexts)

    assert "parent_doc_id=doc-1" in prompt
    assert "pages=3-4" in prompt
    assert format_sources(contexts) == "근거: parent_doc_id=doc-1, pages=3-4"
    assert cites_context("(근거: parent_doc_id=doc-1, pages=3-4)", contexts) == 1.0
