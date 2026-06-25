from pathlib import Path

from koreanops_rag.evaluation.build_eval_subset import build_subset
from koreanops_rag.io import write_jsonl


def test_build_subset_keeps_gold_parents(tmp_path: Path):
    docs = tmp_path / "docs.jsonl"
    questions = tmp_path / "questions.jsonl"
    write_jsonl(
        docs,
        [
            {"doc_id": "gold__ctx_00", "metadata": {"parent_doc_id": "gold"}},
            {"doc_id": "neg_1", "metadata": {"parent_doc_id": "neg_1"}},
            {"doc_id": "neg_2", "metadata": {"parent_doc_id": "neg_2"}},
        ],
    )
    write_jsonl(questions, [{"question": "q", "gold_doc_ids": ["gold"]}])

    subset = list(build_subset(docs, questions, max_rows=2))

    assert [row["doc_id"] for row in subset] == ["gold__ctx_00", "neg_1"]
