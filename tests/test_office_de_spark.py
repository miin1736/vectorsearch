import json
import shutil

import pytest

from koreanops_rag.office_de.spark import convert_jsonl_to_parquet


def test_jsonl_to_parquet_with_local_spark(tmp_path):
    pytest.importorskip("pyspark")
    if shutil.which("java") is None:
        pytest.skip("PySpark parquet smoke test requires Java")

    source = tmp_path / "input.jsonl"
    source.write_text(
        "\n".join(
            json.dumps(row)
            for row in [
                {"doc_id": "doc-1", "content": "a"},
                {"doc_id": "doc-2", "content": "b"},
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    counts = convert_jsonl_to_parquet(
        {"sample": source},
        tmp_path / "parquet",
        spark_master="local[1]",
    )

    assert counts == {"sample": 2}
    assert (tmp_path / "parquet" / "sample").exists()

