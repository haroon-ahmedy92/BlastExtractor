from app.crawler.ajira import extract_title


def test_extract_title() -> None:
    sample = "<html><head><title>Ajira Portal</title></head><body></body></html>"
    assert extract_title(sample) == "Ajira Portal"
