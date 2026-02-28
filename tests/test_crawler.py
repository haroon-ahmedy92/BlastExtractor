from __future__ import annotations

import asyncio
import json
from pathlib import Path

from app.crawler.run import export_jsonl, run_site_once
from app.models.news import NewsRecord


def test_export_jsonl_writes_one_json_document_per_line(tmp_path: Path) -> None:
    target = tmp_path / "records.jsonl"
    records = [
        NewsRecord(
            source="news_stub",
            source_url="https://example.com/news/1",
            title="Headline",
            author="Author",
            published_at=None,
            body_text="Body",
            body_html="<p>Body</p>",
            tags_json=["news"],
            attachments_json=None,
            content_hash="hash-1",
        )
    ]

    export_jsonl(str(target), records)

    lines = target.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["title"] == "Headline"


def test_run_site_once_succeeds_for_stub_adapters() -> None:
    async def scenario() -> None:
        news_report = await run_site_once(site_name="news_stub", concurrency=2)
        exam_report = await run_site_once(site_name="exam_stub", concurrency=2)
        assert news_report.discovered == 0
        assert news_report.failed == 0
        assert exam_report.discovered == 0
        assert exam_report.failed == 0

    asyncio.run(scenario())
