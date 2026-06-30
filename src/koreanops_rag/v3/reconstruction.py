from __future__ import annotations

import csv
import hashlib
import re
from collections import Counter
from os import getenv
from pathlib import Path
from statistics import mean
from typing import Any, Literal, cast

import typer

from koreanops_rag.io import ensure_parent, read_jsonl, write_jsonl
from koreanops_rag.v3.preprocessing import noise_score, sentence_boundary_break_ratio

app = typer.Typer(add_completion=False)

ReconstructionProfile = Literal["reconstruct_light", "reconstruct_packed", "reconstruct_fielded"]
PROFILES: tuple[ReconstructionProfile, ...] = (
    "reconstruct_light",
    "reconstruct_packed",
    "reconstruct_fielded",
)

URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
DOI_RE = re.compile(r"\bdoi\s*:?\s*10\.\d{4,9}/\S+|10\.\d{4,9}/\S+", re.IGNORECASE)
EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b")
PROVIDER_RE = re.compile(r"earticle\.net|download by ip|\[provider:|provider", re.IGNORECASE)
PAGE_NUMBER_RE = re.compile(r"^(?:page\s*)?\d{1,4}$", re.IGNORECASE)
MULTISPACE_RE = re.compile(r"[ \t]{2,}")
BROKEN_KOREAN_RE = re.compile(r"[가-힣]\s*\n\s*[가-힣]")

CASE_KEYWORDS = {
    "table": ("table", "표 ", "<table", "|"),
    "figure": ("figure", "fig.", "그림 "),
    "caption": ("caption", "캡션", "source", "출처"),
    "reference": ("references", "참고문헌", "인용문헌", "bibliography"),
    "formula": ("=", "∑", "≤", "≥", "±", "β", "α"),
}
META_HINTS = ("abstract", "국문초록", "주제어", "keywords", "journal", "vol.", "no.")
SENTENCE_ENDINGS = (".", "?", "!", "다", "요", "음", "함", ")", "]")


def default_data_root() -> Path:
    return Path(getenv("DATA_ROOT", r"C:\vectorsearch-data")) / "ko-dense-technical"


def default_pilot_processed_path(name: str) -> Path:
    return default_data_root() / "processed" / "pilot_1000" / name


def default_pilot_eval_path(name: str) -> Path:
    return default_data_root() / "eval" / "pilot_1000" / name


def normalize_line(text: str) -> str:
    return MULTISPACE_RE.sub(" ", str(text).strip())


def normalize_text(text: str) -> str:
    lines = [normalize_line(line) for line in str(text).splitlines()]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(line for line in lines if line)).strip()


def raw_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def detect_case_type(line: str) -> str:
    normalized = normalize_line(line)
    lower = normalized.lower()
    if not normalized:
        return "empty"
    if PAGE_NUMBER_RE.match(normalized):
        return "page_number"
    if PROVIDER_RE.search(normalized) or URL_RE.search(normalized) or DOI_RE.search(normalized):
        return "provider_or_link"
    for case_type, needles in CASE_KEYWORDS.items():
        if any(needle in lower or needle in normalized for needle in needles):
            return case_type
    if any(hint in lower for hint in META_HINTS):
        return "metadata_anchor"
    if len(normalized) <= 80 and ("*" in normalized or "대학교" in normalized or "저자" in normalized):
        return "author_affiliation"
    if len(normalized) <= 120 and re.match(r"^\d+(?:\.\d+)*\s+", normalized):
        return "section_heading"
    if BROKEN_KOREAN_RE.search(line):
        return "broken_korean"
    return "body"


def strip_low_value_noise(line: str) -> str:
    line = URL_RE.sub(" ", line)
    line = DOI_RE.sub(" ", line)
    line = EMAIL_RE.sub(" ", line)
    line = re.sub(r"\[(?:provider|download)[^\]]*\]", " ", line, flags=re.IGNORECASE)
    return normalize_line(line)


def should_preserve_case(case_type: str) -> bool:
    return case_type in {
        "table",
        "figure",
        "caption",
        "reference",
        "formula",
        "metadata_anchor",
        "author_affiliation",
        "section_heading",
    }


