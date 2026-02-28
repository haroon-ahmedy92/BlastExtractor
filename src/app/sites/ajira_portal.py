"""Ajira Portal job adapter and parsing helpers.

This module contains the real Ajira site plugin used by the generic crawl
runner. The helper functions parse listing pages and detail pages, while
``AjiraPortalAdapter`` connects that parsing logic to browser fetches and job
table upserts.
"""

from __future__ import annotations

import hashlib
import json
import re
from asyncio import Lock, sleep
from datetime import date, datetime
from time import monotonic
from urllib.parse import urljoin

from lxml import html
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.config import get_settings
from app.db.job_postings import upsert_job_posting
from app.models.common import ContentType, UpsertResult, normalize_whitespace, parse_optional_date
from app.models.jobs import JobRecord, JobStub
from app.sites.base import SiteAdapter
from app.sites.registry import register_adapter

VACANCIES_URL = "https://portal.ajira.go.tz/vacancies"
GENERIC_LINK_TEXTS = {
    "details",
    "view",
    "view details",
    "read more",
    "more",
    "open",
    "apply",
}
MENU_LINK_TEXTS = {"home", "vacancies", "feedback", "login", "register", "contact"}
ATTACHMENT_EXTENSIONS = (".pdf", ".doc", ".docx", ".xls", ".xlsx")
FOOTER_KEYWORDS = (
    "download ajira portal app",
    "download ajira app",
    "download our app",
    "download the app",
    "download on the app store",
    "get it on google play",
    "google play",
    "app store",
    "play store",
)
STRUCTURED_FIELD_LABELS: dict[str, tuple[str, ...]] = {
    "remuneration": ("remuneration", "salary", "pay", "pay scale"),
    "application_period": (
        "application period",
        "application window",
        "application timeline",
        "application dates",
        "application duration",
    ),
    "qualifications": (
        "qualifications",
        "qualification",
        "minimum qualifications",
        "required qualifications",
        "requirements",
    ),
    "duties": (
        "duties",
        "responsibilities",
        "roles",
        "roles and responsibilities",
        "duties and responsibilities",
    ),
}


class AjiraTransientError(RuntimeError):
    """Retryable error raised for transient browser or network failures."""

    pass


def _parse_number_of_posts(value: str) -> int | None:
    match = re.search(r"\b(\d{1,4})\b", value)
    return int(match.group(1)) if match else None


def _parse_date(value: str) -> date | None:
    text = normalize_whitespace(value)
    if not text:
        return None
    patterns = [
        (r"\b(\d{4}-\d{1,2}-\d{1,2})\b", ("%Y-%m-%d",)),
        (r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{4})\b", ("%d/%m/%Y", "%d-%m-%Y", "%m/%d/%Y", "%m-%d-%Y")),
        (r"\b(\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4})\b", ("%d %b %Y", "%d %B %Y")),
        (r"\b([A-Za-z]{3,9}\s+\d{1,2},\s+\d{4})\b", ("%b %d, %Y", "%B %d, %Y")),
    ]
    for regex, fmts in patterns:
        match = re.search(regex, text)
        if not match:
            continue
        for fmt in fmts:
            try:
                return datetime.strptime(match.group(1), fmt).date()
            except ValueError:
                continue
    return None


def _looks_like_details_href(href: str) -> bool:
    lower = href.lower()
    if not href or href.startswith("#") or lower.startswith("javascript:"):
        return False
    if any(domain in lower for domain in ("play.google.com", "apps.apple.com")):
        return False
    if lower in {"/", "/vacancies", "/feedback", "/auth/login"}:
        return False
    tokens = ("/view-advert/", "vacanc", "job", "post", "detail", "opening", "apply")
    return any(token in lower for token in tokens)


def _title_from_container(container: html.HtmlElement) -> str | None:
    title_nodes = container.xpath(".//h1|.//h2|.//h3|.//h4|.//strong|.//b|.//a")
    for node in title_nodes:
        text = normalize_whitespace(node.text_content())
        if not text or text.lower() in GENERIC_LINK_TEXTS | MENU_LINK_TEXTS or len(text) < 4:
            continue
        return text
    text = normalize_whitespace(container.text_content())
    return text[:200] if text else None


