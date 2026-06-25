from pathlib import Path

import yaml

from koreanops_rag.config import load_config


V2_CONFIG_DIR = Path("experiments/ko_unstructured_v2/configs")
V2_STAGES = ["raw", "cleaned", "normalized", "contextual_chunks"]
PDF_STAGES = ["fixed", "page", "structure", "contextual", "oracle"]


def test_ko_unstructured_v2_configs_use_isolated_namespace():
    for stage in V2_STAGES:
        path = V2_CONFIG_DIR / f"{stage}.yaml"
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))

        assert raw["data_root"] == r"C:\vectorsearch-data\ko-unstructured"
        assert raw["qdrant"]["collection"] == f"ko_unstructured_{stage}"
        assert raw["opensearch"]["index"] == f"ko_unstructured_{stage}"


def test_explicit_config_data_root_wins_over_environment(monkeypatch):
    monkeypatch.setenv("DATA_ROOT", r"C:\vectorsearch-data")

    config = load_config(V2_CONFIG_DIR / "raw.yaml")

    assert config.data_root == Path(r"C:\vectorsearch-data\ko-unstructured")
    assert config.qdrant.collection == "ko_unstructured_raw"
    assert config.opensearch.index == "ko_unstructured_raw"


def test_office_pdf_configs_use_isolated_namespace():
    for stage in PDF_STAGES:
        path = V2_CONFIG_DIR / f"pdf_{stage}.yaml"
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))

        assert raw["data_root"] == r"C:\vectorsearch-data\ko-unstructured"
        assert raw["qdrant"]["collection"] == f"ko_unstructured_pdf_{stage}"
        assert raw["opensearch"]["index"] == f"ko_unstructured_pdf_{stage}"


def test_default_config_can_still_use_environment_data_root(monkeypatch, tmp_path: Path):
    config_path = tmp_path / "minimal.yaml"
    config_path.write_text("qdrant:\n  collection: demo\n", encoding="utf-8")
    monkeypatch.setenv("DATA_ROOT", r"C:\vectorsearch-data\override")

    config = load_config(config_path)

    assert config.data_root == Path(r"C:\vectorsearch-data\override")
