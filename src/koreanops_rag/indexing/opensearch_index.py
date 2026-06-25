from __future__ import annotations

from pathlib import Path

import typer

from koreanops_rag.config import load_config
from koreanops_rag.io import read_jsonl

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


@app.command()
def run(documents_jsonl: Path, config_path: Path = Path("configs/default.yaml")) -> None:
    """Index RAG documents into OpenSearch for BM25 retrieval."""
    from opensearchpy import OpenSearch, helpers

    config = load_config(config_path)
    client = OpenSearch(hosts=[config.opensearch.url], use_ssl=False)
    create_index(client, config.opensearch.index)
    actions = (
        {"_index": config.opensearch.index, "_id": row["doc_id"], "_source": row}
        for row in read_jsonl(documents_jsonl)
    )
    success, _ = helpers.bulk(client, actions)
    typer.echo(f"Indexed {success} documents into OpenSearch index {config.opensearch.index}")


def main() -> None:
    app()
