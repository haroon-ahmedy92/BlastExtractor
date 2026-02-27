from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
from datetime import date, datetime
from time import perf_counter
from urllib.parse import urljoin, urlparse

from lxml import html
from tenacity import retry, stop_after_attempt, wait_exponential

from app.models.listing_detail import ListingDetail
from app.models.listing_stub import ListingStub

logger = logging.getLogger(__name__)

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


def _normalize_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _parse_number_of_posts(value: str) -> int | None:
    match = re.search(r"\b(\d{1,4})\b", value)
    return int(match.group(1)) if match else None


def _parse_date(value: str) -> date | None:
    text = _normalize_whitespace(value)
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
    return any(token in lower for token in ("/view-advert/", "vacanc", "job", "post", "detail", "opening", "apply"))


def _title_from_container(container: html.HtmlElement) -> str | None:
    title_nodes = container.xpath(".//h1|.//h2|.//h3|.//h4|.//strong|.//b|.//a")
    for node in title_nodes:
        text = _normalize_whitespace(node.text_content())
        if not text:
            continue
        if text.lower() in GENERIC_LINK_TEXTS | MENU_LINK_TEXTS:
            continue
        if len(text) < 4:
            continue
        return text
    text = _normalize_whitespace(container.text_content())
    return text[:200] if text else None


def _select_listing_container(link_node: html.HtmlElement) -> html.HtmlElement:
    for node in link_node.iterancestors():
        if node.tag not in {"tr", "article", "li", "div", "section"}:
            continue
        text_len = len(_normalize_whitespace(node.text_content()))
        if 30 <= text_len <= 3000:
            return node
    return link_node


def _extract_labeled_value(text: str, labels: tuple[str, ...]) -> str | None:
    for label in labels:
        match = re.search(
            rf"\b{label}\b\s*[:\-]?\s*(.+?)(?=\b(number of posts|positions|vacancies|posts|closing date|deadline|last date|application deadline|view details|login to apply)\b|$)",
            text,
            flags=re.IGNORECASE,
        )
        if match:
            value = _normalize_whitespace(match.group(1))
            if value:
                return value
    return None


def _fallback_row_url(base_url: str, serial: str | None) -> str:
    if serial and serial.isdigit():
        return f"{base_url}?row={serial}"
    return base_url


def _parse_table_row(row: html.HtmlElement, base_url: str) -> ListingStub | None:
    cells = row.xpath("./td")
    if len(cells) < 4:
        return None

    first_cell_text = _normalize_whitespace(" ".join(cells[0].xpath(".//text()")))
    serial = first_cell_text if first_cell_text.isdigit() else None

    if serial:
        title_source_idx = 1
        institution_idx = 2
        deadline_idx = 3
    else:
        title_source_idx = 0
        institution_idx = 1
        deadline_idx = 3

    title_raw = _normalize_whitespace(" ".join(cells[title_source_idx].xpath(".//text()")))
    title = re.sub(r"Number\s+of\s+Posts\s*:\s*\d+", "", title_raw, flags=re.IGNORECASE)
    title = _normalize_whitespace(title)

    institution = _normalize_whitespace(" ".join(cells[institution_idx].xpath(".//text()"))) or None
    deadline_date = _parse_date(_normalize_whitespace(" ".join(cells[deadline_idx].xpath(".//text()"))))

    number_text = _normalize_whitespace(
        " ".join(
            cells[title_source_idx].xpath(
                ".//*[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'number of posts')]//text()"
            )
        )
    )
    if not number_text and len(cells) > 2:
        number_text = _normalize_whitespace(" ".join(cells[2].xpath(".//text()")))
    number_of_posts = _parse_number_of_posts(number_text or title_raw)

    href = None
    links = row.xpath(".//a[@href]")
    for link in links:
        raw_href = _normalize_whitespace(link.get("href", ""))
        if _looks_like_details_href(raw_href):
            href = raw_href
            break

    details_url = urljoin(base_url, href) if href else _fallback_row_url(base_url, serial)

    if not title or title.lower() in MENU_LINK_TEXTS:
        return None

    try:
        return ListingStub(
            title=title,
            institution=institution,
            number_of_posts=number_of_posts,
            deadline_date=deadline_date,
            details_url=details_url,
        )
    except Exception:
        return None


