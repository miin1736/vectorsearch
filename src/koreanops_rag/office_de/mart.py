from __future__ import annotations

import os
from pathlib import Path

import typer

from koreanops_rag.office_de.quality import count_jsonl
from koreanops_rag.office_de.paths import OfficeDePaths
from koreanops_rag.office_de.spark import _session

app = typer.Typer(add_completion=False)


def build_mart(
    paths: OfficeDePaths,
    output_root: Path | None = None,
    *,
    spark_master: str | None = None,
    mode: str = "overwrite",
) -> dict[str, int]:
    target = output_root or paths.lake_mart_root
    spark = _session("ko_unstructured_v2_build_mart", spark_master)
    counts: dict[str, int] = {}
    try:
        manifest = spark.read.json(str(paths.manifest_jsonl))
        documents = spark.read.json(str(paths.documents_jsonl))
        page_chunks = spark.read.json(str(paths.chunks_page_jsonl))
        structure_chunks = spark.read.json(str(paths.chunks_structure_jsonl))

        dim_document = manifest.select(
            "doc_id",
            "split",
            "document_type",
            "source_archive",
            "source_member",
            "file_size",
        )
        dim_document.write.mode(mode).parquet(str(target / "dim_document"))
        counts["dim_document"] = dim_document.count()

        parse_quality = documents.selectExpr(
            "doc_id",
            "title",
            "length(coalesce(content, '')) as content_chars",
            "length(coalesce(content, '')) = 0 as empty_content",
            "metadata.page_count as page_count",
            "metadata.text_layer_pages as text_layer_pages",
            "metadata.parse_error as parse_error",
        )
        parse_quality.write.mode(mode).parquet(str(target / "fact_pdf_parse_quality"))
        counts["fact_pdf_parse_quality"] = parse_quality.count()

        chunks = page_chunks.unionByName(structure_chunks, allowMissingColumns=True)
        chunk_quality = chunks.selectExpr(
            "metadata.chunking_strategy as chunking_strategy",
            "metadata.parent_doc_id as parent_doc_id",
            "doc_id as chunk_id",
            "length(coalesce(content, '')) as content_chars",
            "metadata.page_start as page_start",
            "metadata.page_end as page_end",
        )
        chunk_quality.write.mode(mode).parquet(str(target / "fact_chunk_quality"))
        counts["fact_chunk_quality"] = chunk_quality.count()

        indexing_rows = [
            {
                "chunking_strategy": "page",
                "target_name": "ko_unstructured_pdf_page",
                "chunk_input_count": count_jsonl(paths.chunks_page_jsonl),
            },
            {
                "chunking_strategy": "structure",
                "target_name": "ko_unstructured_pdf_structure",
                "chunk_input_count": count_jsonl(paths.chunks_structure_jsonl),
            },
        ]
        indexing_result = spark.createDataFrame(indexing_rows)
        indexing_result.write.mode(mode).parquet(str(target / "fact_indexing_result"))
        counts["fact_indexing_result"] = indexing_result.count()
    finally:
        spark.stop()
    return counts


@app.command()
def run(
    data_root: Path = typer.Option(OfficeDePaths().data_root),
    output_root: Path | None = typer.Option(None),
    spark_master: str | None = typer.Option(None),
) -> None:
    """Build Parquet mart tables for ko_unstructured_v2."""
    if spark_master is None:
        spark_master = os.getenv("SPARK_MASTER_URL")
    counts = build_mart(OfficeDePaths(data_root), output_root, spark_master=spark_master)
    for table, count in counts.items():
        typer.echo(f"{table}: {count}")


def main() -> None:
    app()
