"""Shared parsing helpers for Nation Media news sites.

The Citizen and Mwananchi share similar article structures. This module keeps
their adapters small by centralizing link discovery and detail parsing.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from lxml import html

from app.models.common import (
    compute_content_hash,
    normalize_whitespace,
    parse_optional_datetime,
    validate_http_url,
)
from app.models.news import NewsRecord, NewsStub
from app.sites.parsing_support import (
    find_json_ld_by_type,
    looks_like_article_link,
    normalize_url,
    parse_html_document,
)


def discover_news_stubs(
    page_html: str,
    *,
    base_url: str,
    source_name: str,
    allowed_prefixes: tuple[str, ...] = (),
    excluded_prefixes: tuple[str, ...] = (),
) -> list[NewsStub]:
    """Extract article links from a listing or homepage.

    Args:
        page_html: Raw HTML page content.
        base_url: Base URL used to resolve links.
        source_name: Source name for filtering and logging context.
        allowed_prefixes: Optional accepted path prefixes.

    Returns:
        list[NewsStub]: Discovered article stubs.
    """

    tree = parse_html_document(page_html)
    stubs: list[NewsStub] = []
    seen_urls: set[str] = set()
    for anchor in tree.xpath("//a[@href]"):
        href = normalize_whitespace(anchor.get("href", ""))
        if not looks_like_article_link(href):
            continue
        absolute_url = normalize_url(base_url, href)
        parsed_url = urlparse(absolute_url)
        if allowed_prefixes and not any(
            parsed_url.path.startswith(prefix) for prefix in allowed_prefixes
        ):
            continue
        if excluded_prefixes and any(
            parsed_url.path.startswith(prefix) for prefix in excluded_prefixes
        ):
            continue
        if absolute_url in seen_urls:
            continue
        title = normalize_whitespace(anchor.text_content())
        if not title or title.lower() in {source_name, "world", "national", "business"}:
            continue
        try:
            stubs.append(NewsStub(url=validate_http_url(absolute_url), title=title))
            seen_urls.add(absolute_url)
        except Exception:
            continue
    return stubs


def _extract_author(article_data: dict[str, Any]) -> str | None:
    author = article_data.get("author")
    if isinstance(author, list) and author:
        author = author[0]
    if isinstance(author, dict):
        return normalize_whitespace(str(author.get("name", ""))) or None
    if isinstance(author, str):
        return normalize_whitespace(author) or None
    return None


def _extract_section(page_html: str, source_url: str) -> str | None:
    breadcrumb = find_json_ld_by_type(page_html, "BreadcrumbList")
    if breadcrumb:
        items = breadcrumb.get("itemListElement", [])
        names = [
            normalize_whitespace(str(item.get("name", "")))
            for item in items
            if isinstance(item, dict)
        ]
        candidates = [name for name in names if name and name.lower() not in {"home", "news"}]
        if candidates:
            return candidates[-1]

    path_parts = [part for part in urlparse(source_url).path.split("/") if part]
    for part in reversed(path_parts):
        if not re.search(r"\d+$", part):
            return normalize_whitespace(part.replace("-", " ").title())
    return None


def parse_news_record(
    page_html: str,
    *,
    source: str,
    source_url: str,
    fallback_title: str | None = None,
) -> NewsRecord:
    """Parse a news detail page into a normalized record.

    Args:
        page_html: Raw article HTML.
        source: Source identifier for the record.
        source_url: Canonical article URL.
        fallback_title: Optional fallback title from discovery.

    Returns:
        NewsRecord: Normalized article record.
    """

    article_data = find_json_ld_by_type(page_html, "NewsArticle") or {}
    tree = parse_html_document(page_html)
    headline = normalize_whitespace(
        str(article_data.get("headline") or article_data.get("name") or "")
    ) or None
    title = (
        headline
        or fallback_title
        or normalize_whitespace("".join(tree.xpath("//h1[1]//text()")))
        or "Untitled"
    )
    published_at = parse_optional_datetime(article_data.get("datePublished"))
    author = _extract_author(article_data)
    section = _extract_section(page_html, source_url)
    paragraphs = [
        normalize_whitespace(paragraph.text_content())
        for paragraph in tree.xpath("//div[contains(@class,'paragraph-wrapper')]//p")
    ]
    if not paragraphs:
        paragraphs = [
            normalize_whitespace(paragraph.text_content())
            for paragraph in tree.xpath("//article//p")
        ]
    body_lines = [line for line in paragraphs if line]
    body_text = "\n".join(body_lines) or None
    body_node = tree.xpath("//section[.//div[contains(@class,'paragraph-wrapper')]][1]")
    if not body_node:
        body_node = tree.xpath("//article[.//p][1]")
    body_html = (
        html.tostring(body_node[0], encoding="unicode", method="html") if body_node else None
    )
    tags = article_data.get("keywords")
    if isinstance(tags, str):
        tags_json: list[str] | None = [
            normalize_whitespace(tag) for tag in tags.split(",") if tag.strip()
        ]
    elif isinstance(tags, list):
        tags_json = [
            normalize_whitespace(str(tag))
            for tag in tags
            if normalize_whitespace(str(tag))
        ]
    else:
        tags_json = None

    hash_payload = {
        "source_url": source_url,
        "title": title,
        "author": author,
        "published_at": published_at.isoformat() if published_at else None,
        "section": section,
        "body_text": body_text,
        "tags_json": tags_json,
    }
    return NewsRecord(
        source=source,
        source_url=validate_http_url(source_url),
        title=title,
        author=author,
        published_at=published_at,
        section=section,
        body_text=body_text,
        body_html=body_html,
        tags_json=tags_json,
        attachments_json=None,
        content_hash=compute_content_hash(hash_payload),
    )
