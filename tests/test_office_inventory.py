import zipfile
from pathlib import Path

from koreanops_rag.office.inventory import iter_inventory


def test_inventory_reads_pdf_members_without_extracting(tmp_path: Path):
    archive_path = (
        tmp_path
        / "Training"
        / "01.원천데이터"
        / "TS_01.보고서(설명형)_02.원천데이터(pdf).zip"
    )
    archive_path.parent.mkdir(parents=True)
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("/OC2_240805_TY1-1_0001.pdf", b"%PDF-test")

    rows = list(iter_inventory(tmp_path))

    assert len(rows) == 1
    assert rows[0].doc_id == "OC2_240805_TY1-1_0001"
    assert rows[0].split == "training"
    assert rows[0].document_type == "보고서(설명형)"


def test_inventory_can_filter_validation_split(tmp_path: Path):
    for split, prefix in (("Training", "TS"), ("Validation", "VS")):
        archive_path = (
            tmp_path
            / split
            / "01.원천데이터"
            / f"{prefix}_01.보고서_02.원천데이터(pdf).zip"
        )
        archive_path.parent.mkdir(parents=True)
        with zipfile.ZipFile(archive_path, "w") as archive:
            archive.writestr(f"/OC2_240805_TY1-1_{prefix}01.pdf", b"%PDF-test")

    rows = list(iter_inventory(tmp_path, split_filter="validation"))

    assert len(rows) == 1
    assert rows[0].split == "validation"


def test_inventory_can_stratify_by_document_type(tmp_path: Path):
    for type_index in range(2):
        archive_path = (
            tmp_path
            / "Validation"
            / "01.원천데이터"
            / f"VS_0{type_index + 1}.type{type_index}_02.원천데이터(pdf).zip"
        )
        archive_path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(archive_path, "w") as archive:
            for doc_index in range(3):
                archive.writestr(
                    f"/OC2_240805_TY{type_index}-{doc_index}_0001.pdf",
                    b"%PDF-test",
                )

    rows = list(
        iter_inventory(
            tmp_path,
            limit=4,
            split_filter="validation",
            stratified=True,
        )
    )

    assert [row.document_type for row in rows] == ["type0", "type1", "type0", "type1"]