def _select_listing_container(link_node: html.HtmlElement) -> html.HtmlElement:
    for node in link_node.iterancestors():
        if node.tag not in {"tr", "article", "li", "div", "section"}:
            continue
        text_len = len(normalize_whitespace(node.text_content()))
        if 30 <= text_len <= 3000:
            return node
    return link_node


def _extract_labeled_value(text: str, labels: tuple[str, ...]) -> str | None:
    stop_tokens = (
        "number of posts|positions|vacancies|posts|closing date|deadline|"
        "last date|application deadline|view details|login to apply"
    )
    for label in labels:
        match = re.search(
            rf"\b{label}\b\s*[:\-]?\s*(.+?)(?=\b({stop_tokens})\b|$)",
            text,
            flags=re.IGNORECASE,
        )
        if match:
            value = normalize_whitespace(match.group(1))
            if value:
                return value
    return None


def _fallback_row_url(base_url: str, serial: str | None) -> str:
    if serial and serial.isdigit():
        return f"{base_url}?row={serial}"
    return base_url


def _parse_table_row(row: html.HtmlElement, base_url: str) -> JobStub | None:
    cells = row.xpath("./td")
    if len(cells) < 4:
        return None

    first_cell_text = normalize_whitespace(" ".join(cells[0].xpath(".//text()")))
    serial = first_cell_text if first_cell_text.isdigit() else None
    title_source_idx = 1 if serial else 0
    institution_idx = 2 if serial else 1
    deadline_idx = 3

    title_raw = normalize_whitespace(" ".join(cells[title_source_idx].xpath(".//text()")))
    title = re.sub(r"Number\s+of\s+Posts\s*:\s*\d+", "", title_raw, flags=re.IGNORECASE)
    title = normalize_whitespace(title)
    institution = normalize_whitespace(" ".join(cells[institution_idx].xpath(".//text()"))) or None
    deadline_text = normalize_whitespace(" ".join(cells[deadline_idx].xpath(".//text()")))
    deadline_date = _parse_date(deadline_text)
    posts_xpath = (
        ".//*[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', "
        "'abcdefghijklmnopqrstuvwxyz'), 'number of posts')]//text()"
    )
    number_text = normalize_whitespace(" ".join(cells[title_source_idx].xpath(posts_xpath)))
    if not number_text and len(cells) > 2:
        number_text = normalize_whitespace(" ".join(cells[2].xpath(".//text()")))
    number_of_posts = _parse_number_of_posts(number_text or title_raw)

    href = None
    for link in row.xpath(".//a[@href]"):
        raw_href = normalize_whitespace(link.get("href", ""))
        if _looks_like_details_href(raw_href):
            href = raw_href
            break

    details_url = urljoin(base_url, href) if href else _fallback_row_url(base_url, serial)
    if not title or title.lower() in MENU_LINK_TEXTS:
        return None
    try:
        return JobStub(
            title=title,
            institution=institution,
            number_of_posts=number_of_posts,
            deadline_date=deadline_date,
            url=details_url,
        )
    except Exception:
        return None


def _parse_from_table_rows(tree: html.HtmlElement, base_url: str) -> list[JobStub]:
    return [
        item
        for row in tree.xpath("//table//tbody/tr")
        if (item := _parse_table_row(row, base_url=base_url)) is not None
    ]