def is_packable_continuation(previous: str, current: str) -> bool:
    if not previous or not current:
        return False
    prev = previous.rstrip()
    cur = current.lstrip()
    if detect_case_type(previous) != "body" or detect_case_type(current) != "body":
        return False
    if prev.endswith(SENTENCE_ENDINGS):
        return False
    if len(prev) < 12 or len(cur) < 2:
        return False
    if re.search(r"[가-힣A-Za-z0-9]$", prev) and re.match(r"^[가-힣a-z0-9]", cur):
        return True
    return False


def pack_lines(lines: list[str]) -> list[str]:
    packed: list[str] = []
    for line in lines:
        if not packed:
            packed.append(line)
            continue
        if is_packable_continuation(packed[-1], line):
            packed[-1] = f"{packed[-1]} {line}"
        else:
            packed.append(line)
    return packed


def reconstruct_text(raw_text: str, *, profile: ReconstructionProfile) -> dict[str, Any]:
    raw_lines = str(raw_text).splitlines()
    content_lines: list[str] = []
    bm25_lines: list[str] = []
    embedding_lines: list[str] = []
    display_lines: list[str] = []
    preserved: list[dict[str, Any]] = []
    alignment: list[dict[str, Any]] = []
    removed_counts: Counter[str] = Counter()

    for raw_index, raw_line in enumerate(raw_lines):
        normalized = normalize_line(raw_line)
        case_type = detect_case_type(raw_line)
        if not normalized:
            continue
        if case_type == "page_number":
            removed_counts[case_type] += 1
            continue

        stripped = strip_low_value_noise(normalized)
        if not stripped:
            removed_counts[case_type] += 1
            continue

        preserve = should_preserve_case(case_type)
        if preserve:
            preserved.append(
                {
                    "case_type": case_type,
                    "raw_line_index": raw_index,
                    "raw_line": normalized,
                    "text": stripped,
                    "decision": "preserve_text",
                    "reason": "retrieval_or_evidence_anchor",
                }
            )

        content_lines.append(stripped)
        display_lines.append(normalized)
        bm25_lines.append(stripped)
        if case_type in {"provider_or_link"}:
            removed_counts[case_type] += 1
            continue
        if profile == "reconstruct_light":
            embedding_lines.append(stripped)
        elif preserve and case_type in {"table", "figure", "caption", "reference", "formula"}:
            embedding_lines.append(stripped)
        elif case_type != "author_affiliation":
            embedding_lines.append(stripped)
        alignment.append(
            {
                "raw_line_index": raw_index,
                "case_type": case_type,
                "content_line_index": len(content_lines) - 1,
                "embedding_line_index": max(len(embedding_lines) - 1, 0),
            }
        )

    if profile in {"reconstruct_packed", "reconstruct_fielded"}:
        embedding_lines = pack_lines(embedding_lines)

    content = normalize_text("\n".join(content_lines))
    bm25_text = normalize_text("\n".join(bm25_lines))
    embedding_text = normalize_text("\n".join(embedding_lines))
    display_text = normalize_text("\n".join(display_lines))
    return {
        "content": content,
        "bm25_text": bm25_text,
        "embedding_text": embedding_text,
        "display_text": display_text,
        "preserved_elements": preserved,
        "alignment_map": alignment if profile == "reconstruct_fielded" else [],
        "removed_counts": dict(removed_counts),
    }


def reconstruction_metadata(
    row: dict[str, Any],
    *,
    profile: ReconstructionProfile,
    raw_text: str,
    reconstructed: dict[str, Any],
) -> dict[str, Any]:
    metadata = dict(row.get("metadata", {}))
    metadata.update(
        {
            "reconstruction_profile": profile,
            "raw_content_hash": raw_hash(raw_text),
            "raw_char_count": len(raw_text),
            "content_char_count": len(reconstructed["content"]),
            "bm25_char_count": len(reconstructed["bm25_text"]),
            "embedding_char_count": len(reconstructed["embedding_text"]),
            "display_char_count": len(reconstructed["display_text"]),
            "preserved_element_count": len(reconstructed["preserved_elements"]),
            "removed_counts": reconstructed["removed_counts"],
            "noise_score_before": noise_score(raw_text),
            "noise_score_after": noise_score(reconstructed["embedding_text"]),
            "sentence_boundary_break_before": sentence_boundary_break_ratio(raw_text),
            "sentence_boundary_break_after": sentence_boundary_break_ratio(reconstructed["embedding_text"]),
        }
    )
    return metadata


