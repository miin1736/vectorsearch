from koreanops_rag.documents.contextual_chunks import document_to_contextual_chunks


def test_contextual_ticket_chunks_repeat_parent_context():
    doc = {
        "doc_id": "ticket_1",
        "source_type": "ticket",
        "title": "Payment timeout",
        "content": "Subject: Payment timeout Description: API timed out Resolution: Increase DB pool",
        "metadata": {"priority": "high", "ticket_type": "incident", "queue": "payment"},
    }

    chunks = list(document_to_contextual_chunks(doc))

    assert chunks[0]["metadata"]["parent_doc_id"] == "ticket_1"
    assert chunks[0]["metadata"]["chunking_strategy"] == "contextual"
    assert "Ticket context:" in chunks[0]["embedding_text"]
    assert "priority: high" in chunks[0]["embedding_text"]
    assert "Current field: subject" in chunks[0]["embedding_text"]


def test_contextual_log_chunk_keeps_original_doc_id():
    doc = {
        "doc_id": "log_1",
        "source_type": "log",
        "title": "HDFS error log",
        "content": "Block missing",
        "metadata": {"severity": "error"},
    }

    chunks = list(document_to_contextual_chunks(doc))

    assert len(chunks) == 1
    assert chunks[0]["doc_id"] == "log_1"
    assert chunks[0]["metadata"]["chunking_strategy"] == "contextual"
