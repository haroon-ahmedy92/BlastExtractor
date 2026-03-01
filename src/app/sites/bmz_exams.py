"""Zanzibar BMZ exams adapter."""

from __future__ import annotations

import re
from urllib.parse import urljoin

from app.db.exam_results import upsert_exam_result
from app.models.common import (
    ContentType,
    UpsertResult,
    compute_content_hash,
    normalize_whitespace,
    validate_http_url,
)
from app.models.exams import ExamRecord, ExamStub
from app.sites.browser_support import BrowserSiteAdapter
from app.sites.parsing_support import extract_table_data, parse_html_document, split_centre_label
from app.sites.registry import register_adapter

BMZ_SCHOOLS_URL = "https://matokeo.bmz.go.tz/schools/"
EXAM_TYPE_MAP = {
    "FII": "Form Two",
    "STD7": "Std Seven",
    "STD6": "Std Six",
    "STD4": "Darasa la Nne",
}


def parse_bmz_exam_links(
    page_html: str,
    *,
    base_url: str = BMZ_SCHOOLS_URL,
) -> list[tuple[int | None, str, str]]:
    """Extract year and exam links from the BMZ landing page."""

    tree = parse_html_document(page_html)
    links: list[tuple[int | None, str, str]] = []
    for anchor in tree.xpath("//a[@href[contains(.,'index.html')]]"):
        href = normalize_whitespace(anchor.get("href", ""))
        text = normalize_whitespace(anchor.text_content())
        match = re.search(r"([A-Z0-9]+)\((\d{4})\)/index\.html", href)
        if not match:
            continue
        exam_code, year_text = match.groups()
        links.append(
            (int(year_text), EXAM_TYPE_MAP.get(exam_code, text), urljoin(base_url, href))
        )
    return links


def parse_bmz_centre_stubs(
    page_html: str,
    *,
    year: int | None,
    exam_type: str,
    base_url: str,
) -> list[ExamStub]:
    """Extract centre links from a BMZ exam page."""

    tree = parse_html_document(page_html)
    stubs: list[ExamStub] = []
    seen_urls: set[str] = set()
    for anchor in tree.xpath("//a[@href]"):
        href = normalize_whitespace(anchor.get("href", ""))
        if not re.search(r"[A-Z]{1,4}\d{3,5}\.html$", href):
            continue
        absolute_url = urljoin(base_url, href)
        if absolute_url in seen_urls:
            continue
        label = normalize_whitespace(anchor.text_content())
        centre_code, centre_name = split_centre_label(label)
        try:
            stubs.append(
                ExamStub(
                    url=validate_http_url(absolute_url),
                    title=label,
                    year=year,
                    exam_type=exam_type,
                    centre_code=centre_code,
                    centre_name=centre_name,
                )
            )
            seen_urls.add(absolute_url)
        except Exception:
            continue
    return stubs


def parse_exam_results_record(page_html: str, *, stub: ExamStub, source: str) -> ExamRecord:
    """Parse a BMZ or NECTA centre page into a normalized exam record."""

    tree = parse_html_document(page_html)
    page_title = (
        normalize_whitespace("".join(tree.xpath("//table[2]//tr[1]//text()"))) or stub.title
    )
    centre_code = stub.centre_code
    centre_name = stub.centre_name
    if page_title and not centre_code and "(" in page_title:
        match = re.search(r"\(([^)]+)\)", page_title)
        if match:
            centre_code = normalize_whitespace(match.group(1))
            centre_name = normalize_whitespace(page_title.replace(match.group(0), ""))

    tables = [
        extract_table_data(table)
        for table in tree.xpath("//table")
        if table.xpath(".//tr[td]") or table.xpath(".//tr[th]")
    ]
    results_json = {"title": page_title, "tables": tables}
    hash_payload = {
        "source_url": str(stub.url),
        "year": stub.year,
        "exam_type": stub.exam_type,
        "centre_code": centre_code,
        "centre_name": centre_name,
        "results_json": results_json,
    }
    return ExamRecord(
        source=source,
        source_url=validate_http_url(str(stub.url)),
        title=page_title,
        year=stub.year,
        exam_type=stub.exam_type,
        centre_code=centre_code,
        centre_name=centre_name,
        results_json=results_json,
        content_hash=compute_content_hash(hash_payload),
    )


class ZanzibarBMZExamAdapter(BrowserSiteAdapter[ExamStub, ExamRecord]):
    """Exam adapter for Zanzibar BMZ school results."""

    site_name = "bmz_exams"
    content_type = ContentType.EXAMS

    async def discover(self) -> list[ExamStub]:
        """Discover BMZ centre result pages from the schools landing page."""

        index_html = await self._fetch_page_html(BMZ_SCHOOLS_URL, wait_selector="a[href]")
        exam_links = parse_bmz_exam_links(index_html, base_url=BMZ_SCHOOLS_URL)
        stubs: list[ExamStub] = []
        for year, exam_type, exam_url in exam_links:
            exam_html = await self._fetch_page_html(exam_url, wait_selector="a[href]")
            stubs.extend(
                parse_bmz_centre_stubs(
                    exam_html,
                    year=year,
                    exam_type=exam_type,
                    base_url=exam_url,
                )
            )
        return stubs

    async def fetch_details(self, stub: ExamStub) -> ExamRecord:
        """Fetch and parse one BMZ centre result page."""

        page_html = await self._fetch_page_html(str(stub.url), wait_selector="table")
        return parse_exam_results_record(page_html, stub=stub, source=self.site_name)

    async def upsert(self, record: ExamRecord) -> UpsertResult:
        """Persist one BMZ exam result row."""

        async with self.session_factory() as db_session:
            _, upsert_result = await upsert_exam_result(db_session, record)
            await db_session.commit()
            return upsert_result


register_adapter("bmz_exams", ZanzibarBMZExamAdapter)