def report_row(row_type: str, row_id: str, metadata: dict[str, Any]) -> dict[str, Any]:
    return {
        "row_type": row_type,
        "row_id": row_id,
        "profile": metadata.get("reconstruction_profile", ""),
        "raw_content_hash": metadata.get("raw_content_hash", ""),
        "raw_char_count": metadata.get("raw_char_count", 0),
        "content_char_count": metadata.get("content_char_count", 0),
        "bm25_char_count": metadata.get("bm25_char_count", 0),
        "embedding_char_count": metadata.get("embedding_char_count", 0),
        "display_char_count": metadata.get("display_char_count", 0),
        "preserved_element_count": metadata.get("preserved_element_count", 0),
        "noise_score_before": metadata.get("noise_score_before", 0),
        "noise_score_after": metadata.get("noise_score_after", 0),
        "sentence_boundary_break_before": metadata.get("sentence_boundary_break_before", 0),
        "sentence_boundary_break_after": metadata.get("sentence_boundary_break_after", 0),
    }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    ensure_parent(path)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = sorted({key for row in rows for key in row})
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def build_preserved_inventory(sections_jsonl: Path, output_csv: Path, *, limit: int = 500) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for section in read_jsonl(sections_jsonl):
        for raw_index, raw_line in enumerate(str(section.get("text") or "").splitlines()):
            line = normalize_line(raw_line)
            case_type = detect_case_type(line)
            if case_type in {"body", "empty", "page_number", "provider_or_link"}:
                continue
            rows.append(
                {
                    "doc_id": section.get("doc_id", ""),
                    "section_id": section.get("section_id", ""),
                    "section_type": section.get("section_type", ""),
                    "page_start": section.get("page_start", ""),
                    "page_end": section.get("page_end", ""),
                    "raw_line_index": raw_index,
                    "case_type": case_type,
                    "raw_line": line,
                    "decision": "preserve_text",
                    "reason": "candidate_information_anchor",
                }
            )
            if len(rows) >= limit:
                write_csv(output_csv, rows)
                return rows
    write_csv(output_csv, rows)
    return rows


def build_reconstructed_documents_and_sections(
    documents_jsonl: Path,
    sections_jsonl: Path,
    output_dir: Path,
    *,
    profile: ReconstructionProfile,
) -> dict[str, Path]:
    docs_out = output_dir / "documents.jsonl"
    sections_out = output_dir / "sections.jsonl"
    report_out = output_dir / "reconstruction_report.csv"
    report_rows: list[dict[str, Any]] = []

    docs = []
    for row in read_jsonl(documents_jsonl):
        raw_text = str(row.get("content") or "")
        reconstructed = reconstruct_text(raw_text, profile=profile)
        updated = dict(row)
        updated.update(
            {
                "content": reconstructed["content"],
                "bm25_text": reconstructed["bm25_text"],
                "embedding_text": reconstructed["embedding_text"],
                "display_text": reconstructed["display_text"],
                "preserved_elements": reconstructed["preserved_elements"],
                "alignment_map": reconstructed["alignment_map"],
            }
        )
        updated["metadata"] = reconstruction_metadata(
            row,
            profile=profile,
            raw_text=raw_text,
            reconstructed=reconstructed,
        )
        docs.append(updated)
        report_rows.append(report_row("document", str(row.get("doc_id", "")), updated["metadata"]))

    sections = []
    for row in read_jsonl(sections_jsonl):
        raw_text = str(row.get("text") or "")
        reconstructed = reconstruct_text(raw_text, profile=profile)
        if not reconstructed["content"].strip():
            continue
        updated = dict(row)
        updated.update(
            {
                "raw_text": raw_text,
                "text": reconstructed["content"],
                "bm25_text": reconstructed["bm25_text"],
                "embedding_text": reconstructed["embedding_text"],
                "display_text": reconstructed["display_text"],
                "preserved_elements": reconstructed["preserved_elements"],
                "alignment_map": reconstructed["alignment_map"],
            }
        )
        updated["metadata"] = reconstruction_metadata(
            row,
            profile=profile,
            raw_text=raw_text,
            reconstructed=reconstructed,
        )
        sections.append(updated)
        report_rows.append(report_row("section", str(row.get("section_id", "")), updated["metadata"]))

    write_jsonl(docs_out, docs)
    write_jsonl(sections_out, sections)
    write_csv(report_out, report_rows)
    return {"documents": docs_out, "sections": sections_out, "report": report_out}


