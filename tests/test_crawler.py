from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from app.crawler.crawl_ajira import export_jsonl
from app.models.listing_detail import ListingDetail


def test_export_jsonl_writes_one_json_document_per_line(tmp_path: Path) -> None:
    target = tmp_path / "jobs.jsonl"
    items = [
        ListingDetail(
            title="Data Engineer",
            institution="Public Data Agency",
            number_of_posts=2,
            deadline_date=date(2026, 3, 10),
            details_url="https://example.com/jobs/1",
            description_text="Build reliable data pipelines",
            description_html="<p>Build reliable data pipelines</p>",
            attachments=None,
            extra_metadata=None,
            structured_fields={"remuneration": "TGS B"},
            content_hash="hash-1",
        )
    ]

    export_jsonl(str(target), items)

    lines = target.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["title"] == "Data Engineer"
    assert payload["structured_fields"]["remuneration"] == "TGS B"
