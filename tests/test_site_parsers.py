from __future__ import annotations

from pathlib import Path

from app.sites.bmz_exams import (
    parse_bmz_centre_stubs,
    parse_bmz_exam_links,
    parse_exam_results_record,
)
from app.sites.citizen_news import CITIZEN_NEWS_URL
from app.sites.nation_media_support import discover_news_stubs, parse_news_record
from app.sites.necta_exams import parse_necta_centre_stubs, parse_necta_results_index_links
from app.sites.zoom_jobs import parse_zoom_job_record, parse_zoom_job_stubs, parse_zoom_next_page

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_citizen_list_parser_extracts_article_links() -> None:
    stubs = discover_news_stubs(
        load_fixture("citizen_list.html"),
        base_url=CITIZEN_NEWS_URL,
        source_name="citizen_news",
        allowed_prefixes=("/tanzania/news/",),
    )

    assert len(stubs) == 2
    assert str(stubs[0].url).endswith("/example-story-12345")


def test_citizen_detail_parser_extracts_core_fields() -> None:
    record = parse_news_record(
        load_fixture("citizen_detail.html"),
        source="citizen_news",
        source_url="https://www.thecitizen.co.tz/tanzania/news/national/example-story-12345",
    )

    assert record.title == "Example Citizen Story"
    assert record.author == "The Citizen Reporter"
    assert record.section == "National"
    assert "Example paragraph one." in (record.body_text or "")


def test_zoom_jobs_list_parser_extracts_cards_and_next_page() -> None:
    stubs = parse_zoom_job_stubs(load_fixture("zoom_jobs_list.html"))
    next_page = parse_zoom_next_page(load_fixture("zoom_jobs_list.html"))

    assert len(stubs) == 1
    assert stubs[0].institution == "Example Company"
    assert next_page == "https://www.zoomtanzania.net/jobs/page/2/"


def test_zoom_job_detail_parser_extracts_json_ld_and_tags() -> None:
    record = parse_zoom_job_record(
        load_fixture("zoom_job_detail.html"),
        source_url="https://www.zoomtanzania.net/jobs/manager/example-job/",
    )

    assert record.title == "Example Operations Manager"
    assert record.institution == "Example Company"
    assert record.location == "Dar es Salaam"
    assert record.category == "Operations"
    assert record.attachments_json is not None


def test_bmz_index_and_centre_parsers_extract_exam_data() -> None:
    exam_links = parse_bmz_exam_links(load_fixture("bmz_index.html"))
    stubs = parse_bmz_centre_stubs(
        load_fixture("bmz_exam_page.html"),
        year=2025,
        exam_type="Form Two",
        base_url="https://matokeo.bmz.go.tz/schools/FII(2025)/index.html",
    )

    assert exam_links[0][0] == 2025
    assert exam_links[0][1] == "Form Two"
    assert len(stubs) == 2
    assert stubs[0].centre_code == "ZS0331"


def test_bmz_centre_page_parser_extracts_results_table() -> None:
    stub = parse_bmz_centre_stubs(
        load_fixture("bmz_exam_page.html"),
        year=2025,
        exam_type="Form Two",
        base_url="https://matokeo.bmz.go.tz/schools/FII(2025)/index.html",
    )[0]
    record = parse_exam_results_record(
        load_fixture("bmz_centre_page.html"),
        stub=stub,
        source="bmz_exams",
    )

    assert record.centre_code == "ZS0331"
    assert record.results_json is not None
    assert record.results_json["tables"][1]["rows"][0][1] == "ZS0331/0001/2025"


def test_necta_parsers_extract_results_index_and_centres() -> None:
    results_links = parse_necta_results_index_links(load_fixture("necta_view.html"))
    stubs = parse_necta_centre_stubs(
        load_fixture("necta_results_index.html"),
        year=2025,
        exam_type="csee",
        base_url="https://matokeo.necta.go.tz/results/2025/csee/index.htm",
    )
    record = parse_exam_results_record(
        load_fixture("necta_centre_page.html"),
        stub=stubs[0],
        source="necta_exams",
    )

    assert results_links[0][0] == 2025
    assert len(stubs) == 2
    assert stubs[0].centre_code == "S0101"
    assert record.results_json is not None
