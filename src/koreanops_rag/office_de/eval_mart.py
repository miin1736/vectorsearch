from __future__ import annotations

import csv
from pathlib import Path

import typer

from koreanops_rag.io import ensure_parent
from koreanops_rag.office_de.paths import OfficeDePaths

app = typer.Typer(add_completion=False)


def _csv_to_jsonl(csv_path: Path, jsonl_path: Path) -> int:
    import json

    if not csv_path.exists():
        return -1
    ensure_parent(jsonl_path)
    count = 0
    with (
        csv_path.open("r", encoding="utf-8", newline="") as input_file,
        jsonl_path.open("w", encoding="utf-8", newline="\n") as output_file,
    ):
        for row in csv.DictReader(input_file):
            output_file.write(json.dumps(row, ensure_ascii=False) + "\n")
            count += 1
    return count


def write_eval_mart(
    paths: OfficeDePaths,
    retrieval_summary_csv: Path,
    rag_summary_csv: Path | None,
    *,
    output_root: Path | None = None,
    spark_master: str | None = None,
) -> dict[str, int]:
    from koreanops_rag.office_de.spark import _session

    target = output_root or paths.lake_mart_root
    staging = paths.data_root / "lake" / "_staging"
    retrieval_jsonl = staging / "retrieval_summary.jsonl"
    rag_jsonl = staging / "rag_summary.jsonl"
    counts = {
        "retrieval_summary_rows": _csv_to_jsonl(retrieval_summary_csv, retrieval_jsonl),
        "rag_summary_rows": _csv_to_jsonl(rag_summary_csv, rag_jsonl) if rag_summary_csv else -1,
    }
    spark = _session("ko_unstructured_v2_write_eval_mart", spark_master)
    try:
        if counts["retrieval_summary_rows"] >= 0:
            frame = spark.read.json(str(retrieval_jsonl))
            frame.write.mode("overwrite").parquet(str(target / "fact_retrieval_eval"))
        if counts["rag_summary_rows"] >= 0:
            frame = spark.read.json(str(rag_jsonl))
            frame.write.mode("overwrite").parquet(str(target / "fact_rag_eval"))
    finally:
        spark.stop()
    return counts


@app.command()
def run(
    retrieval_summary_csv: Path,
    rag_summary_csv: Path | None = typer.Option(None),
    data_root: Path = typer.Option(OfficeDePaths().data_root),
    output_root: Path | None = typer.Option(None),
    spark_master: str | None = typer.Option(None),
) -> None:
    """Convert retrieval/RAG evaluation summaries into mart Parquet tables."""
    counts = write_eval_mart(
        OfficeDePaths(data_root),
        retrieval_summary_csv,
        rag_summary_csv,
        output_root=output_root,
        spark_master=spark_master,
    )
    for table, count in counts.items():
        typer.echo(f"{table}: {'missing' if count < 0 else count}")


def main() -> None:
    app()
