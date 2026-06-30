from __future__ import annotations

import csv
import hashlib
import re
from collections import Counter
from os import getenv
from pathlib import Path
from statistics import mean
from typing import Any, Iterable, Literal, cast

import typer

from koreanops_rag.io import ensure_parent, read_jsonl, write_jsonl

app = typer.Typer(add_completion=False)

CleaningProfile = Literal["clean_light", "clean_structural", "clean_embedding_optimized"]
PROFILES: tuple[CleaningProfile, ...] = (
    "clean_light",
    "clean_structural",
    "clean_embedding_optimized",
)

URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
DOI_RE = re.compile(r"\bdoi\s*:?\s*10\.\d{4,9}/\S+|10\.\d{4,9}/\S+", re.IGNORECASE)
EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b")
HTML_TAG_RE = re.compile(r"</?[A-Za-z][^>]{0,80}>")
BRACKET_MARKER_RE = re.compile(r"\[(?:provider|download|table|figure|fig\.?|표|그림)[^\]]*\]", re.IGNORECASE)
TABLE_FIGURE_RE = re.compile(
    r"^\s*(table|figure|fig\.?|표|그림)\s*[\dIVXivx.-]*\s*[:.]?",
    re.IGNORECASE | re.MULTILINE,
)
REFERENCE_HEADING_RE = re.compile(
    r"^\s*(references|bibliography|참고문헌|인용문헌)\s*$",
    re.IGNORECASE | re.MULTILINE,
)
PAGE_NUMBER_RE = re.compile(r"^\s*(?:page\s*)?\d{1,4}\s*$", re.IGNORECASE | re.MULTILINE)
PROVIDER_RE = re.compile(r"earticle\.net|download by ip|\[provider:|provider", re.IGNORECASE)
MULTISPACE_RE = re.compile(r"[ \t]{2,}")

NOISE_PATTERNS = {
    "url": URL_RE,
    "doi": DOI_RE,
    "email": EMAIL_RE,
    "html_tag": HTML_TAG_RE,
    "bracket_marker": BRACKET_MARKER_RE,
    "table_figure": TABLE_FIGURE_RE,
    "reference_heading": REFERENCE_HEADING_RE,
    "page_number": PAGE_NUMBER_RE,
    "provider": PROVIDER_RE,
}


def default_data_root() -> Path:
    return Path(getenv("DATA_ROOT", r"C:\vectorsearch-data")) / "ko-dense-technical"


def default_pilot_processed_path(name: str) -> Path:
    return default_data_root() / "processed" / "pilot_1000" / name


def default_pilot_eval_path(name: str) -> Path:
    return default_data_root() / "eval" / "pilot_1000" / name


def normalize_spaces(text: str) -> str:
    lines = [MULTISPACE_RE.sub(" ", line).strip() for line in str(text).splitlines()]
    collapsed = "\n".join(line for line in lines if line)
    return re.sub(r"\n{3,}", "\n\n", collapsed).strip()


def raw_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def noise_counts(text: str) -> dict[str, int]:
    return {name: len(pattern.findall(text)) for name, pattern in NOISE_PATTERNS.items()}


def noise_score(text: str) -> float:
    if not text:
        return 0.0
    weighted = sum(noise_counts(text).values())
    return round(weighted / max(len(text.split()), 1), 6)


def sentence_boundary_break_ratio(text: str) -> float:
    lines = [line.strip() for line in str(text).splitlines() if line.strip()]
    if not lines:
        return 0.0
    broken = 0
    for line in lines:
        if len(line) < 30:
            continue
        if not re.search(r"[.!?]$|[다요]\.$", line):
            broken += 1
    return round(broken / max(len(lines), 1), 6)


def collect_repeated_lines(pages_jsonl: Path | None) -> set[str]:
    if not pages_jsonl or not pages_jsonl.exists():
        return set()
    counts: Counter[str] = Counter()
    for page in read_jsonl(pages_jsonl):
        seen_in_page = set()
        for line in str(page.get("clean_text") or page.get("raw_text") or "").splitlines():
            value = normalize_spaces(line)
            if 5 <= len(value) <= 180:
                seen_in_page.add(value)
        counts.update(seen_in_page)
    return {line for line, count in counts.items() if count >= 3}


