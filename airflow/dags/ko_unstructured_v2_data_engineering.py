from __future__ import annotations

import os
from datetime import datetime

from airflow import DAG
from airflow.operators.bash import BashOperator


REPO = "/opt/koreanops-rag"
DATA_ROOT = os.getenv("DATA_ROOT", "C:/vectorsearch-data/ko-unstructured")
RAW = f"{DATA_ROOT}/raw"
PROCESSED = f"{DATA_ROOT}/processed"
FULL = f"{PROCESSED}/full"
EVAL = f"{DATA_ROOT}/eval/full"
CONFIG_PAGE = "experiments/ko_unstructured_v2/configs/pdf_page.yaml"
CONFIG_STRUCTURE = "experiments/ko_unstructured_v2/configs/pdf_structure.yaml"


def uv_command(command: str) -> str:
    return f"cd {REPO} && python -m pip install -q uv && uv run {command}"


default_args = {
    "owner": "koreanops-rag",
    "retries": 0,
}


with DAG(
    dag_id="office_pdf_etl",
    default_args=default_args,
    start_date=datetime(2026, 1, 1),
    schedule=None,
    catchup=False,
    tags=["ko_unstructured_v2", "data-engineering", "local-only"],
) as office_pdf_etl:
    inventory = BashOperator(
        task_id="inventory",
        bash_command=uv_command(
            "koreanops-office-inventory "
            f"{RAW} {PROCESSED}/office_manifest.jsonl"
        ),
    )
    parse = BashOperator(
        task_id="parse",
        bash_command=uv_command(
            "koreanops-office-parse "
            f"{RAW} {PROCESSED}/office_manifest.jsonl "
            f"{FULL}/pdf_pages_raw.jsonl "
            f"{FULL}/pdf_blocks_cleaned.jsonl "
            f"{FULL}/office_documents_normalized.jsonl"
        ),
    )
    build_chunks_page = BashOperator(
        task_id="build_chunks_page",
        bash_command=uv_command(
            "koreanops-office-build-chunks "
            f"{FULL}/office_documents_normalized.jsonl "
            f"{FULL}/chunks_page.jsonl page "
            f"--pages-jsonl {FULL}/pdf_pages_raw.jsonl"
        ),
    )
    build_chunks_structure = BashOperator(
        task_id="build_chunks_structure",
        bash_command=uv_command(
            "koreanops-office-build-chunks "
            f"{FULL}/office_documents_normalized.jsonl "
            f"{FULL}/chunks_structure.jsonl structure "
            f"--blocks-jsonl {FULL}/pdf_blocks_cleaned.jsonl "
            f"--pages-jsonl {FULL}/pdf_pages_raw.jsonl"
        ),
    )
    spark_jsonl_to_parquet = BashOperator(
        task_id="spark_jsonl_to_parquet",
        bash_command=uv_command(
            "koreanops-office-jsonl-to-parquet "
            f"--data-root {DATA_ROOT} "
            "--spark-master spark://spark-master:7077"
        ),
    )
    run_data_quality = BashOperator(
        task_id="run_data_quality",
        bash_command=uv_command(
            "koreanops-office-data-quality "
            f"--data-root {DATA_ROOT}"
        ),
    )
    build_mart = BashOperator(
        task_id="build_mart",
        bash_command=uv_command(
            "koreanops-office-build-mart "
            f"--data-root {DATA_ROOT} "
            "--spark-master spark://spark-master:7077"
        ),
    )

    (
        inventory
        >> parse
        >> build_chunks_page
        >> build_chunks_structure
        >> spark_jsonl_to_parquet
        >> run_data_quality
        >> build_mart
    )


with DAG(
    dag_id="retrieval_evaluation",
    default_args=default_args,
    start_date=datetime(2026, 1, 1),
    schedule=None,
    catchup=False,
    tags=["ko_unstructured_v2", "retrieval", "local-only"],
) as retrieval_evaluation:
    index_qdrant = BashOperator(
        task_id="index_qdrant",
        bash_command=uv_command(
            "koreanops-index-qdrant "
            f"{FULL}/chunks_structure.jsonl "
            f"--config-path {CONFIG_STRUCTURE} --resume"
        ),
    )
    index_opensearch = BashOperator(
        task_id="index_opensearch",
        bash_command=uv_command(
            "koreanops-index-opensearch "
            f"{FULL}/chunks_structure.jsonl "
            f"--config-path {CONFIG_STRUCTURE}"
        ),
    )
    run_retrieval_eval = BashOperator(
        task_id="run_retrieval_eval",
        bash_command=uv_command(
            "koreanops-office-eval-retrieval "
            f"{EVAL}/golden_questions_reviewed.jsonl "
            f"{EVAL}/retrieval_structure_summary.csv "
            f"{EVAL}/retrieval_structure_details.csv "
            f"{CONFIG_STRUCTURE}"
        ),
    )
    run_rag_eval = BashOperator(
        task_id="run_rag_eval",
        bash_command=uv_command(
            "koreanops-office-eval-rag "
            f"{EVAL}/golden_questions_reviewed.jsonl "
            f"{EVAL}/rag_structure_vector_200.csv "
            f"{CONFIG_STRUCTURE} "
            f"--summary-csv {EVAL}/rag_structure_vector_200_summary.csv "
            "--resume"
        ),
    )
    write_eval_mart = BashOperator(
        task_id="write_eval_mart",
        bash_command=uv_command(
            "koreanops-office-write-eval-mart "
            f"{EVAL}/retrieval_structure_summary.csv "
            f"--rag-summary-csv {EVAL}/rag_structure_vector_200_summary.csv "
            f"--data-root {DATA_ROOT} "
            "--spark-master spark://spark-master:7077"
        ),
    )

    [index_qdrant, index_opensearch] >> run_retrieval_eval >> run_rag_eval >> write_eval_mart
