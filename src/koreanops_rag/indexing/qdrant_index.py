from __future__ import annotations

from pathlib import Path

import typer

from koreanops_rag.config import load_config
from koreanops_rag.io import read_jsonl
from koreanops_rag.retrieval.vector_qdrant import SentenceTransformerEmbedder

app = typer.Typer(add_completion=False)


def batched(rows, size: int):
    batch = []
    for row in rows:
        batch.append(row)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


def skip_rows(rows, count: int):
    for idx, row in enumerate(rows):
        if idx < count:
            continue
        yield row


def embedding_text(row: dict) -> str:
    return str(row.get("embedding_text") or row["content"])


@app.command()
def run(
    documents_jsonl: Path,
    config_path: Path = Path("configs/default.yaml"),
    resume: bool = False,
) -> None:
    """Embed and upsert RAG documents into Qdrant."""
    from qdrant_client import QdrantClient, models

    config = load_config(config_path)
    embedder = SentenceTransformerEmbedder(
        config.embedding.model_name,
        config.embedding.device,
        document_prefix=config.embedding.document_prefix,
        query_prefix=config.embedding.query_prefix,
    )
    client = QdrantClient(url=config.qdrant.url)
    if resume and client.collection_exists(config.qdrant.collection):
        total = client.get_collection(config.qdrant.collection).points_count or 0
        rows = skip_rows(read_jsonl(documents_jsonl), total)
        typer.echo(f"Resuming Qdrant collection {config.qdrant.collection} from point {total}")
    else:
        vector_size = len(embedder.encode(["dimension probe"], batch_size=1, text_kind="document")[0])
        client.recreate_collection(
            collection_name=config.qdrant.collection,
            vectors_config=models.VectorParams(size=vector_size, distance=models.Distance.COSINE),
        )
        total = 0
        rows = read_jsonl(documents_jsonl)
    for batch in batched(rows, config.embedding.batch_size):
        vectors = embedder.encode(
            [embedding_text(row) for row in batch],
            config.embedding.batch_size,
            text_kind="document",
        )
        points = [
            models.PointStruct(
                id=idx + total,
                vector=vector,
                payload=row,
            )
            for idx, (row, vector) in enumerate(zip(batch, vectors, strict=True))
        ]
        client.upsert(collection_name=config.qdrant.collection, points=points)
        total += len(points)
        typer.echo(f"Upserted {total} documents...")
    typer.echo(f"Indexed {total} documents into Qdrant collection {config.qdrant.collection}")


def main() -> None:
    app()
