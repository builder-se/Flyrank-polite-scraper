import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from src.main import (
    discover_catalogue_pages,
    deduplicate_urls,
    fetch_page,
    find_next_page_url,
    make_absolute_url,
)


@pytest.fixture
def sample_catalogue_html():
    return """
    <html>
      <body>
        <ol class="row">
          <li class="col-xs-6 col-sm-4 col-md-3 col-lg-3">
            <article class="product_pod">
              <h3><a href="catalogue/book-1/index.html">Book 1</a></h3>
            </article>
          </li>
          <li class="col-xs-6 col-sm-4 col-md-3 col-lg-3">
            <article class="product_pod">
              <h3><a href="catalogue/book-2/index.html">Book 2</a></h3>
            </article>
          </li>
        </ol>
        <ul class="pager">
          <li class="next"><a href="catalogue/page-2.html">next</a></li>
        </ul>
      </body>
    </html>
    """


def test_make_absolute_url_from_relative_hrefs():
    page_url = "https://books.toscrape.com/catalogue/page-1.html"
    href = "../book-name_1/index.html"
    assert make_absolute_url(page_url, href) == "https://books.toscrape.com/book-name_1/index.html"


def test_find_next_page_url_from_catalogue_pagination(sample_catalogue_html):
    assert find_next_page_url(sample_catalogue_html, "https://books.toscrape.com/") == "https://books.toscrape.com/catalogue/page-2.html"


def test_deduplicate_urls_preserves_order():
    urls = [
        "https://books.toscrape.com/catalogue/book-1/index.html",
        "https://books.toscrape.com/catalogue/book-2/index.html",
        "https://books.toscrape.com/catalogue/book-1/index.html",
    ]
    assert deduplicate_urls(urls) == [
        "https://books.toscrape.com/catalogue/book-1/index.html",
        "https://books.toscrape.com/catalogue/book-2/index.html",
    ]


def test_discover_catalogue_pages_follows_next_links(monkeypatch):
    def fake_fetch(url: str):
        page_map = {
            "https://books.toscrape.com/": """
            <html><body>
            <ol class="row">
              <li><article class="product_pod"><h3><a href="catalogue/book-1/index.html">Book 1</a></h3></article></li>
              <li><article class="product_pod"><h3><a href="catalogue/book-2/index.html">Book 2</a></h3></article></li>
              ...
            </ol>
            <ul class="pager"><li class="next"><a href="catalogue/page-2.html">next</a></li></ul>
            </body></html>
            """,
            "https://books.toscrape.com/catalogue/page-2.html": """
            <html><body>
            <ol class="row">
              <li><article class="product_pod"><h3><a href="catalogue/book-3/index.html">Book 3</a></h3></article></li>
              <li><article class="product_pod"><h3><a href="catalogue/book-4/index.html">Book 4</a></h3></article></li>
              ...
            </ol>
            <ul class="pager"><li class="next"><a href="page-3.html">next</a></li></ul>
            </body></html>
            """,
            "https://books.toscrape.com/catalogue/page-3.html": """
            <html><body>
            <ol class="row">
              <li><article class="product_pod"><h3><a href="catalogue/book-5/index.html">Book 5</a></h3></article></li>
              <li><article class="product_pod"><h3><a href="catalogue/book-6/index.html">Book 6</a></h3></article></li>
              ...
            </ol>
            </body></html>
            """,
        }
        if url not in page_map:
            raise AssertionError(f"Unexpected URL: {url}")
        return page_map[url]

    monkeypatch.setattr("src.main.fetch_page", fake_fetch)

    result = discover_catalogue_pages("https://books.toscrape.com/", max_pages=3)

    assert result["catalogue_pages"] == 3
    assert result["discovered"] == 6
    assert result["unique_urls"] == 6


def test_fetch_page_uses_cache_without_sleep(monkeypatch, tmp_path):
    import src.main as main

    cache_path = tmp_path / "catalogue-page-1.html"
    cache_path.write_text("<html><body>cached</body></html>", encoding="utf-8")

    monkeypatch.setattr(main, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(main, "CACHE_FILE", cache_path)
    monkeypatch.setattr(main, "TARGET_URL", "https://books.toscrape.com/")

    sleep_calls = []
    monkeypatch.setattr(main.time, "sleep", lambda seconds: sleep_calls.append(seconds))

    def boom(*args, **kwargs):
        raise AssertionError("Network request should not happen when cache is available")

    monkeypatch.setattr(main.requests, "get", boom)

    content = fetch_page("https://books.toscrape.com/")

    assert content == "<html><body>cached</body></html>"
    assert sleep_calls == []