def _parse_from_links(tree: html.HtmlElement, base_url: str) -> list[JobStub]:
    results: list[JobStub] = []
    seen_urls: set[str] = set()
    for link in tree.xpath("//a[@href]"):
        href = normalize_whitespace(link.get("href", ""))
        if not _looks_like_details_href(href):
            continue
        details_url = urljoin(base_url, href)
        if details_url in seen_urls:
            continue
        container = _select_listing_container(link)
        container_text = normalize_whitespace(container.text_content())
        lower_text = container_text.lower()
        if len(container_text) < 20:
            continue
        if not any(signal in lower_text for signal in ("number of posts", "deadline", "close date", "login to apply")):
            continue

        title = _title_from_container(container)
        if not title or title.lower() in MENU_LINK_TEXTS:
            continue
        institution = _extract_labeled_value(
            container_text,
            ("institution", "employer", "organization", "ministry", "agency"),
        )
        number_label = _extract_labeled_value(
            container_text,
            ("number of posts", "positions", "vacancies", "posts"),
        )
        deadline_label = _extract_labeled_value(
            container_text,
            ("deadline", "closing date", "last date", "application deadline"),
        )
        try:
            results.append(
                JobStub(
                    title=title,
                    institution=institution,
                    number_of_posts=_parse_number_of_posts(number_label or container_text),
                    deadline_date=_parse_date(deadline_label or container_text),
                    url=details_url,
                )
            )
            seen_urls.add(details_url)
        except Exception:
            continue
    return results


def parse_listing_stubs_from_html(page_html: str, base_url: str = VACANCIES_URL) -> list[JobStub]:
    """Parse job listing stubs from the Ajira vacancies page HTML.

    Args:
        page_html: Raw listing page HTML.
        base_url: Base URL used to resolve relative links.

    Returns:
        list[JobStub]: Parsed job stubs.
    """

    document_tree = html.fromstring(page_html)
    row_based_stubs = _parse_from_table_rows(document_tree, base_url=base_url)
    if row_based_stubs:
        return row_based_stubs
    return _parse_from_links(document_tree, base_url=base_url)


def _extract_attachments(tree: html.HtmlElement, base_url: str) -> list[str]:
    attachments: list[str] = []
    seen: set[str] = set()
    for link in tree.xpath("//a[@href]"):
        href = normalize_whitespace(link.get("href", ""))
        text = normalize_whitespace(link.text_content()).lower()
        if not href:
            continue
        lower_href = href.lower()
        looks_attachment = lower_href.endswith(ATTACHMENT_EXTENSIONS) or "download" in lower_href
        looks_attachment = looks_attachment or any(k in text for k in ("attachment", "pdf", "doc", "download"))
        if not looks_attachment:
            continue
        absolute = urljoin(base_url, href)
        if absolute in seen:
            continue
        seen.add(absolute)
        attachments.append(absolute)
    return attachments


def _extract_extra_metadata(tree: html.HtmlElement) -> dict[str, str]:
    metadata: dict[str, str] = {}
    for row in tree.xpath("//tr[td and (count(td)=2 or count(th)=1 and count(td)=1)]"):
        key_node = row.xpath("./th[1] | ./td[1]")
        value_node = row.xpath("./td[last()]")
        if not key_node or not value_node:
            continue
        key = normalize_whitespace(key_node[0].text_content()).rstrip(":").lower()
        value = normalize_whitespace(value_node[0].text_content())
        if key and value and len(key) <= 60 and len(value) <= 500:
            metadata[key] = value
    for node in tree.xpath("//p|//li"):
        text = normalize_whitespace(node.text_content())
        if ":" not in text or len(text) < 6 or len(text) > 300:
            continue
        left, right = text.split(":", 1)
        key = normalize_whitespace(left).lower()
        value = normalize_whitespace(right)
        if key and value and key not in {"number of posts", "deadline", "close date"}:
            metadata.setdefault(key, value)
    return metadata


def _remove_footer_sections(node: html.HtmlElement) -> None:
    for footer in list(node.xpath(".//footer | .//index-footer")):
        parent = footer.getparent()
        if parent is not None:
            parent.remove(footer)
    for descendant in list(node.xpath(".//*")):
        if not isinstance(descendant.tag, str):
            continue
        text = normalize_whitespace(descendant.text_content()).lower()
        if text and any(keyword in text for keyword in FOOTER_KEYWORDS):
            parent = descendant.getparent()
            if parent is not None:
                parent.remove(descendant)


