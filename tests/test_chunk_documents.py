from koreanops_rag.documents.chunk_documents import document_to_field_chunks


def test_ticket_field_chunks_preserve_parent_doc_id():
    doc = {
        "doc_id": "ticket_1",
        "source_type": "ticket",
        "title": "Payment timeout",
        "content": "Subject: Payment timeout\nDescription: Card fails\nResolution: Retry later",
        "metadata": {"priority": "high"},
    }

    chunks = list(document_to_field_chunks(doc))

    assert [chunk["metadata"]["chunk_field"] for chunk in chunks] == [
        "subject",
        "description",
        "resolution",
    ]
    assert all(chunk["metadata"]["parent_doc_id"] == "ticket_1" for chunk in chunks)
    assert chunks[0]["doc_id"] == "ticket_1__chunk_00_subject"


def test_log_chunk_keeps_original_doc_id():
    doc = {
        "doc_id": "log_1",
        "source_type": "log",
        "title": "HDFS error log",
        "content": "Block missing",
        "metadata": {"severity": "error"},
    }

    chunks = list(document_to_field_chunks(doc))

    assert len(chunks) == 1
    assert chunks[0]["doc_id"] == "log_1"
    assert chunks[0]["metadata"]["parent_doc_id"] == "log_1"
