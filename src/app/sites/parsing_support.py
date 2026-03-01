"""Shared HTML parsing helpers for site adapters.

These helpers keep adapter modules focused on site-specific selectors while
providing small reusable functions for JSON-LD parsing, link normalization,
table extraction, and text cleanup.
"""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urljoin

from lxml import html

from app.models.common import normalize_whitespace


def parse_html_document(page_html: str) -> html.HtmlElement:
    """Parse raw HTML into an lxml document tree."""

    return html.fromstring(page_html)


def extract_json_ld_objects(page_html: str) -> list[dict[str, Any]]:
    """Extract JSON-LD objects from a page.

    Args:
        page_html: Raw HTML page content.

    Returns:
        list[dict[str, Any]]: Parsed JSON-LD dictionaries.
    """

    tree = parse_html_document(page_html)
    objects: list[dict[str, Any]] = []
    for node in tree.xpath("//script[@type='application/ld+json']/text()"):
        text = normalize_whitespace(node)
        if not text:
            continue
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, list):
            objects.extend(item for item in parsed if isinstance(item, dict))
        elif isinstance(parsed, dict):
            objects.append(parsed)
    return objects


def find_json_ld_by_type(page_html: str, type_name: str) -> dict[str, Any] | None:
    """Return the first JSON-LD object with a matching ``@type`` value."""

    for obj in extract_json_ld_objects(page_html):
        item_type = obj.get("@type")
        if item_type == type_name:
            return obj
        if isinstance(item_type, list) and type_name in item_type:
            return obj
    return None


def extract_text_lines(node: html.HtmlElement, xpath: str) -> list[str]:
    """Collect normalized text lines from matching nodes."""

    lines: list[str] = []
    for value in node.xpath(xpath):
        raw_value = value.text_content() if hasattr(value, "text_content") else str(value)
        text = normalize_whitespace(raw_value)
        if text:
            lines.append(text)
    return lines


def normalize_url(base_url: str, href: str) -> str:
    """Resolve a relative link against a base URL."""

    return urljoin(base_url, href)


def extract_table_data(table: html.HtmlElement) -> dict[str, Any]:
    """Convert an HTML table into a JSON-friendly structure.

    Args:
        table: Table element.

    Returns:
        dict[str, Any]: Table headers and rows.
    """

    rows = []
    header_rows = table.xpath(".//tr[th]")
    headers: list[str] = []
    if header_rows:
        headers = [
            normalize_whitespace(cell.text_content())
            for cell in header_rows[-1].xpath("./th|./td")
            if normalize_whitespace(cell.text_content())
        ]

    for row in table.xpath(".//tr[td]"):
        cells = [
            normalize_whitespace(cell.text_content())
            for cell in row.xpath("./th|./td")
        ]
        if any(cells):
            rows.append(cells)

    return {"headers": headers, "rows": rows}


def looks_like_article_link(href: str) -> bool:
    """Return whether a link looks like a news article detail page."""

    normalized = href.strip()
    if not normalized or normalized.startswith("#"):
        return False
    return bool(re.search(r"/[^/]+/[^/]+/[^/]+-\d+$", normalized.rstrip("/")))


def split_centre_label(label: str) -> tuple[str | None, str | None]:
    """Split a centre label into code and name parts."""

    normalized = normalize_whitespace(label)
    match = re.match(r"^([A-Z]{1,4}\d{3,5})\s+(.+)$", normalized)
    if not match:
        return None, normalized or None
    return match.group(1), match.group(2)
