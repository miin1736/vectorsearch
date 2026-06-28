from __future__ import annotations

from koreanops_rag.rag.llm_provider import LlmProvider
from koreanops_rag.schemas import SearchResult


def format_sources(contexts: list[SearchResult]) -> str:
    sources = []
    seen = set()
    for result in contexts:
        parent_doc_id = str(result.metadata.get("parent_doc_id") or result.doc_id)
        page_start = result.metadata.get("page_start", "")
        page_end = result.metadata.get("page_end", page_start)
        page_label = f"{page_start}" if page_start == page_end else f"{page_start}-{page_end}"
        key = (parent_doc_id, page_label)
        if key in seen:
            continue
        seen.add(key)
        sources.append(f"parent_doc_id={parent_doc_id}, pages={page_label}")
    return "근거: " + "; ".join(sources)


def build_prompt(question: str, contexts: list[SearchResult]) -> str:
    context_blocks = []
    for result in contexts:
        parent_doc_id = result.metadata.get("parent_doc_id") or result.doc_id
        page_start = result.metadata.get("page_start", "")
        page_end = result.metadata.get("page_end", page_start)
        page_label = f"{page_start}" if page_start == page_end else f"{page_start}-{page_end}"
        context_blocks.append(
            "\n".join(
                [
                    f"[{result.rank}] chunk_id={result.doc_id}",
                    f"parent_doc_id={parent_doc_id}",
                    f"pages={page_label}",
                    f"title={result.title}",
                    f"content={result.content}",
                ]
            )
        )
    return f"""당신은 한국어 문서 검색 기반 질의응답 도우미입니다.

규칙:
- 제공된 근거만 사용해 한국어로 답하세요.
- Answer only from the provided context.
- 근거가 부족하면 추측하지 말고 "제공된 문서만으로는 확인할 수 없습니다."라고 답하세요.
- 답변 끝에 반드시 사용한 parent_doc_id와 페이지를 근거로 표시하세요.
- 근거 표기 형식: (근거: parent_doc_id=..., pages=...)
- 불필요하게 길게 쓰지 말고 3-6문장 안에서 답하세요.

질문:
{question}

근거:
{chr(10).join(context_blocks)}
"""


class AnswerGenerator:
    def __init__(self, provider: LlmProvider):
        self.provider = provider

    def answer(self, question: str, contexts: list[SearchResult]) -> str:
        answer = self.provider.generate(build_prompt(question, contexts)).strip()
        if not contexts:
            return answer
        return f"{answer}\n\n({format_sources(contexts)})"