def _strip_inline_noise(line: str, *, remove_citation_markers: bool = False) -> str:
    line = URL_RE.sub(" ", line)
    line = DOI_RE.sub(" ", line)
    line = EMAIL_RE.sub(" ", line)
    line = HTML_TAG_RE.sub(" ", line)
    line = BRACKET_MARKER_RE.sub(" ", line)
    if remove_citation_markers:
        line = re.sub(r"\[[\d,\s-]{1,30}\]", " ", line)
        line = re.sub(r"\((?:19|20)\d{2}[a-z]?(?:[;,]\s*(?:19|20)\d{2}[a-z]?)*\)", " ", line)
    return normalize_spaces(line)


def _should_drop_line(
    line: str,
    *,
    profile: CleaningProfile,
    repeated_lines: set[str],
) -> bool:
    normalized = normalize_spaces(line)
    if not normalized:
        return True
    if PAGE_NUMBER_RE.match(normalized):
        return True
    if PROVIDER_RE.search(normalized):
        return True
    if profile in {"clean_structural", "clean_embedding_optimized"}:
        if normalized in repeated_lines:
            return True
        if TABLE_FIGURE_RE.match(normalized) and len(normalized) < 180:
            return True
    if profile == "clean_embedding_optimized":
        if len(normalized) < 8:
            return True
        if re.match(r"^\s*\[[\d,\s-]{1,30}\]", normalized):
            return True
        if normalized.count("|") >= 3:
            return True
    return False


def clean_text(
    text: str,
    *,
    profile: CleaningProfile,
    repeated_lines: set[str] | None = None,
    section_type: str = "",
) -> tuple[str, dict[str, int]]:
    repeated_lines = repeated_lines or set()
    before = noise_counts(text)
    remove_citation_markers = profile == "clean_embedding_optimized"
    lines = []
    in_references = False
    for raw_line in str(text).splitlines():
        line = normalize_spaces(raw_line)
        if profile in {"clean_structural", "clean_embedding_optimized"}:
            if REFERENCE_HEADING_RE.match(line) or section_type == "references":
                in_references = True
            if in_references:
                continue
        if _should_drop_line(line, profile=profile, repeated_lines=repeated_lines):
            continue
        cleaned = _strip_inline_noise(line, remove_citation_markers=remove_citation_markers)
        if (
            profile == "clean_embedding_optimized"
            and len(cleaned) >= 30
            and not re.search(r"[.!?]$|[다요]\.$", cleaned)
        ):
            cleaned = f"{cleaned}."
        if cleaned:
            lines.append(cleaned)
    separator = " " if profile == "clean_embedding_optimized" else "\n"
    cleaned_text = normalize_spaces(separator.join(lines))
    after = noise_counts(cleaned_text)
    removed = {name: max(before[name] - after[name], 0) for name in before}
    return cleaned_text, removed


def clean_row_texts(
    row: dict[str, Any],
    *,
    text_key: str,
    profile: CleaningProfile,
    repeated_lines: set[str],
) -> tuple[str, str, dict[str, int]]:
    raw_text = str(row.get(text_key) or row.get("content") or "")
    section_type = str(row.get("section_type") or "")
    content, removed = clean_text(
        raw_text,
        profile=profile if profile != "clean_embedding_optimized" else "clean_structural",
        repeated_lines=repeated_lines,
        section_type=section_type,
    )
    embedding_text = content
    if profile == "clean_embedding_optimized":
        embedding_text, embedding_removed = clean_text(
            raw_text,
            profile=profile,
            repeated_lines=repeated_lines,
            section_type=section_type,
        )
        removed = {key: removed.get(key, 0) + embedding_removed.get(key, 0) for key in removed}
    return content, embedding_text, removed


