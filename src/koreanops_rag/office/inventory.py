from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Iterator

import typer

from koreanops_rag.io import write_jsonl
from koreanops_rag.office.common import (
    document_id,
    document_type_from_archive,
    split_from_path,
)
from koreanops_rag.schemas import OfficeDocument

app = typer.Typer(add_completion=False)


def iter_inventory(
    dataset_root: Path,
    limit: int | None = None,
    split_filter: str | None = None,
    stratified: bool = False,
) -> Iterator[OfficeDocument]:
    groups: dict[str, list[OfficeDocument]] = {}
    archives = sorted(dataset_root.rglob("*원천데이터(pdf).zip"))
    for archive_path in archives:
        split = split_from_path(archive_path)
        if split_filter and split != split_filter:
            continue
        document_type = document_type_from_archive(archive_path)
        rows = []
        with zipfile.ZipFile(archive_path) as archive:
            for member in archive.infolist():
                if not member.filename.lower().endswith(".pdf"):
                    continue
                rows.append(
                    OfficeDocument(
                        doc_id=document_id(member.filename),
                        split=split,
                        document_type=document_type,
                        source_archive=str(archive_path.relative_to(dataset_root)),
                        source_member=member.filename,
                        file_size=member.file_size,
                    )
                )
        groups.setdefault(document_type, []).extend(rows)
        if not stratified:
            for row in rows:
                yield row
                if limit is not None:
                    limit -= 1
                    if limit == 0:
                        return
    if stratified:
        emitted = 0
        while any(groups.values()):
            for document_type in sorted(groups):
                if not groups[document_type]:
                    continue
                yield groups[document_type].pop(0)
                emitted += 1
                if limit is not None and emitted >= limit:
                    return


@app.command()
def run(
    dataset_root: Path,
    output_jsonl: Path,
    limit: int | None = typer.Option(None, min=1),
    split: str | None = typer.Option(None, help="training or validation"),
    stratified: bool = typer.Option(False, help="Round-robin by document type"),
) -> None:
    """Inventory office PDFs stored inside AI Hub ZIP archives."""
    if split not in {None, "training", "validation"}:
        raise typer.BadParameter("--split must be training or validation")
    count = write_jsonl(
        output_jsonl,
        iter_inventory(
            dataset_root,
            limit=limit,
            split_filter=split,
            stratified=stratified,
        ),
    )
    typer.echo(f"Wrote {count} office PDF manifest rows to {output_jsonl}")


def main() -> None:
    app()
