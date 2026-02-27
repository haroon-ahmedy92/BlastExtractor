from app.sites.ajira_portal import compute_content_hash


def test_content_hash_is_deterministic_for_same_payload() -> None:
    payload_a = {
        "source_url": "https://portal.ajira.go.tz/view-advert/abc",
        "title": "Data Engineer",
        "institution": "Public Data Agency",
        "number_of_posts": 2,
        "deadline_date": "2026-03-15",
        "description_text": "Build pipelines",
        "description_html": "<p>Build pipelines</p>",
        "attachments": ["https://portal.ajira.go.tz/docs/a.pdf"],
        "extra_metadata": {"duty station": "Dodoma", "salary scale": "TGS C"},
    }
    payload_b = {
        "extra_metadata": {"salary scale": "TGS C", "duty station": "Dodoma"},
        "attachments": ["https://portal.ajira.go.tz/docs/a.pdf"],
        "description_html": "<p>Build pipelines</p>",
        "description_text": "Build pipelines",
        "deadline_date": "2026-03-15",
        "number_of_posts": 2,
        "institution": "Public Data Agency",
        "title": "Data Engineer",
        "source_url": "https://portal.ajira.go.tz/view-advert/abc",
    }

    assert compute_content_hash(payload_a) == compute_content_hash(payload_b)


def test_content_hash_changes_when_relevant_field_changes() -> None:
    baseline = {
        "source_url": "https://portal.ajira.go.tz/view-advert/abc",
        "title": "Data Engineer",
        "institution": "Public Data Agency",
        "number_of_posts": 2,
        "deadline_date": "2026-03-15",
        "description_text": "Build pipelines",
        "description_html": "<p>Build pipelines</p>",
        "attachments": ["https://portal.ajira.go.tz/docs/a.pdf"],
        "extra_metadata": {"duty station": "Dodoma"},
    }
    changed = {**baseline, "description_text": "Build resilient pipelines"}

    assert compute_content_hash(baseline) != compute_content_hash(changed)
