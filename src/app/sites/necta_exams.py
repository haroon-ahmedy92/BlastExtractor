"""NECTA exam adapter with graceful upstream discovery failures."""

from __future__ import annotations

import re
from urllib.parse import urljoin

from app.db.exam_results import upsert_exam_result
from app.models.common import ContentType, UpsertResult, normalize_whitespace, validate_http_url
from app.models.exams import ExamRecord, ExamStub
from app.sites.bmz_exams import parse_exam_results_record
from app.sites.browser_support import BlockedNavigationError, BrowserSiteAdapter
from app.sites.parsing_support import parse_html_document, split_centre_label
from app.sites.registry import register_adapter

NECTA_VIEW_URLS = {
    "csee": "https://www.necta.go.tz/results/view/csee",
    "acsee": "https://www.necta.go.tz/results/view/acsee",
    "psle": "https://www.necta.go.tz/results/view/psle",
    "ftna": "https://www.necta.go.tz/results/view/ftna",
}


def parse_necta_results_index_links(page_html: str) -> list[tuple[int | None, str]]:
    """Extract year and results-index URLs from a NECTA view page."""

    tree = parse_html_document(page_html)
    links: list[tuple[int | None, str]] = []
    for anchor in tree.xpath("//a[@href]"):
        href = normalize_whitespace(anchor.get("href", ""))
        match = re.search(r"/results/(\d{4})/([a-z0-9_-]+)/index\.htm$", href, re.IGNORECASE)
        if not match:
            continue
        year_text, _ = match.groups()
        links.append((int(year_text), href))
    return links


def parse_necta_centre_stubs(
    page_html: str,
    *,
    year: int | None,
    exam_type: str,
    base_url: str,
) -> list[ExamStub]:
    """Extract centre links from a NECTA result index page."""

    tree = parse_html_document(page_html)
    stubs: list[ExamStub] = []
    seen_urls: set[str] = set()
    for anchor in tree.xpath("//a[@href]"):
        href = normalize_whitespace(anchor.get("href", ""))
        if not href.lower().endswith((".htm", ".html")) or "index." in href.lower():
            continue
        label = normalize_whitespace(anchor.text_content())
        if not label or label.lower() in {"back", "next"}:
            continue
        absolute_url = urljoin(base_url, href)
        if absolute_url in seen_urls:
            continue
        centre_code, centre_name = split_centre_label(label)
        try:
            stubs.append(
                ExamStub(
                    url=validate_http_url(absolute_url),
                    title=label,
                    year=year,
                    exam_type=exam_type.upper(),
                    centre_code=centre_code,
                    centre_name=centre_name,
                )
            )
            seen_urls.add(absolute_url)
        except Exception:
            continue
    return stubs


class NectaExamAdapter(BrowserSiteAdapter[ExamStub, ExamRecord]):
    """Exam adapter for NECTA result view pages and centre result pages."""

    site_name = "necta_exams"
    content_type = ContentType.EXAMS

    async def discover(self) -> list[ExamStub]:
        """Discover NECTA centre result pages from exam view pages.

        The upstream ``necta.go.tz`` view pages can block or reset requests.
        When that happens, the adapter logs the evidence and continues without
        crashing the whole run.
        """

        stubs: list[ExamStub] = []
        for exam_type, view_url in NECTA_VIEW_URLS.items():
            try:
                _, view_html = await self._fetch_page(view_url, wait_selector="a[href]")
            except BlockedNavigationError as error:
                self._log_blocked(
                    url=error.url,
                    status_code=error.status_code,
                    detail=error.detail,
                )
                continue
            except Exception as error:
                self._log_blocked(url=view_url, status_code=None, detail=str(error))
                continue
            results_links = parse_necta_results_index_links(view_html)
            for year, index_url in results_links:
                try:
                    index_html = await self._fetch_page_html(index_url, wait_selector="a[href]")
                except Exception as error:
                    self._log_blocked(url=index_url, status_code=None, detail=str(error))
                    continue
                stubs.extend(
                    parse_necta_centre_stubs(
                        index_html,
                        year=year,
                        exam_type=exam_type,
                        base_url=index_url,
                    )
                )
        return stubs

    async def fetch_details(self, stub: ExamStub) -> ExamRecord:
        """Fetch and parse one NECTA centre result page."""

        page_html = await self._fetch_page_html(str(stub.url), wait_selector="table")
        return parse_exam_results_record(page_html, stub=stub, source=self.site_name)

    async def upsert(self, record: ExamRecord) -> UpsertResult:
        """Persist one NECTA exam result row."""

        async with self.session_factory() as db_session:
            _, upsert_result = await upsert_exam_result(db_session, record)
            await db_session.commit()
            return upsert_result


register_adapter("necta_exams", NectaExamAdapter)
