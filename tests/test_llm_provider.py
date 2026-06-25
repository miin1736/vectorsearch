from koreanops_rag.rag.answer_generator import AnswerGenerator, build_prompt
from koreanops_rag.rag.llm_provider import MockProvider
from koreanops_rag.schemas import SearchResult


def test_mock_provider_answer_generator():
    generator = AnswerGenerator(MockProvider("ok"))

    assert generator.answer("question", []) == "ok"


def test_prompt_contains_context_and_grounding_instruction():
    prompt = build_prompt(
        "payment timeout",
        [SearchResult(doc_id="ticket_1", score=1.0, rank=1, content="DB pool exhausted")],
    )

    assert "Answer only from the provided context" in prompt
    assert "DB pool exhausted" in prompt