def _node_matches_label(text: str, labels: tuple[str, ...]) -> bool:
    normalized = normalize_whitespace(text).lower()
    if not normalized or len(normalized) > 120:
        return False
    for label in labels:
        label_lower = label.lower()
        if normalized == label_lower:
            return True
        if normalized.startswith(f"{label_lower}:") or normalized.startswith(f"{label_lower}-"):
            return True
    return False


def _extract_value_after_label(node: html.HtmlElement, label_text: str) -> str | None:
    for sibling in node.itersiblings():
        if not isinstance(sibling.tag, str) or sibling.xpath(".//button"):
            continue
        text = normalize_whitespace(sibling.text_content())
        if text:
            return text
    parent = node.getparent()
    if parent is not None:
        parent_text = normalize_whitespace(parent.text_content())
        idx = parent_text.lower().find(label_text.lower())
        if idx != -1:
            remainder = normalize_whitespace(parent_text[idx + len(label_text) :])
            if remainder:
                return remainder
    return None


def _extract_structured_fields(tree: html.HtmlElement) -> dict[str, str]:
    structured: dict[str, str] = {}
    for key, labels in STRUCTURED_FIELD_LABELS.items():
        for node in tree.iter():
            if not isinstance(node.tag, str) or node.tag.lower() in {"script", "style", "noscript"}:
                continue
            text = normalize_whitespace(node.text_content())
            if not text or not _node_matches_label(text, labels):
                continue
            value = _extract_value_after_label(node, text)
            if value:
                structured[key] = value
                break
    return structured


def _extract_description(tree: html.HtmlElement) -> tuple[str | None, str | None]:
    for node in tree.xpath("//script|//style|//noscript"):
        parent = node.getparent()
        if parent is not None:
            parent.remove(node)
    candidates = tree.xpath(
        "//main|//article|//section|//div[contains(@class,'description') or contains(@class,'content')]"
    )
    best = None
    best_len = 0
    for node in candidates:
        text = normalize_whitespace(node.text_content())
        if len(text) > best_len:
            best = node
            best_len = len(text)
    if best is None:
        body_nodes = tree.xpath("//body")
        best = body_nodes[0] if body_nodes else tree
    _remove_footer_sections(best)
    description_text = normalize_whitespace(best.text_content())
    if len(description_text) < 20:
        return None, None
    return description_text, html.tostring(best, encoding="unicode", method="html")


def parse_listing_detail_from_html(
    page_html: str,
    base_url: str,
) -> tuple[str | None, str | None, list[str], dict[str, str], dict[str, str]]:
    """Parse a job detail page into normalized pieces.

    Args:
        page_html: Raw detail page HTML.
        base_url: Base URL used to resolve relative links.

    Returns:
        tuple[str | None, str | None, list[str], dict[str, str], dict[str, str]]:
            Description text, description HTML, attachment links, extra
            metadata, and extracted structured fields.
    """

    document_tree = html.fromstring(page_html)
    description_text, description_html = _extract_description(document_tree)
    attachments = _extract_attachments(document_tree, base_url=base_url)
    extra_metadata = _extract_extra_metadata(document_tree)
    structured_fields = _extract_structured_fields(document_tree)
    return description_text, description_html, attachments, extra_metadata, structured_fields