def _parse_from_table_rows(tree: html.HtmlElement, base_url: str) -> list[ListingStub]:
    rows = tree.xpath("//table//tbody/tr")
    if not rows:
        return []

    parsed: list[ListingStub] = []
    for row in rows:
        item = _parse_table_row(row, base_url=base_url)
        if item is not None:
            parsed.append(item)
    return parsed


def _parse_from_links(tree: html.HtmlElement, base_url: str) -> list[ListingStub]:
    results: list[ListingStub] = []
    seen_urls: set[str] = set()

    for link in tree.xpath("//a[@href]"):
        href = _normalize_whitespace(link.get("href", ""))
        if not _looks_like_details_href(href):
            continue

        details_url = urljoin(base_url, href)
        if details_url in seen_urls:
            continue

        container = _select_listing_container(link)
        container_text = _normalize_whitespace(container.text_content())
        lower_text = container_text.lower()
        if len(container_text) < 20:
            continue
        if not any(signal in lower_text for signal in ("number of posts", "deadline", "close date", "login to apply")):
            continue

        title = _title_from_container(container)
        if not title or title.lower() in MENU_LINK_TEXTS:
            continue

        institution = _extract_labeled_value(
            container_text, ("institution", "employer", "organization", "ministry", "agency")
        )

        number_label = _extract_labeled_value(
            container_text, ("number of posts", "positions", "vacancies", "posts")
        )
        number_of_posts = _parse_number_of_posts(number_label or container_text)

        deadline_label = _extract_labeled_value(
            container_text, ("deadline", "closing date", "last date", "application deadline")
        )
        deadline_date = _parse_date(deadline_label or container_text)

        try:
            listing = ListingStub(
                title=title,
                institution=institution,
                number_of_posts=number_of_posts,
                deadline_date=deadline_date,
                details_url=details_url,
            )
        except Exception:
            continue

        results.append(listing)
        seen_urls.add(details_url)

    return results


def parse_listing_stubs_from_html(page_html: str, base_url: str = VACANCIES_URL) -> list[ListingStub]:
    tree = html.fromstring(page_html)

    rows_first = _parse_from_table_rows(tree, base_url=base_url)
    if rows_first:
        return rows_first

    return _parse_from_links(tree, base_url=base_url)


def _extract_attachments(tree: html.HtmlElement, base_url: str) -> list[str]:
    attachments: list[str] = []
    seen: set[str] = set()
    for link in tree.xpath("//a[@href]"):
        href = _normalize_whitespace(link.get("href", ""))
        text = _normalize_whitespace(link.text_content()).lower()
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
        val_node = row.xpath("./td[last()]")
        if not key_node or not val_node:
            continue
        key = _normalize_whitespace(key_node[0].text_content()).rstrip(":").lower()
        value = _normalize_whitespace(val_node[0].text_content())
        if not key or not value:
            continue
        if len(key) > 60 or len(value) > 500:
            continue
        metadata[key] = value

    dts = tree.xpath("//dt")
    for dt in dts:
        dd = dt.getnext()
        if dd is None or dd.tag.lower() != "dd":
            continue
        key = _normalize_whitespace(dt.text_content()).rstrip(":").lower()
        value = _normalize_whitespace(dd.text_content())
        if key and value and len(key) <= 60 and len(value) <= 500:
            metadata[key] = value

    for node in tree.xpath("//p|//li"):
        text = _normalize_whitespace(node.text_content())
        if ":" not in text or len(text) < 6 or len(text) > 300:
            continue
        left, right = text.split(":", 1)
        key = _normalize_whitespace(left).lower()
        value = _normalize_whitespace(right)
        if not key or not value:
            continue
        if len(key) > 60 or len(value) > 500:
            continue
        if key in {"number of posts", "deadline", "close date", "advert name", "employer name"}:
            continue
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
        text = _normalize_whitespace(descendant.text_content()).lower()
        if not text:
            continue
        if any(keyword in text for keyword in FOOTER_KEYWORDS):
            parent = descendant.getparent()
            if parent is not None:
                parent.remove(descendant)


