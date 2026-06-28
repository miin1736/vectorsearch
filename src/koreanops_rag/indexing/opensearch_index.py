from __future__ import annotations

import json
from pathlib import Path

import typer

from koreanops_rag.config import load_config
from koreanops_rag.io import ensure_parent, read_jsonl
from koreanops_rag.observability import RunRecorder, path_fingerprint, utc_now

app = typer.Typer(add_completion=False)


def create_index(client, index: str) -> None:
    if client.indices.exists(index=index):
        return
    client.indices.create(
        index=index,
        body={
            "mappings": {
                "properties": {
                    "doc_id": {"type": "keyword"},
                    "source_type": {"type": "keyword"},
                    "title": {"type": "text"},
                    "content": {"type": "text"},
                    "metadata": {"type": "object", "enabled": True},
                }
            }
        },
    )


def checkpoint_path(reports_dir: Path, index: str) -> Path:
    return reports_dir / "checkpoints" / f"opensearch_{index}.json"


def _write_checkpoint(
    path: Path,
    *,
    index: str,
    config_path: Path,
    documents_jsonl: Path,
    indexed_count: int,
    status: str,
) -> None:
    ensure_parent(path)
    checkpoint = {
        "stage": "index_opensearch",
        "index": index,
        "config_path": str(config_path.resolve()),
        "input_artifact": path_fingerprint(documents_jsonl),
        "indexed_count": indexed_count,
        "status": status,
        "updated_at": utc_now(),
    }
    path.write_text(json.dumps(checkpoint, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


@app.command()
def run(
    documents_jsonl: Path,
    config_path: Path = Path("configs/default.yaml"),
    run_id: str | None = None,
) -> None:
    """Index RAG documents into OpenSearch for BM25 retrieval."""
    from opensearchpy import OpenSearch, helpers

    config = load_config(config_path)
    reports_dir = config.data_root / "reports"
    checkpoint = checkpoint_path(reports_dir, config.opensearch.index)
    with RunRecorder(
        "index_opensearch",
        reports_dir,
        run_id=run_id,
        command="koreanops-index-opensearch",
        config_path=config_path,
        input_paths=[documents_jsonl, config_path],
        output_paths=[checkpoint],
    ) as recorder:
        _write_checkpoint(
            checkpoint,
            index=config.opensearch.index,
            config_path=config_path,
            documents_jsonl=documents_jsonl,
            indexed_count=0,
            status="running",
        )
        client = OpenSearch(hosts=[config.opensearch.url], use_ssl=False)
        create_index(client, config.opensearch.index)
        actions = (
            {"_index": config.opensearch.index, "_id": row["doc_id"], "_source": row}
            for row in read_jsonl(documents_jsonl)
        )
        success, _ = helpers.bulk(client, actions)
        recorder.set_record_count(success)
        recorder.event("bulk_indexed", indexed_count=success)
        _write_checkpoint(
            checkpoint,
            index=config.opensearch.index,
            config_path=config_path,
            documents_jsonl=documents_jsonl,
            indexed_count=success,
            status="succeeded",
        )
    typer.echo(f"Indexed {success} documents into OpenSearch index {config.opensearch.index}")


def main() -> None:
    app()
