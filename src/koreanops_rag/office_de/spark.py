from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable

import typer

from koreanops_rag.io import ensure_parent
from koreanops_rag.office_de.paths import OfficeDePaths

app = typer.Typer(add_completion=False)


def _session(app_name: str, master: str | None = None):
    from pyspark.sql import SparkSession

    builder = SparkSession.builder.appName(app_name)
    if master:
        builder = builder.master(master)
    return builder.getOrCreate()


def default_jsonl_sources(paths: OfficeDePaths) -> dict[str, Path]:
    return {
        "office_manifest": paths.manifest_jsonl,
        "office_documents_normalized": paths.documents_jsonl,
        "pdf_pages_raw": paths.pages_jsonl,
        "pdf_blocks_cleaned": paths.blocks_jsonl,
        "chunks_page": paths.chunks_page_jsonl,
        "chunks_structure": paths.chunks_structure_jsonl,
        "golden_questions_reviewed": paths.golden_questions_jsonl,
    }


def convert_jsonl_to_parquet(
    sources: dict[str, Path],
    output_root: Path,
    *,
    spark_master: str | None = None,
    mode: str = "overwrite",
) -> dict[str, int]:
    spark = _session("ko_unstructured_v2_jsonl_to_parquet", spark_master)
    counts: dict[str, int] = {}
    try:
        for table, source in sources.items():
            if not source.exists():
                counts[table] = -1
                continue
            output = output_root / table
            ensure_parent(output / "_placeholder")
            frame = spark.read.json(str(source))
            frame.write.mode(mode).parquet(str(output))
            counts[table] = frame.count()
    finally:
        spark.stop()
    return counts


def parse_extra_source(values: Iterable[str]) -> dict[str, Path]:
    output: dict[str, Path] = {}
    for value in values:
        if "=" not in value:
            raise typer.BadParameter("--source must be formatted as table=path")
        table, path = value.split("=", 1)
        output[table.strip()] = Path(path.strip())
    return output


@app.command()
def run(
    data_root: Path = typer.Option(OfficeDePaths().data_root),
    output_root: Path | None = typer.Option(None),
    spark_master: str | None = typer.Option(
        None,
        help="Optional Spark master URL, for example spark://localhost:7077.",
    ),
    source: list[str] = typer.Option(
        [],
        help="Optional table=path override. If any are provided, only these sources are used.",
    ),
) -> None:
    """Convert ko_unstructured_v2 JSONL artifacts to Parquet with PySpark."""
    paths = OfficeDePaths(data_root)
    sources = parse_extra_source(source) if source else default_jsonl_sources(paths)
    target_root = output_root or paths.lake_processed_root
    if spark_master is None:
        spark_master = os.getenv("SPARK_MASTER_URL")
    counts = convert_jsonl_to_parquet(sources, target_root, spark_master=spark_master)
    for table, count in counts.items():
        status = "missing" if count < 0 else str(count)
        typer.echo(f"{table}: {status}")


def main() -> None:
    app()