def _metadata_with_cleaning(
    row: dict[str, Any],
    *,
    profile: CleaningProfile,
    raw_text: str,
    content: str,
    embedding_text: str,
    removed: dict[str, int],
) -> dict[str, Any]:
    metadata = dict(row.get("metadata", {}))
    metadata.update(
        {
            "cleaning_profile": profile,
            "noise_removed": removed,
            "raw_content_hash": raw_hash(raw_text),
            "raw_char_count": len(raw_text),
            "cleaned_char_count": len(content),
            "embedding_char_count": len(embedding_text),
            "noise_score_before": noise_score(raw_text),
            "noise_score_after": noise_score(embedding_text),
            "sentence_boundary_break_before": sentence_boundary_break_ratio(raw_text),
            "sentence_boundary_break_after": sentence_boundary_break_ratio(embedding_text),
        }
    )
    return metadata


def preprocess_documents_and_sections(
    documents_jsonl: Path,
    sections_jsonl: Path,
    output_dir: Path,
    *,
    profile: CleaningProfile,
    pages_jsonl: Path | None = None,
) -> dict[str, Path]:
    repeated_lines = collect_repeated_lines(pages_jsonl)
    docs_out = output_dir / "documents.jsonl"
    sections_out = output_dir / "sections.jsonl"
    report_out = output_dir / "cleaning_report.csv"

    report_rows = []
    documents = []
    for row in read_jsonl(documents_jsonl):
        raw_text = str(row.get("content") or "")
        content, embedding_text, removed = clean_row_texts(
            row,
            text_key="content",
            profile=profile,
            repeated_lines=repeated_lines,
        )
        updated = dict(row)
        updated["content"] = content
        updated["embedding_text"] = embedding_text
        updated["metadata"] = _metadata_with_cleaning(
            row,
            profile=profile,
            raw_text=raw_text,
            content=content,
            embedding_text=embedding_text,
            removed=removed,
        )
        documents.append(updated)
        report_rows.append(_report_row("document", str(row.get("doc_id", "")), updated["metadata"]))

    sections = []
    for row in read_jsonl(sections_jsonl):
        raw_text = str(row.get("text") or "")
        content, embedding_text, removed = clean_row_texts(
            row,
            text_key="text",
            profile=profile,
            repeated_lines=repeated_lines,
        )
        if not content.strip() and not embedding_text.strip():
            continue
        updated = dict(row)
        updated["raw_text"] = raw_text
        updated["text"] = content
        updated["embedding_text"] = embedding_text
        updated["metadata"] = _metadata_with_cleaning(
            row,
            profile=profile,
            raw_text=raw_text,
            content=content,
            embedding_text=embedding_text,
            removed=removed,
        )
        sections.append(updated)
        report_rows.append(_report_row("section", str(row.get("section_id", "")), updated["metadata"]))

    write_jsonl(docs_out, documents)
    write_jsonl(sections_out, sections)
    write_report_csv(report_out, report_rows)
    return {"documents": docs_out, "sections": sections_out, "report": report_out}


def _report_row(row_type: str, row_id: str, metadata: dict[str, Any]) -> dict[str, Any]:
    removed = metadata.get("noise_removed", {})
    return {
        "row_type": row_type,
        "row_id": row_id,
        "cleaning_profile": metadata.get("cleaning_profile", ""),
        "raw_content_hash": metadata.get("raw_content_hash", ""),
        "raw_char_count": metadata.get("raw_char_count", 0),
        "cleaned_char_count": metadata.get("cleaned_char_count", 0),
        "embedding_char_count": metadata.get("embedding_char_count", 0),
        "noise_score_before": metadata.get("noise_score_before", 0.0),
        "noise_score_after": metadata.get("noise_score_after", 0.0),
        "sentence_boundary_break_before": metadata.get("sentence_boundary_break_before", 0.0),
        "sentence_boundary_break_after": metadata.get("sentence_boundary_break_after", 0.0),
        **{f"removed_{key}": value for key, value in sorted(removed.items())},
    }


def write_report_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    ensure_parent(path)
    fieldnames = sorted({key for row in rows for key in row})
    preferred = [
        "row_type",
        "row_id",
        "cleaning_profile",
        "raw_content_hash",
        "raw_char_count",
        "cleaned_char_count",
        "embedding_char_count",
        "noise_score_before",
        "noise_score_after",
        "sentence_boundary_break_before",
        "sentence_boundary_break_after",
    ]
    ordered = [field for field in preferred if field in fieldnames] + [
        field for field in fieldnames if field not in preferred
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=ordered)
        writer.writeheader()
        writer.writerows(rows)


