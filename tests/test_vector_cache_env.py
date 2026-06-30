from __future__ import annotations

from koreanops_rag.retrieval.vector_qdrant import ensure_model_cache_env


def test_ensure_model_cache_env_defaults_to_data_root(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("DATA_ROOT", str(tmp_path))
    for name in ["HF_HOME", "SENTENCE_TRANSFORMERS_HOME", "TORCH_HOME"]:
        monkeypatch.delenv(name, raising=False)

    ensure_model_cache_env()

    assert (tmp_path / "models" / "huggingface").is_dir()
    assert (tmp_path / "models" / "huggingface" / "sentence-transformers").is_dir()
    assert (tmp_path / "cache" / "torch").is_dir()
