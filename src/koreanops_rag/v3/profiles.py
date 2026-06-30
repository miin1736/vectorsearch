from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

ProfileKind = Literal["chunking", "retriever", "reranker", "evaluation"]


class ExperimentProfile(BaseModel):
    name: str
    kind: ProfileKind
    family: str
    implementation: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    description: str = ""


def _profile(
    name: str,
    kind: ProfileKind,
    family: str,
    implementation: str,
    **parameters: Any,
) -> ExperimentProfile:
    return ExperimentProfile(
        name=name,
        kind=kind,
        family=family,
        implementation=implementation,
        parameters=parameters,
    )


CHUNKING_PROFILES: dict[str, ExperimentProfile] = {
    "fixed_512_overlap_64": _profile(
        "fixed_512_overlap_64",
        "chunking",
        "fixed",
        "token_window",
        token_budget=512,
        overlap=64,
        tokenizer="regex_baseline",
    ),
    "page_then_tokenizer_subchunk": _profile(
        "page_then_tokenizer_subchunk",
        "chunking",
        "page",
        "page_with_token_subchunks",
        token_budget=512,
        overlap=64,
        tokenizer="embedding_model",
    ),
    "paper_section_max_480_e5_tokens": _profile(
        "paper_section_max_480_e5_tokens",
        "chunking",
        "section",
        "paper_section_pack",
        max_tokens=480,
        tokenizer="intfloat/multilingual-e5-small",
    ),
    "e5_tokenizer_512_overlap_64": _profile(
        "e5_tokenizer_512_overlap_64",
        "chunking",
        "fixed",
        "token_window",
        token_budget=512,
        overlap=64,
        tokenizer="intfloat/multilingual-e5-small",
    ),
    "audit_only": _profile(
        "audit_only",
        "chunking",
        "audit",
        "token_length_distribution",
        tokenizer="intfloat/multilingual-e5-small",
    ),
    "sentence_96_192_e5_tokens": _profile(
        "sentence_96_192_e5_tokens",
        "chunking",
        "sentence",
        "sentence_pack",
        min_tokens=96,
        max_tokens=192,
        tokenizer="intfloat/multilingual-e5-small",
    ),
    "passage_320_384_e5_tokens": _profile(
        "passage_320_384_e5_tokens",
        "chunking",
        "passage",
        "paragraph_pack",
        min_tokens=320,
        max_tokens=384,
        tokenizer="intfloat/multilingual-e5-small",
    ),
    "sentence_passage_section_tree": _profile(
        "sentence_passage_section_tree",
        "chunking",
        "hierarchical",
        "multi_granularity_tree",
        levels=["sentence", "passage", "section"],
        tokenizer="intfloat/multilingual-e5-small",
    ),
    "child_passage_parent_section": _profile(
        "child_passage_parent_section",
        "chunking",
        "parent_child",
        "child_passage_parent_section",
        child_tokens=384,
        parent_type="section",
        tokenizer="intfloat/multilingual-e5-small",
    ),
    "section_graph_edges": _profile(
        "section_graph_edges",
        "chunking",
        "graph",
        "section_edge_builder",
        edge_types=[
            "parent",
            "adjacent",
            "section_transition",
            "citation_or_keyword_related",
            "same_topic_related",
        ],
    ),
    "best_available_from_smoke": _profile(
        "best_available_from_smoke",
        "chunking",
        "selection",
        "selected_smoke_winner",
    ),
    "best_pilot": _profile(
        "best_pilot",
        "chunking",
        "selection",
        "selected_pilot_winner",
    ),
    "not_applicable": _profile(
        "not_applicable",
        "chunking",
        "none",
        "no_chunking",
    ),
}


RETRIEVER_PROFILES: dict[str, ExperimentProfile] = {
    "dense_vector": _profile("dense_vector", "retriever", "dense", "qdrant_vector"),
    "none": _profile("none", "retriever", "none", "no_retrieval"),
    "hierarchical_dense": _profile(
        "hierarchical_dense",
        "retriever",
        "hierarchical",
        "dense_child_then_parent_aggregate",
    ),
    "child_dense_parent_context": _profile(
        "child_dense_parent_context",
        "retriever",
        "parent_child",
        "dense_child_parent_context",
    ),
    "rrf_seed_candidates": _profile(
        "rrf_seed_candidates",
        "retriever",
        "hybrid",
        "bm25_dense_rrf",
        candidate_k=100,
    ),
    "bm25_dense_rrf": _profile(
        "bm25_dense_rrf",
        "retriever",
        "hybrid",
        "bm25_dense_rrf",
        candidate_k=100,
        rrf_k=60,
    ),
    "bm25_dense_weighted": _profile(
        "bm25_dense_weighted",
        "retriever",
        "hybrid",
        "bm25_dense_weighted",
        bm25_weight=2.0,
        vector_weight=1.0,
    ),
    "rrf_top_100": _profile(
        "rrf_top_100",
        "retriever",
        "hybrid",
        "bm25_dense_rrf",
        candidate_k=100,
    ),
    "adaptive_k_score_tail": _profile(
        "adaptive_k_score_tail",
        "retriever",
        "adaptive",
        "score_tail_adaptive_k",
        min_k=3,
        max_k=20,
    ),
    "topic_keyword_soft_boost": _profile(
        "topic_keyword_soft_boost",
        "retriever",
        "domain_scope",
        "metadata_soft_boost",
        fields=["research_field", "paper_topic", "keyword", "publication_year"],
    ),
    "retry_on_low_evidence_sufficiency": _profile(
        "retry_on_low_evidence_sufficiency",
        "retriever",
        "corrective",
        "single_retry_query_expansion",
    ),
    "hnsw_parameter_grid": _profile(
        "hnsw_parameter_grid",
        "retriever",
        "ann",
        "qdrant_hnsw_grid",
    ),
    "best_pilot": _profile(
        "best_pilot",
        "retriever",
        "selection",
        "selected_pilot_winner",
    ),
    "trainable_dense_retriever": _profile(
        "trainable_dense_retriever",
        "retriever",
        "deferred",
        "trainable_dense_retriever",
    ),
    "compressed_embedding_index": _profile(
        "compressed_embedding_index",
        "retriever",
        "deferred",
        "compressed_embedding_index",
    ),
    "multimodal": _profile(
        "multimodal",
        "retriever",
        "deferred",
        "multimodal_retrieval",
    ),
}