def validate_profiles(values: list[str] | None) -> list[ReconstructionProfile]:
    if not values:
        return list(PROFILES)
    valid = set(PROFILES)
    profiles: list[ReconstructionProfile] = []
    for value in values:
        for item in value.split(","):
            item = item.strip()
            if not item:
                continue
            if item not in valid:
                raise typer.BadParameter(f"Unknown reconstruction profile: {item}")
            profiles.append(cast(ReconstructionProfile, item))
    return profiles


@app.command("inventory")
def inventory_command(
    sections_jsonl: Path | None = None,
    output_csv: Path | None = None,
    limit: int = 500,
) -> None:
    sections_jsonl = sections_jsonl or default_pilot_processed_path("sections.jsonl")
    output_csv = output_csv or default_pilot_eval_path(
        "reconstruction/preserved_case_inventory.csv"
    )
    rows = build_preserved_inventory(sections_jsonl, output_csv, limit=limit)
    typer.echo(f"Wrote {len(rows)} preserved case rows to {output_csv}")


@app.command("build")
def build_command(
    documents_jsonl: Path | None = None,
    sections_jsonl: Path | None = None,
    output_root: Path | None = None,
    profile: list[str] | None = typer.Option(None, "--profile"),
) -> None:
    documents_jsonl = documents_jsonl or default_pilot_processed_path("documents_normalized.jsonl")
    sections_jsonl = sections_jsonl or default_pilot_processed_path("sections.jsonl")
    output_root = output_root or default_pilot_processed_path("reconstructed")
    for item in validate_profiles(profile):
        outputs = build_reconstructed_documents_and_sections(
            documents_jsonl,
            sections_jsonl,
            output_root / item,
            profile=item,
        )
        typer.echo(f"Wrote {item}: {outputs['documents']}, {outputs['sections']}")


def summarize_report(report_csv: Path) -> dict[str, Any]:
    rows = []
    with report_csv.open(encoding="utf-8-sig") as file:
        rows = list(csv.DictReader(file))
    if not rows:
        return {}

    def avg(key: str) -> float:
        values = [float(row.get(key) or 0) for row in rows]
        return round(mean(values), 6) if values else 0.0

    return {
        "profile": rows[0].get("profile", ""),
        "rows": len(rows),
        "avg_noise_before": avg("noise_score_before"),
        "avg_noise_after": avg("noise_score_after"),
        "avg_sentence_break_before": avg("sentence_boundary_break_before"),
        "avg_sentence_break_after": avg("sentence_boundary_break_after"),
        "preserved_elements": sum(int(float(row.get("preserved_element_count") or 0)) for row in rows),
    }


@app.command("summarize")
def summarize_command(
    input_root: Path | None = None,
    output_csv: Path | None = None,
) -> None:
    input_root = input_root or default_pilot_processed_path("reconstructed")
    output_csv = output_csv or default_pilot_eval_path("reconstruction/reconstruction_quality_summary.csv")
    rows = []
    for profile_dir in sorted(path for path in input_root.iterdir() if path.is_dir()):
        report = profile_dir / "reconstruction_report.csv"
        if report.exists():
            rows.append(summarize_report(report))
    write_csv(output_csv, rows)
    typer.echo(f"Wrote {len(rows)} reconstruction summaries to {output_csv}")


def main() -> None:
    app()
