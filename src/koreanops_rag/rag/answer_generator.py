from __future__ import annotations

from koreanops_rag.rag.llm_provider import LlmProvider
from koreanops_rag.schemas import SearchResult


def build_prompt(question: str, contexts: list[SearchResult]) -> str:
    context_blocks = []
    for result in contexts:
        context_blocks.append(
            "\n".join(
                [
                    f"[{result.rank}] doc_id={result.doc_id}",
                    f"title={result.title}",
                    f"metadata={result.metadata}",
                    f"content={result.content}",
                ]
            )
        )
    return f"""당신은 한국어 문서 검색 기반 질의응답 도우미입니다.

제공된 근거만 사용하여 한국어로 답변하세요.
Answer only from the provided context.
근거가 부족하면 추측하지 말고 "제공된 문서만으로는 확인할 수 없습니다."라고 답하세요.
답변 끝에는 사용한 doc_id와 페이지 번호를 근거로 표시하세요.

질문:
{question}

근거:
{chr(10).join(context_blocks)}
"""


class AnswerGenerator:
    def __init__(self, provider: LlmProvider):
        self.provider = provider

    def answer(self, question: str, contexts: list[SearchResult]) -> str:
        return self.provider.generate(build_prompt(question, contexts))
