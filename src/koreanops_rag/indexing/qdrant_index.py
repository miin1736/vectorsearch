from __future__ import annotations

import json
from pathlib import Path

import typer

from koreanops_rag.config import load_config
from koreanops_rag.io import ensure_parent, read_jsonl
from koreanops_rag.observability import RunRecorder, path_fingerprint, utc_now
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


def checkpoint_path(reports_dir: Path, collection: str) -> Path:
    return reports_dir / "checkpoints" / f"qdrant_{collection}.json"


def _read_checkpoint(path: Path) -> dict | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _write_checkpoint(
    path: Path,
    *,
    collection: str,
    config_path: Path,
    documents_jsonl: Path,
    indexed_count: int,
    status: str,
) -> None:
    ensure_parent(path)
    checkpoint = {
        "stage": "index_qdrant",
        "collection": collection,
        "config_path": str(config_path.resolve()),
        "input_artifact": path_fingerprint(documents_jsonl),
        "indexed_count": indexed_count,
        "status": status,
        "updated_at": utc_now(),
    }
    path.write_text(json.dumps(checkpoint, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _validate_resume_checkpoint(
    checkpoint: dict | None,
    *,
    collection: str,
    config_path: Path,
    documents_jsonl: Path,
) -> None:
    if not checkpoint:
        return
    expected = {
        "collection": collection,
        "config_path": str(config_path.resolve()),
        "input_artifact": path_fingerprint(documents_jsonl),
    }
    for key, value in expected.items():
        if checkpoint.get(key) != value:
            raise typer.BadParameter(
                f"Unsafe Qdrant resume: checkpoint {key} does not match current run."
            )


@app.command()
def run(
    documents_jsonl: Path,
    config_path: Path = Path("configs/default.yaml"),
    resume: bool = False,
    run_id: str | None = None,
) -> None:
    """Embed and upsert RAG documents into Qdrant."""
    config = load_config(config_path)
    reports_dir = config.data_root / "reports"
    checkpoint = checkpoint_path(reports_dir, config.qdrant.collection)
    with RunRecorder(
        "index_qdrant",
        reports_dir,
        run_id=run_id,
        command="koreanops-index-qdrant",
        config_path=config_path,
        input_paths=[documents_jsonl, config_path],
        output_paths=[checkpoint],
    ) as recorder:
        _run_index(documents_jsonl, config_path, resume, checkpoint, recorder)


def _run_index(
    documents_jsonl: Path,
    config_path: Path,
    resume: bool,
    checkpoint: Path,
    recorder: RunRecorder,
) -> None:
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
        _validate_resume_checkpoint(
            _read_checkpoint(checkpoint),
            collection=config.qdrant.collection,
            config_path=config_path,
            documents_jsonl=documents_jsonl,
        )
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
        _write_checkpoint(
            checkpoint,
            collection=config.qdrant.collection,
            config_path=config_path,
            documents_jsonl=documents_jsonl,
            indexed_count=total,
            status="running",
        )
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
        recorder.set_record_count(total)
        recorder.event("batch_indexed", indexed_count=total, batch_size=len(points))
        _write_checkpoint(
            checkpoint,
            collection=config.qdrant.collection,
            config_path=config_path,
            documents_jsonl=documents_jsonl,
            indexed_count=total,
            status="running",
        )
        typer.echo(f"Upserted {total} documents...")
    _write_checkpoint(
        checkpoint,
        collection=config.qdrant.collection,
        config_path=config_path,
        documents_jsonl=documents_jsonl,
        indexed_count=total,
        status="succeeded",
    )
    typer.echo(f"Indexed {total} documents into Qdrant collection {config.qdrant.collection}")


def main() -> None:
    app()
