import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import src.main as main


def _build_valid_html(index: int) -> str:
    return f"""
    <html><body>
      <article class="product_page">
        <div class="product_main">
          <h1>Book {index}</h1>
          <p class="price_color">£{index}.99</p>
          <p class="instock availability">In stock (1 available)</p>
          <p class="star-rating Four"><i class="icon-star"></i></p>
        </div>
        <div id="product_description"><h2>Product Description</h2></div>
        <p>Useful summary for Book {index}.</p>
      </article>
    </body></html>
    """


@pytest.fixture
def temp_output_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(main, "BOOKS_FILE", tmp_path / "books.json")
    monkeypatch.setattr(main, "ERRORS_FILE", tmp_path / "errors.json")
    return tmp_path


def test_run_scraper_survives_one_fake_book_url(temp_output_dir, monkeypatch):
    urls = [f"https://books.toscrape.com/catalogue/book-{i}_index.html" for i in range(1, 61)]
    urls.append("https://example.invalid/fake-book-for-stage5")

    def fake_fetch_with_retry(url, *, stats=None):
        if url.endswith("fake-book-for-stage5"):
            return None
        return _build_valid_html(int(url.rsplit("-", 1)[1].split("_", 1)[0]))

    monkeypatch.setattr(main, "fetch_with_retry", fake_fetch_with_retry)
    monkeypatch.setattr(main, "discover_catalogue_pages", lambda *args, **kwargs: {"catalogue_pages": 3, "discovered": 60, "unique_urls": 60, "urls": urls})

    report = main.run_scraper(urls)

    assert report["failed_pages"] == 1
    assert report["valid_records"] == 60
    books = json.loads(main.BOOKS_FILE.read_text(encoding="utf-8"))
    assert len(books) == 60
    assert all(book["product_url"] != "https://example.invalid/fake-book-for-stage5" for book in books)


def test_404_is_not_retried(monkeypatch):
    calls = []

    def fake_get(url, headers=None, timeout=None):
        calls.append((url, timeout))
        return SimpleNamespace(status_code=404, text="missing")

    monkeypatch.setattr(main.requests, "get", fake_get)

    result = main.fetch_with_retry("https://example.invalid/missing")

    assert result is None
    assert len(calls) == 1


def test_403_is_not_retried(monkeypatch):
    calls = []

    def fake_get(url, headers=None, timeout=None):
        calls.append((url, timeout))
        return SimpleNamespace(status_code=403, text="denied")

    monkeypatch.setattr(main.requests, "get", fake_get)

    result = main.fetch_with_retry("https://example.invalid/denied")

    assert result is None
    assert len(calls) == 1


def test_timeout_retries_once(monkeypatch):
    calls = []
    responses = [
        requests_exception := main.requests.exceptions.Timeout("timeout"),
        SimpleNamespace(status_code=200, text="ok"),
    ]

    def fake_get(url, headers=None, timeout=None):
        calls.append((url, timeout))
        response = responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    monkeypatch.setattr(main.requests, "get", fake_get)
    monkeypatch.setattr(main.time, "sleep", lambda *_args, **_kwargs: None)

    result = main.fetch_with_retry("https://example.com/timeout")

    assert result == "ok"
    assert len(calls) == 2


def test_5xx_retries_once(monkeypatch):
    calls = []
    responses = [
        SimpleNamespace(status_code=500, text="server error"),
        SimpleNamespace(status_code=200, text="ok"),
    ]

    def fake_get(url, headers=None, timeout=None):
        calls.append((url, timeout))
        return responses.pop(0)

    monkeypatch.setattr(main.requests, "get", fake_get)
    monkeypatch.setattr(main.time, "sleep", lambda *_args, **_kwargs: None)

    result = main.fetch_with_retry("https://example.com/500")

    assert result == "ok"
    assert len(calls) == 2


def test_repeated_5xx_stops_after_one_retry(monkeypatch):
    calls = []
    responses = [
        SimpleNamespace(status_code=500, text="server error"),
        SimpleNamespace(status_code=500, text="server error"),
    ]

    def fake_get(url, headers=None, timeout=None):
        calls.append((url, timeout))
        return responses.pop(0)

    monkeypatch.setattr(main.requests, "get", fake_get)
    monkeypatch.setattr(main.time, "sleep", lambda *_args, **_kwargs: None)

    result = main.fetch_with_retry("https://example.com/500-again")

    assert result is None
    assert len(calls) == 2


def test_run_report_exists_and_contains_required_fields(temp_output_dir, monkeypatch):
    urls = [f"https://books.toscrape.com/catalogue/book-{i}_index.html" for i in range(1, 5)]

    def fake_fetch_with_retry(url, *, stats=None):
        return _build_valid_html(int(url.rsplit("-", 1)[1].split("_", 1)[0]))

    monkeypatch.setattr(main, "fetch_with_retry", fake_fetch_with_retry)
    main.run_scraper(urls)

    report_path = temp_output_dir / "run-report.json"
    assert report_path.exists()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    required = {"start_time", "duration", "pages_fetched", "cache_hits", "valid_records", "invalid_records", "failed_pages"}
    assert required.issubset(report)


def test_stage4_successful_run_keeps_60_valid_records(temp_output_dir, monkeypatch):
    urls = [f"https://books.toscrape.com/catalogue/book-{i}_index.html" for i in range(1, 61)]

    def fake_fetch_with_retry(url, *, stats=None):
        return _build_valid_html(int(url.rsplit("-", 1)[1].split("_", 1)[0]))

    monkeypatch.setattr(main, "fetch_with_retry", fake_fetch_with_retry)
    main.run_scraper(urls)

    books = json.loads(main.BOOKS_FILE.read_text(encoding="utf-8"))
    assert len(books) == 60