def summarize_noise(rows: Iterable[dict[str, Any]], *, text_key: str, dataset: str) -> dict[str, Any]:
    total = 0
    total_chars = 0
    scores = []
    breaks = []
    counters: Counter[str] = Counter()
    for row in rows:
        text = str(row.get(text_key) or row.get("content") or "")
        total += 1
        total_chars += len(text)
        scores.append(noise_score(text))
        breaks.append(sentence_boundary_break_ratio(text))
        counters.update(noise_counts(text))
    return {
        "dataset": dataset,
        "rows": total,
        "total_chars": total_chars,
        "avg_noise_score": round(mean(scores), 6) if scores else 0.0,
        "avg_sentence_boundary_break_ratio": round(mean(breaks), 6) if breaks else 0.0,
        **{f"{key}_count": counters.get(key, 0) for key in NOISE_PATTERNS},
    }


def write_noise_profile(output_csv: Path, summaries: list[dict[str, Any]]) -> None:
    write_report_csv(output_csv, summaries)


def validate_profiles(values: list[str] | None) -> list[CleaningProfile]:
    if not values:
        return list(PROFILES)
    valid = set(PROFILES)
    profiles: list[CleaningProfile] = []
    for value in values:
        for item in value.split(","):
            normalized = item.strip()
            if not normalized:
                continue
            if normalized not in valid:
                raise typer.BadParameter(f"Unknown cleaning profile: {normalized}")
            profiles.append(cast(CleaningProfile, normalized))
    return profiles


@app.command("profile-noise")
def profile_noise_command(
    documents_jsonl: Path | None = None,
    sections_jsonl: Path | None = None,
    chunks_jsonl: Path | None = None,
    output_csv: Path | None = None,
) -> None:
    """Profile noise markers in raw V3 pilot documents, sections, and chunks."""
    documents_jsonl = documents_jsonl or default_pilot_processed_path("documents_normalized.jsonl")
    sections_jsonl = sections_jsonl or default_pilot_processed_path("sections.jsonl")
    chunks_jsonl = chunks_jsonl or default_pilot_processed_path("chunks_baseline_fixed_512.jsonl")
    output_csv = output_csv or default_pilot_eval_path("preprocessing/noise_profile_raw.csv")
    summaries = [
        summarize_noise(read_jsonl(documents_jsonl), text_key="content", dataset="documents_raw"),
        summarize_noise(read_jsonl(sections_jsonl), text_key="text", dataset="sections_raw"),
    ]
    if chunks_jsonl.exists():
        summaries.append(
            summarize_noise(read_jsonl(chunks_jsonl), text_key="content", dataset="chunks_raw_fixed_512")
        )
    write_noise_profile(output_csv, summaries)
    typer.echo(f"Wrote raw noise profile to {output_csv}")


@app.command("build")
def build_command(
    documents_jsonl: Path | None = None,
    sections_jsonl: Path | None = None,
    pages_jsonl: Path | None = None,
    output_root: Path | None = None,
    profile: list[str] | None = typer.Option(None, "--profile"),
) -> None:
    """Build preprocessed pilot documents and sections for cleaning profiles."""
    documents_jsonl = documents_jsonl or default_pilot_processed_path("documents_normalized.jsonl")
    sections_jsonl = sections_jsonl or default_pilot_processed_path("sections.jsonl")
    pages_jsonl = pages_jsonl or default_pilot_processed_path("pages.jsonl")
    output_root = output_root or default_pilot_processed_path("preprocessed")
    profiles = validate_profiles(profile)
    for item in profiles:
        outputs = preprocess_documents_and_sections(
            documents_jsonl,
            sections_jsonl,
            output_root / item,
            profile=item,
            pages_jsonl=pages_jsonl,
        )
        typer.echo(f"Wrote {item}: {outputs['documents']}, {outputs['sections']}")


def main() -> None:
    app()
