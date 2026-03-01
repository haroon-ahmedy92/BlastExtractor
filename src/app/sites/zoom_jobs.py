"""Zoom Tanzania jobs adapter."""

from __future__ import annotations

from typing import Any

from lxml import html

from app.db.job_postings import upsert_job_posting
from app.models.common import (
    ContentType,
    UpsertResult,
    compute_content_hash,
    normalize_whitespace,
    validate_http_url,
)
from app.models.jobs import JobRecord, JobStub
from app.sites.browser_support import BrowserSiteAdapter
from app.sites.parsing_support import find_json_ld_by_type, normalize_url, parse_html_document
from app.sites.registry import register_adapter

ZOOM_JOBS_URL = "https://www.zoomtanzania.net/jobs/"


def parse_zoom_job_stubs(page_html: str, *, base_url: str = ZOOM_JOBS_URL) -> list[JobStub]:
    """Parse Zoom job cards from a listing page."""

    tree = parse_html_document(page_html)
    stubs: list[JobStub] = []
    seen_urls: set[str] = set()
    for item in tree.xpath("//div[contains(@class,'civi-jobs-item')]"):
        detail_href = normalize_whitespace(
            "".join(item.xpath(".//a[contains(@class,'civi-link-item')]/@href"))
        )
        if not detail_href:
            detail_href = normalize_whitespace("".join(item.xpath(".//h3//a/@href")))
        if not detail_href:
            continue
        absolute_url = normalize_url(base_url, detail_href)
        if absolute_url in seen_urls:
            continue
        title = normalize_whitespace(
            "".join(item.xpath(".//h3[contains(@class,'jobs-title')]//text()"))
        )
        company = normalize_whitespace(
            "".join(
                item.xpath(
                    ".//*[contains(@class,'info-company')]//a[contains(@class,'authour')]//text()"
                )
            )
        ) or None
        location = normalize_whitespace(
            "".join(item.xpath(".//a[contains(@class,'label-location')]//text()"))
        ).replace(" ", " ", 1) or None
        job_type = normalize_whitespace(
            "".join(item.xpath(".//a[contains(@class,'label-type')]//text()"))
        ) or None
        try:
            stubs.append(
                JobStub(
                    url=validate_http_url(absolute_url),
                    title=title,
                    institution=company,
                )
            )
            seen_urls.add(absolute_url)
        except Exception:
            continue
        _ = location
        _ = job_type
    return stubs


def parse_zoom_next_page(page_html: str, *, base_url: str = ZOOM_JOBS_URL) -> str | None:
    """Return the next page URL from a Zoom jobs listing page."""

    tree = parse_html_document(page_html)
    href = normalize_whitespace(
        "".join(
            tree.xpath(
                "//a[contains(@class,'next') or contains(@class,'page-numbers next')][1]/@href"
            )
        )
    )
    return normalize_url(base_url, href) if href else None


def parse_zoom_job_record(page_html: str, *, source_url: str) -> JobRecord:
    """Parse one Zoom job detail page into a normalized job record."""

    tree = parse_html_document(page_html)
    job_data = find_json_ld_by_type(page_html, "JobPosting") or {}
    title = normalize_whitespace(str(job_data.get("title", ""))) or normalize_whitespace(
        "".join(tree.xpath("//h1[1]//text()"))
    )
    company_info = job_data.get("hiringOrganization") or {}
    company = normalize_whitespace(str(company_info.get("name", ""))) or "Unknown"
    employment_type = job_data.get("employmentType")
    if isinstance(employment_type, list):
        employment_type = ", ".join(str(item) for item in employment_type)
    location = None
    address = ((job_data.get("jobLocation") or {}).get("address") or {})
    if isinstance(address, dict):
        location = normalize_whitespace(
            str(
                address.get("addressLocality")
                or address.get("addressRegion")
                or address.get("streetAddress")
                or ""
            )
        ) or None
    description_node = html.fromstring(f"<div>{job_data.get('description', '')}</div>")
    description_text = normalize_whitespace(description_node.text_content()) or None
    description_html = str(job_data.get("description") or "") or None
    skills = [
        normalize_whitespace(link.text_content())
        for link in tree.xpath("//a[contains(@href,'/jobs-skills/')]")
        if normalize_whitespace(link.text_content())
    ]
    categories = [
        normalize_whitespace(link.text_content())
        for link in tree.xpath("//a[contains(@href,'/jobs-categories/')]")
        if normalize_whitespace(link.text_content())
    ]
    apply_links = [
        normalize_whitespace(link.get("href", ""))
        for link in tree.xpath("//a[@href]")
        if "apply" in normalize_whitespace(link.text_content()).lower()
        or "apply" in normalize_whitespace(link.get("href", "")).lower()
    ]
    apply_links = [link for link in apply_links if link and not link.startswith("#")]
    metadata: dict[str, Any] = {
        "job_type": normalize_whitespace(str(employment_type or "")) or None,
        "skills": skills or None,
        "categories": categories or None,
        "apply_links": apply_links or None,
    }
    hash_payload = {
        "source_url": source_url,
        "title": title,
        "institution": company,
        "category": ", ".join(categories) if categories else None,
        "location": location,
        "description_text": description_text,
        "metadata": metadata,
    }
    return JobRecord(
        source="zoom_jobs",
        source_url=validate_http_url(source_url),
        title=title or "Untitled",
        institution=company,
        number_of_posts=None,
        deadline_date=None,
        category=", ".join(categories) if categories else None,
        location=location,
        description_text=description_text,
        description_html=description_html,
        attachments_json=metadata,
        content_hash=compute_content_hash(hash_payload),
    )


class ZoomTanzaniaJobsAdapter(BrowserSiteAdapter[JobStub, JobRecord]):
    """Jobs adapter for Zoom Tanzania listings."""

    site_name = "zoom_jobs"
    content_type = ContentType.JOBS

    async def discover(self) -> list[JobStub]:
        """Discover Zoom Tanzania jobs, following pagination when present."""

        page_url: str | None = ZOOM_JOBS_URL
        stubs: list[JobStub] = []
        seen_urls: set[str] = set()
        pages_seen = 0
        while page_url and pages_seen < self.settings.zoom_jobs_max_pages:
            page_html = await self._fetch_page_html(page_url, wait_selector="div.civi-jobs-item")
            page_stubs = parse_zoom_job_stubs(page_html, base_url=ZOOM_JOBS_URL)
            new_stubs = [stub for stub in page_stubs if str(stub.url) not in seen_urls]
            if not new_stubs:
                break
            for stub in new_stubs:
                seen_urls.add(str(stub.url))
            stubs.extend(new_stubs)
            page_url = parse_zoom_next_page(page_html, base_url=ZOOM_JOBS_URL)
            pages_seen += 1
        return stubs

    async def fetch_details(self, stub: JobStub) -> JobRecord:
        """Fetch and parse one Zoom job detail page."""

        page_html = await self._fetch_page_html(str(stub.url), wait_selector="h1")
        return parse_zoom_job_record(page_html, source_url=str(stub.url))

    async def upsert(self, record: JobRecord) -> UpsertResult:
        """Persist one Zoom job into the jobs table."""

        async with self.session_factory() as db_session:
            _, upsert_result = await upsert_job_posting(db_session, record)
            await db_session.commit()
            return upsert_result


register_adapter("zoom_jobs", ZoomTanzaniaJobsAdapter)
