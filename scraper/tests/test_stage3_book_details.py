import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

import src.main as main


SAMPLE_DETAIL_HTML = """
<article class="product_page">
  <div class="product_main">
    <h1>Example Book</h1>
    <p class="price_color">£12.34</p>
    <p class="instock availability">In stock (7 available)</p>
    <p class="star-rating Three">
      <i class="icon-star"></i>
      <i class="icon-star"></i>
      <i class="icon-star"></i>
    </p>
  </div>
  <div class="sub-header" id="product_description">
    <h2>Product Description</h2>
  </div>
  <p>Detailed summary for this example book.</p>
</article>
"""


def test_record_contains_all_eight_keys():
    record = main.extract_detail_record(
        "https://books.toscrape.com/catalogue/example-book_1/index.html",
        SAMPLE_DETAIL_HTML,
        "https://books.toscrape.com/catalogue/page-1.html",
    )

    assert set(record.keys()) == {
        "title",
        "product_url",
        "price_text",
        "availability_text",
        "rating_text",
        "description",
        "source_page",
        "fetched_at",
    }

    datetime.fromisoformat(record["fetched_at"].replace("Z", "+00:00"))


def test_title_price_availability_and_rating_are_extracted():
    record = main.extract_detail_record(
        "https://books.toscrape.com/catalogue/example-book_1/index.html",
        SAMPLE_DETAIL_HTML,
        "https://books.toscrape.com/catalogue/page-1.html",
    )

    assert record["title"] == "Example Book"
    assert record["price_text"] == "£12.34"
    assert record["availability_text"] == "In stock (7 available)"
    assert record["rating_text"] == "Three"


def test_missing_description_returns_none():
    html = """
    <article class="product_page">
      <div class="product_main">
        <h1>Another Book</h1>
        <p class="price_color">£8.99</p>
        <p class="instock availability">In stock (3 available)</p>
        <p class="star-rating One"></p>
      </div>
    </article>
    """

    record = main.extract_detail_record(
        "https://books.toscrape.com/catalogue/another-book_2/index.html",
        html,
        "https://books.toscrape.com/catalogue/page-2.html",
    )

    assert record["description"] is None


def test_product_and_source_urls_are_preserved():
    record = main.extract_detail_record(
        "https://books.toscrape.com/catalogue/example-book_1/index.html",
        SAMPLE_DETAIL_HTML,
        "https://books.toscrape.com/catalogue/page-1.html",
    )

    assert record["product_url"] == "https://books.toscrape.com/catalogue/example-book_1/index.html"
    assert record["source_page"] == "https://books.toscrape.com/catalogue/page-1.html"


def test_cache_uses_existing_detail_page_and_skips_network(monkeypatch, tmp_path):
    product_url = "https://books.toscrape.com/catalogue/example-book_1/index.html"
    monkeypatch.setattr(main, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(main, "CACHE_FILE", tmp_path / "catalogue-page-1.html")

    cache_file = main.cache_file_for_url(product_url)
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(SAMPLE_DETAIL_HTML, encoding="utf-8")
    main.cache_metadata_file_for_url(product_url).write_text('{"fetched_at": "2026-08-31T10:00:00Z"}', encoding="utf-8")

    sleep_calls = []
    monkeypatch.setattr(main.time, "sleep", lambda seconds: sleep_calls.append(seconds))

    def boom(*args, **kwargs):
        raise AssertionError("Network request should not occur when detail page is cached")

    monkeypatch.setattr(main.requests, "get", boom)

    record = main.extract_detail_record(product_url, main.fetch_page(product_url), "https://books.toscrape.com/catalogue/page-1.html")

    assert record["title"] == "Example Book"
    assert record["fetched_at"] == "2026-08-31T10:00:00Z"
    assert sleep_calls == []