def compute_content_hash(payload: dict[str, object]) -> str:
    """Compute a stable content hash for a normalized record payload.

    Args:
        payload: JSON-serializable payload containing meaningful content fields.

    Returns:
        str: SHA-256 hex digest.
    """

    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class AjiraPortalAdapter(SiteAdapter[JobStub, JobRecord]):
    """Site adapter that crawls Ajira Portal job postings."""

    site_name = "ajira"
    content_type = ContentType.JOBS

    def __init__(self, *, browser_context: object | None, session_factory) -> None:
        """Create an Ajira adapter with shared runtime dependencies.

        Args:
            browser_context: Shared Playwright browser context.
            session_factory: Async SQLAlchemy session factory.
        """

        super().__init__(browser_context=browser_context, session_factory=session_factory)
        self.settings = get_settings()
        self._rate_lock = Lock()
        self._last_request_started = 0.0

    async def _wait_for_rate_limit(self) -> None:
        async with self._rate_lock:
            current_time = monotonic()
            delay = self.settings.browser_rate_limit_seconds - (
                current_time - self._last_request_started
            )
            if delay > 0:
                await sleep(delay)
            self._last_request_started = monotonic()

    def _classify_error(self, error: Exception) -> type[Exception]:
        message = str(error).lower()
        transient_markers = ("timeout", "timed out", "net::err", "503", "502", "500")
        if any(marker in message for marker in transient_markers):
            return AjiraTransientError
        return RuntimeError

    async def _fetch_page_html(self, url: str, wait_selector: str | None = None) -> str:
        if self.browser_context is None:
            raise RuntimeError("Browser context is required for AjiraPortalAdapter")
        async for attempt in AsyncRetrying(
            reraise=True,
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=1, max=8),
            retry=retry_if_exception_type(AjiraTransientError),
        ):
            with attempt:
                page = await self.browser_context.new_page()
                try:
                    await self._wait_for_rate_limit()
                    await page.goto(url, wait_until="domcontentloaded")
                    if wait_selector:
                        await page.wait_for_selector(wait_selector)
                    else:
                        await page.wait_for_load_state("networkidle")
                    return await page.content()
                except Exception as error:
                    error_type = self._classify_error(error)
                    raise error_type(str(error)) from error
                finally:
                    await page.close()
        raise AjiraTransientError(f"Failed to fetch page: {url}")

    async def discover(self) -> list[JobStub]:
        """Discover job stubs from the Ajira vacancies listing page.

        Returns:
            list[JobStub]: Discovered job stubs.
        """

        page_html = await self._fetch_page_html(
            VACANCIES_URL,
            wait_selector="table tbody tr, article, li",
        )
        discovered_stubs = parse_listing_stubs_from_html(page_html, base_url=VACANCIES_URL)
        self.logger.info(
            "Discovered stubs",
            extra={"site_name": self.site_name, "count": len(discovered_stubs)},
        )
        return discovered_stubs

    async def fetch_details(self, stub: JobStub) -> JobRecord:
        """Fetch and normalize one Ajira job detail page.

        Args:
            stub: Discovered Ajira job stub.

        Returns:
            JobRecord: Normalized job record.
        """

        page_html = await self._fetch_page_html(str(stub.url))
        description_text, description_html, attachment_links, extra_metadata, structured_fields = (
            parse_listing_detail_from_html(page_html, base_url=str(stub.url))
        )
        metadata = dict(extra_metadata or {})
        if structured_fields:
            metadata["structured_fields"] = structured_fields
        category = metadata.get("category") or metadata.get("job category")
        location = metadata.get("duty station") or metadata.get("location")
        attachments_json = None
        if attachment_links or metadata:
            attachments_json = {"links": attachment_links, "metadata": metadata}
        hash_payload = {
            "source_url": str(stub.url),
            "title": stub.title,
            "institution": stub.institution,
            "number_of_posts": stub.number_of_posts,
            "deadline_date": str(stub.deadline_date) if stub.deadline_date else None,
            "description_text": description_text,
            "description_html": description_html,
            "attachments": sorted(attachment_links),
            "metadata": metadata,
        }
        return JobRecord(
            source=self.site_name,
            source_url=str(stub.url),
            title=stub.title or "Unknown",
            institution=stub.institution or "Unknown",
            number_of_posts=stub.number_of_posts,
            deadline_date=stub.deadline_date,
            category=category,
            location=location,
            description_text=description_text,
            description_html=description_html,
            attachments_json=attachments_json,
            content_hash=compute_content_hash(hash_payload),
        )

    async def upsert(self, record: JobRecord) -> UpsertResult:
        """Persist one Ajira job record into the jobs table.

        Args:
            record: Normalized job record.

        Returns:
            UpsertResult: Summary of the database action taken.
        """

        async with self.session_factory() as db_session:
            _, upsert_result = await upsert_job_posting(db_session, record)
            await db_session.commit()
            return upsert_result


register_adapter("ajira", AjiraPortalAdapter)