def _node_matches_label(text: str, labels: tuple[str, ...]) -> bool:
    normalized = _normalize_whitespace(text)
    if not normalized:
        return False
    lower_text = normalized.lower()
    if len(lower_text) > 120:
        return False
    for label in labels:
        label_lower = label.lower()
        if lower_text == label_lower:
            return True
        if lower_text.startswith(f"{label_lower}:") or lower_text.startswith(f"{label_lower}-"):
            return True
        if lower_text.startswith(label_lower + " ") and len(lower_text) <= len(label_lower) + 5:
            return True
    return False


def _extract_value_after_label(node: html.HtmlElement, label_text: str | None) -> str | None:
    for sibling in node.itersiblings():
        if not isinstance(sibling.tag, str):
            continue
        if sibling.xpath(".//button"):
            continue
        text = _normalize_whitespace(sibling.text_content())
        if text:
            return text

    parent = node.getparent()
    if parent is not None and label_text:
        parent_text = _normalize_whitespace(parent.text_content())
        lower_parent = parent_text.lower()
        lower_label = label_text.lower()
        idx = lower_parent.find(lower_label)
        if idx != -1:
            remainder = parent_text[idx + len(label_text) :]
            remainder = _normalize_whitespace(remainder)
            if remainder:
                return remainder

    grandparent = parent.getparent() if parent is not None else None
    if grandparent is not None and label_text:
        grand_text = _normalize_whitespace(grandparent.text_content())
        lower_grand = grand_text.lower()
        lower_label = label_text.lower()
        idx = lower_grand.find(lower_label)
        if idx != -1:
            remainder = grand_text[idx + len(label_text) :]
            remainder = _normalize_whitespace(remainder)
            if remainder:
                return remainder

    return None


def _extract_structured_fields(tree: html.HtmlElement) -> dict[str, str]:
    structured: dict[str, str] = {}
    for key, labels in STRUCTURED_FIELD_LABELS.items():
        for node in tree.iter():
            if not isinstance(node.tag, str):
                continue
            if node.tag.lower() in {"script", "style", "noscript"}:
                continue
            text = _normalize_whitespace(node.text_content())
            if not text:
                continue
            if _node_matches_label(text, labels):
                value = _extract_value_after_label(node, text)
                if value:
                    structured[key] = value
                    break
        if key in structured:
            continue
    return structured


def _extract_description(tree: html.HtmlElement) -> tuple[str | None, str | None]:
    for node in tree.xpath("//script|//style|//noscript"):
        node.getparent().remove(node)

    candidates = tree.xpath("//main|//article|//section|//div[contains(@class,'description') or contains(@class,'content')]")
    best = None
    best_len = 0
    for node in candidates:
        text = _normalize_whitespace(node.text_content())
        if len(text) > best_len:
            best = node
            best_len = len(text)

    if best is None:
        body_nodes = tree.xpath("//body")
        best = body_nodes[0] if body_nodes else tree

    _remove_footer_sections(best)

    description_text = _normalize_whitespace(best.text_content())
    if len(description_text) < 20:
        return None, None

    description_html = html.tostring(best, encoding="unicode", method="html")
    return description_text, description_html


def parse_listing_detail_from_html(
    page_html: str, base_url: str
) -> tuple[str | None, str | None, list[str], dict[str, str], dict[str, str]]:
    tree = html.fromstring(page_html)
    description_text, description_html = _extract_description(tree)
    attachments = _extract_attachments(tree, base_url=base_url)
    extra_metadata = _extract_extra_metadata(tree)
    structured_fields = _extract_structured_fields(tree)
    return description_text, description_html, attachments, extra_metadata, structured_fields


