import json
import shutil

import pytest

from koreanops_rag.office_de.mart import build_mart
from koreanops_rag.office_de.paths import OfficeDePaths


def _write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n",
        encoding="utf-8",
    )


def test_build_mart_with_local_spark(tmp_path):
    pytest.importorskip("pyspark")
    if shutil.which("java") is None:
        pytest.skip("PySpark mart smoke test requires Java")

    paths = OfficeDePaths(tmp_path)
    _write_jsonl(
        paths.manifest_jsonl,
        [
            {
                "doc_id": "doc-1",
                "split": "training",
                "document_type": "report",
                "source_archive": "a.zip",
                "source_member": "a.pdf",
                "file_size": 123,
            }
        ],
    )
    _write_jsonl(
        paths.documents_jsonl,
        [
            {
                "doc_id": "doc-1",
                "title": "title",
                "content": "content",
                "metadata": {
                    "page_count": 1,
                    "text_layer_pages": 1,
                    "parse_error": "",
                },
            }
        ],
    )
    chunk = {
        "doc_id": "doc-1__page_0000",
        "content": "content",
        "metadata": {
            "chunking_strategy": "page",
            "parent_doc_id": "doc-1",
            "page_start": 1,
            "page_end": 1,
        },
    }
    _write_jsonl(paths.chunks_page_jsonl, [chunk])
    _write_jsonl(paths.chunks_structure_jsonl, [{**chunk, "doc_id": "doc-1__structure_0000"}])

    counts = build_mart(paths, spark_master="local[1]")

    assert counts["dim_document"] == 1
    assert counts["fact_pdf_parse_quality"] == 1
    assert counts["fact_chunk_quality"] == 2
    assert counts["fact_indexing_result"] == 2
