from __future__ import annotations

import json
import re
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Any

import typer

from koreanops_rag.io import ensure_parent
from koreanops_rag.io import read_jsonl
from koreanops_rag.office.common import document_id, document_type_from_archive, split_from_path

app = typer.Typer(add_completion=False)
REFERENCE_ONLY_RE = re.compile(r"^(?:\s*\[&\][^\s]+\s*)+$")


def _element_text(learning: dict[str, Any]) -> str:
    return str(
        learning.get("plain_text")
        or learning.get("visual_description")
        or learning.get("document_description")
        or ""
    ).strip()


def _is_reference_only(value: str) -> bool:
    """Return whether a label value only points at other annotation JSON files."""
    return bool(value.strip() and REFERENCE_ONLY_RE.fullmatch(value.strip()))


def _page_texts(elements: list[dict[str, Any]]) -> tuple[str, str, str]:
    """Build semantic page content and a PDF-text-only parsing reference."""
    d01 = next(
        (
            item["document_description"]
            for item in elements
            if item["class_name"] == "D01" and item["document_description"]
        ),
        "",
    )
    plain_text = "\n".join(
        item["plain_text"]
        for item in elements
        if item["plain_text"] and item["class_name"] != "D01"
    )
    visual_text = "\n".join(
        item["visual_description"] for item in elements if item["visual_description"]
    )
    if d01 and not _is_reference_only(d01):
        return d01, d01, "document_description"
    if plain_text:
        return plain_text, plain_text, "plain_text"
    if visual_text:
        return visual_text, "", "visual_description"
    return "", "", "empty"


@app.command()
def run(
    dataset_root: Path,
    documents_output: Path,
    pages_output: Path,
    elements_output: Path,
    limit: int | None = typer.Option(None, min=1),
    manifest_jsonl: Path | None = None,
) -> None:
    """Build evaluation-only Oracle text and layout records from label JSON."""
    documents: dict[str, dict[str, Any]] = {}
    pages: dict[str, dict[int, list[dict[str, Any]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    allowed_ids = (
        {row["doc_id"] for row in read_jsonl(manifest_jsonl)}
        if manifest_jsonl is not None
        else None
    )
    selected_ids: set[str] = set()

    for archive_path in sorted(dataset_root.rglob("*json.zip")):
        split = split_from_path(archive_path)
        document_type = document_type_from_archive(archive_path)
        with zipfile.ZipFile(archive_path) as archive:
            for member in archive.infolist():
                if not member.filename.lower().endswith(".json"):
                    continue
                record = json.loads(archive.read(member).decode("utf-8-sig"))
                raw = record["raw_data_info"]
                source = record["source_data_info"]
                learning = record["learning_data_info"]
                doc_id = document_id(source["source_data_name_pdf"])
                if allowed_ids is not None and doc_id not in allowed_ids:
                    continue
                if doc_id not in selected_ids:
                    if limit is not None and len(selected_ids) >= limit:
                        continue
                    selected_ids.add(doc_id)
                if doc_id not in selected_ids:
                    continue
                documents.setdefault(
                    doc_id,
                    {
                        "doc_id": doc_id,
                        "source_type": "office_document",
                        "title": str(raw.get("doc_name") or doc_id),
                        "metadata": {
                            "split": split,
                            "document_type": document_type,
                            "publisher": str(raw.get("publisher") or ""),
                            "organ_type": str(raw.get("organ_type") or ""),
                            "source_pdf": source["source_data_name_pdf"],
                            "oracle_only": True,
                        },
                    },
                )
                page_num = int(learning["page_num"])
                bbox = learning.get("bounding_box") or [0, 0, 0, 0]
                pages[doc_id][page_num].append(
                    {
                        "doc_id": doc_id,
                        "page_num": page_num,
                        "class_name": str(learning.get("class_name") or ""),
                        "bbox": bbox,
                        "text": _element_text(learning),
                        "plain_text": str(learning.get("plain_text") or ""),
                        "visual_description": str(
                            learning.get("visual_description") or ""
                        ),
                        "document_description": str(
                            learning.get("document_description") or ""
                        ),
                    }
                )

    for path in (documents_output, pages_output, elements_output):
        ensure_parent(path)
    with (
        documents_output.open("w", encoding="utf-8", newline="\n") as doc_file,
        pages_output.open("w", encoding="utf-8", newline="\n") as page_file,
        elements_output.open("w", encoding="utf-8", newline="\n") as element_file,
    ):
        for doc_id in sorted(documents):
            page_texts = []
            for page_num in sorted(pages[doc_id]):
                elements = sorted(
                    pages[doc_id][page_num],
                    key=lambda item: (
                        item["bbox"][1] if len(item["bbox"]) >= 2 else 0,
                        item["bbox"][0] if item["bbox"] else 0,
                    ),
                )
                page_text, parsing_reference_text, oracle_text_type = _page_texts(elements)
                page_texts.append(page_text)
                page_file.write(json.dumps(
                    {
                        "doc_id": doc_id,
                        "page_num": page_num,
                        "content": page_text,
                        "parsing_reference_text": parsing_reference_text,
                        "oracle_text_type": oracle_text_type,
                    },
                    ensure_ascii=False,
                ) + "\n")
                for item in elements:
                    element_file.write(json.dumps(item, ensure_ascii=False) + "\n")
            document = documents[doc_id]
            content = "\n\n".join(text for text in page_texts if text)
            doc_file.write(json.dumps(
                {
                    **document,
                    "content": content,
                    "embedding_text": content,
                    "metadata": {
                        **document["metadata"],
                        "page_count": len(pages[doc_id]),
                    },
                },
                ensure_ascii=False,
            ) + "\n")
    typer.echo(
        f"Wrote {len(documents)} Oracle documents, "
        f"{sum(len(value) for value in pages.values())} pages"
    )


def main() -> None:
    app()