RERANKER_PROFILES: dict[str, ExperimentProfile] = {
    "none": _profile("none", "reranker", "none", "no_reranker"),
    "parent_score_aggregation": _profile(
        "parent_score_aggregation",
        "reranker",
        "parent_child",
        "parent_score_aggregation",
    ),
    "one_hop_section_graph": _profile(
        "one_hop_section_graph",
        "reranker",
        "graph",
        "one_hop_graph_rerank",
    ),
    "cpu_cross_encoder_top_50": _profile(
        "cpu_cross_encoder_top_50",
        "reranker",
        "cross_encoder",
        "sentence_transformers_cross_encoder",
        top_k=50,
        device="cpu",
    ),
    "optional_best_pilot": _profile(
        "optional_best_pilot",
        "reranker",
        "selection",
        "optional_selected_pilot_winner",
    ),
    "late_interaction_top_50_subset": _profile(
        "late_interaction_top_50_subset",
        "reranker",
        "late_interaction",
        "late_interaction_subset",
        top_k=50,
    ),
    "best_pilot": _profile(
        "best_pilot",
        "reranker",
        "selection",
        "selected_pilot_winner",
    ),
    "multimodal": _profile(
        "multimodal",
        "reranker",
        "deferred",
        "multimodal_reranker",
    ),
}


EVALUATION_PROFILES: dict[str, ExperimentProfile] = {
    "retrieval_core": _profile(
        "retrieval_core",
        "evaluation",
        "retrieval",
        "core_retrieval_metrics",
        metrics=[
            "recall_at_5",
            "recall_at_10",
            "mrr",
            "ndcg_at_10",
            "latency_p50_p95",
        ],
    ),
    "truncation_and_retrieval": _profile(
        "truncation_and_retrieval",
        "evaluation",
        "tokenizer",
        "tokenizer_length_plus_retrieval",
    ),
    "tokenizer_length_distribution": _profile(
        "tokenizer_length_distribution",
        "evaluation",
        "tokenizer",
        "token_length_distribution",
    ),
    "retrieval_context_efficiency": _profile(
        "retrieval_context_efficiency",
        "evaluation",
        "retrieval",
        "context_efficiency_metrics",
    ),
    "reranker_cost_quality": _profile(
        "reranker_cost_quality",
        "evaluation",
        "reranker",
        "quality_latency_cost_curve",
    ),
    "context_efficiency": _profile(
        "context_efficiency",
        "evaluation",
        "retrieval",
        "context_efficiency_metrics",
    ),
    "hard_negative_rejection": _profile(
        "hard_negative_rejection",
        "evaluation",
        "retrieval",
        "hard_negative_rejection_metrics",
    ),
    "rag_retrieval_recovery": _profile(
        "rag_retrieval_recovery",
        "evaluation",
        "rag",
        "corrective_retrieval_recovery",
    ),
    "quality_latency": _profile(
        "quality_latency",
        "evaluation",
        "ann",
        "quality_latency_tradeoff",
    ),
    "rag_reliability": _profile(
        "rag_reliability",
        "evaluation",
        "rag",
        "clean_misleading_mixed_reliability",
    ),
    "deferred": _profile(
        "deferred",
        "evaluation",
        "deferred",
        "not_scheduled",
    ),
}


PROFILE_GROUPS: dict[ProfileKind, dict[str, ExperimentProfile]] = {
    "chunking": CHUNKING_PROFILES,
    "retriever": RETRIEVER_PROFILES,
    "reranker": RERANKER_PROFILES,
    "evaluation": EVALUATION_PROFILES,
}


def get_profile(kind: ProfileKind, name: str) -> ExperimentProfile:
    try:
        return PROFILE_GROUPS[kind][name]
    except KeyError as exc:
        raise KeyError(f"Unknown {kind} profile: {name}") from exc


def validate_profile_references(
    *,
    chunking_profile: str,
    retriever_profile: str,
    reranker_profile: str,
    evaluation_profile: str,
) -> None:
    get_profile("chunking", chunking_profile)
    get_profile("retriever", retriever_profile)
    get_profile("reranker", reranker_profile)
    get_profile("evaluation", evaluation_profile)
