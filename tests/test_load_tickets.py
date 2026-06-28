from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from koreanops_rag.ingestion.load_tickets import iter_tickets


def test_iter_tickets_streams_rows_from_csv(tmp_path: Path):
    csv_path = tmp_path / "tickets.csv"
    csv_path.write_text(
        "id,subject,description,resolution,priority\n"
        "1,Login fails,User cannot login,Reset password,high\n"
        "2,Payment timeout,API timeout,Increase pool,medium\n",
        encoding="utf-8",
    )
    mapping = {
        "ticket_id": "id",
        "subject": "subject",
        "description": "description",
        "resolution": "resolution",
        "priority": "priority",
    }

    rows = iter_tickets(csv_path, "sample", mapping, limit=1, chunksize=1)

    assert isinstance(rows, Iterator)
    tickets = list(rows)
    assert len(tickets) == 1
    assert tickets[0].ticket_id == "1"
    assert tickets[0].priority == "high"
