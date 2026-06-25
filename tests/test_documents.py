from koreanops_rag.documents.build_documents import log_to_document, ticket_to_document
from koreanops_rag.schemas import LogRecord, Ticket


def test_ticket_to_document_builds_content_and_metadata():
    ticket = Ticket(
        ticket_id="1842",
        source_dataset="sample",
        ticket_type="incident",
        priority="high",
        queue="payment",
        subject="Payment timeout",
        description="API timed out",
        resolution="Increase DB pool",
        tags=["payment", "db"],
        status="resolved",
    )

    doc = ticket_to_document(ticket)

    assert doc is not None
    assert doc.doc_id == "ticket_sample_1842"
    assert "Payment timeout" in doc.content
    assert "ticket subject: Payment timeout" in doc.embedding_text
    assert "priority: high" in doc.embedding_text
    assert doc.metadata["priority"] == "high"


def test_log_to_document_builds_log_metadata():
    log = LogRecord(
        log_id="abc",
        source_dataset="loghub_hdfs",
        system="hdfs",
        severity="error",
        message="Connection refused",
    )

    doc = log_to_document(log)

    assert doc is not None
    assert doc.doc_id == "log_loghub_hdfs_abc"
    assert doc.metadata["system"] == "hdfs"
    assert "log message: Connection refused" in doc.embedding_text
