from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

Priority = Literal["low", "medium", "high", "critical", "unknown"]
TicketType = Literal["incident", "request", "problem", "question", "unknown"]
TicketStatus = Literal["open", "closed", "resolved", "unknown"]
SourceType = Literal["ticket", "log", "office_document"]
Severity = Literal["info", "warning", "error", "alert", "unknown"]


class Ticket(BaseModel):
    ticket_id: str
    source_dataset: str
    created_at: datetime | None = None
    ticket_type: TicketType = "unknown"
    priority: Priority = "unknown"
    queue: str = ""
    business_type: str = ""
    subject: str = ""
    description: str = ""
    resolution: str = ""
    tags: list[str] = Field(default_factory=list)
    status: TicketStatus = "unknown"
    raw_text: str = ""


class LogRecord(BaseModel):
    log_id: str
    source_dataset: str
    timestamp: datetime | None = None
    system: str = "unknown"
    severity: Severity = "unknown"
    component: str = ""
    message: str
    is_anomaly: bool | None = None
    template: str = ""
    raw_log: str = ""


class PageBlock(BaseModel):
    block_id: str
    page_num: int
    bbox: tuple[float, float, float, float]
    text: str
    raw_text: str = ""
    block_type: str = "text"
    font_size: float = 0.0
    is_heading: bool = False
    reading_order: int = 0


class OfficeDocument(BaseModel):
    doc_id: str
    split: Literal["training", "validation"]
    document_type: str
    title: str = ""
    publisher: str = ""
    source_archive: str
    source_member: str
    page_count: int = 0
    file_size: int = 0
    text_layer_pages: int = 0
    is_valid: bool = True
    error: str = ""


class GoldenQuestion(BaseModel):
    question_id: str
    question: str
    reference_answer: str
    gold_doc_ids: list[str]
    gold_pages: list[int]
    evidence_text: str
    question_type: str
    lexical_overlap: float
    hard_negative_doc_ids: list[str] = Field(default_factory=list)
    review_status: Literal["pending", "approved", "rejected", "revised"] = "pending"
    source_type: Literal["office_document"] = "office_document"


class RagDocument(BaseModel):
    doc_id: str
    source_type: SourceType
    title: str
    content: str
    embedding_text: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class SearchResult(BaseModel):
    doc_id: str
    score: float
    rank: int
    title: str = ""
    content: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    source_scores: dict[str, float] = Field(default_factory=dict)