def compute_content_hash(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class AjiraPortalSite:
    vacancies_url = VACANCIES_URL

    async def _resolve_detail_urls_from_row_actions(self, page, item_count: int) -> list[str | None]:
        urls: list[str | None] = []
        rows = page.locator("table tbody tr")
        row_count = await rows.count()
        limit = min(item_count, row_count, 25)

        for idx in range(limit):
            button = rows.nth(idx).locator("button")
            if await button.count() == 0:
                urls.append(None)
                continue

            try:
                await button.first.click(timeout=5000)
                await page.wait_for_url(re.compile(r".*/view-advert/.*"), timeout=8000)
                current = page.url
                parsed = urlparse(current)
                urls.append(current if "/view-advert/" in parsed.path else None)
            except Exception:
                urls.append(None)
            finally:
                if "/view-advert/" in page.url:
                    await page.go_back(wait_until="domcontentloaded")
                    try:
                        await page.wait_for_load_state("networkidle", timeout=10000)
                    except Exception:
                        pass
                    await asyncio.sleep(0.2)

        return urls

    @retry(reraise=True, stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
    async def fetch_listing_stubs(self) -> list[ListingStub]:
        from playwright.async_api import TimeoutError as PlaywrightTimeoutError, async_playwright

        started = perf_counter()
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            context = await browser.new_context()
            page = await context.new_page()

            await page.goto(self.vacancies_url, wait_until="domcontentloaded")

            try:
                await page.wait_for_load_state("networkidle", timeout=15000)
            except PlaywrightTimeoutError:
                await page.wait_for_selector("table tbody tr, article, li", timeout=15000)

            await asyncio.sleep(1.0)
            content = await page.content()
            listings = parse_listing_stubs_from_html(content, base_url=self.vacancies_url)

            detail_urls = await self._resolve_detail_urls_from_row_actions(page, len(listings))
            for idx, url in enumerate(detail_urls):
                if idx >= len(listings) or not url:
                    continue
                payload = listings[idx].model_dump(mode="python")
                payload["details_url"] = url
                listings[idx] = ListingStub(**payload)

            await context.close()
            await browser.close()

        logger.info(
            "Ajira listings extracted",
            extra={"count": len(listings), "elapsed_seconds": round(perf_counter() - started, 2)},
        )
        return listings

    async def _fetch_single_detail(self, context, stub: ListingStub, semaphore: asyncio.Semaphore) -> ListingDetail:
        from playwright.async_api import TimeoutError as PlaywrightTimeoutError

        async with semaphore:
            page = await context.new_page()
            details_url = str(stub.details_url)
            try:
                await page.goto(details_url, wait_until="domcontentloaded")
                try:
                    await page.wait_for_load_state("networkidle", timeout=12000)
                except PlaywrightTimeoutError:
                    await asyncio.sleep(0.5)

                html_content = await page.content()
                description_text, description_html, attachments, extra_metadata, structured_fields = parse_listing_detail_from_html(
                    html_content, base_url=details_url
                )
            except Exception as exc:
                logger.warning("Failed to fetch listing detail", extra={"url": details_url, "error": str(exc)})
                description_text = None
                description_html = None
                attachments = []
                extra_metadata = {}
                structured_fields = {}
            finally:
                await page.close()
                await asyncio.sleep(0.2)

            hash_input = {
                "source_url": details_url,
                "title": stub.title,
                "institution": stub.institution,
                "number_of_posts": stub.number_of_posts,
                "deadline_date": str(stub.deadline_date) if stub.deadline_date else None,
                "description_text": description_text,
                "description_html": description_html,
                "attachments": sorted(attachments),
                "extra_metadata": extra_metadata,
                "structured_fields": structured_fields or None,
            }

            return ListingDetail(
                title=stub.title,
                institution=stub.institution,
                number_of_posts=stub.number_of_posts,
                deadline_date=stub.deadline_date,
                details_url=stub.details_url,
                description_text=description_text,
                description_html=description_html,
                attachments=attachments or None,
                extra_metadata=extra_metadata or None,
                structured_fields=structured_fields or None,
                content_hash=compute_content_hash(hash_input),
            )

    async def fetch_listing_details(
        self, listings: list[ListingStub], max_concurrency: int = 4
    ) -> list[ListingDetail]:
        from playwright.async_api import async_playwright

        if not listings:
            return []

        semaphore = asyncio.Semaphore(max(1, min(5, max_concurrency)))

        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            context = await browser.new_context()

            tasks = [self._fetch_single_detail(context, listing, semaphore) for listing in listings]
            detailed = await asyncio.gather(*tasks)

            await context.close()
            await browser.close()

        return detailed

    async def crawl_with_details(self, max_concurrency: int = 4) -> list[ListingDetail]:
        stubs = await self.fetch_listing_stubs()
        return await self.fetch_listing_details(stubs, max_concurrency=max_concurrency)
