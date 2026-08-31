import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

try:
    import requests
except ImportError:
    print("Error: 'requests' library is required. Install it with: pip install requests")
    sys.exit(1)

# Constants
USER_AGENT = "FlyRankInternshipA9/1.0 (+https://github.com/)"
TIMEOUT_SECONDS = 5
REQUEST_DELAY_SECONDS = 0.5
TARGET_URL = "https://books.toscrape.com/"
CACHE_DIR = Path(__file__).parent.parent / "cache"
CACHE_FILE = CACHE_DIR / "catalogue-page-1.html"


def cache_file_for_url(url: str) -> Path:
    """Return the cache filename for a URL using the same local cache layout."""
    parsed = urlparse(url)
    path = parsed.path.lstrip("/").rstrip("/")
    if not path:
        return CACHE_DIR / "catalogue-page-1.html"

    if path.endswith("/index.html"):
        path = path[: -len("/index.html")]
    elif path.endswith("index.html"):
        path = path[: -len("index.html")]

    if not path:
        return CACHE_DIR / "catalogue-page-1.html"

    normalised = path.replace("/", "-")
    if not normalised.endswith(".html"):
        normalised = f"{normalised}.html"
    return CACHE_DIR / normalised


def cache_metadata_file_for_url(url: str) -> Path:
    """Return the metadata sidecar filename for a cached URL."""
    return cache_file_for_url(url).with_suffix(".meta.json")


def load_cache_metadata(url: str) -> str | None:
    """Load the cached fetch timestamp metadata for a URL when present."""
    metadata_file = cache_metadata_file_for_url(url)
    if not metadata_file.exists():
        return None

    try:
        payload = json.loads(metadata_file.read_text(encoding="utf-8"))
        return payload.get("fetched_at")
    except Exception:
        return None


def fetch_page(url: str) -> str | None:
    """Fetch a page or load it from the local cache with polite request spacing."""
    cached_content = load_from_cache(url)
    if cached_content is not None:
        return cached_content

    time.sleep(REQUEST_DELAY_SECONDS)

    try:
        headers = {"User-Agent": USER_AGENT}
        response = requests.get(url, headers=headers, timeout=TIMEOUT_SECONDS)

        if response.status_code == 200:
            save_to_cache(url, response.text)
            return response.text
        print(f"Error: HTTP {response.status_code}")
        return None
    except requests.exceptions.Timeout:
        print(f"Error: Request timed out after {TIMEOUT_SECONDS} seconds")
        return None
    except requests.exceptions.RequestException as e:
        print(f"Error: Network error - {e}")
        return None


def load_from_cache(url: str | None = None) -> str | None:
    """Load the cached HTML file for a URL when available."""
    cache_file = cache_file_for_url(url) if url is not None else CACHE_FILE
    if cache_file.exists():
        try:
            return cache_file.read_text(encoding="utf-8")
        except Exception as e:
            print(f"Error: Could not read cache file - {e}")
            return None
    return None


def save_to_cache(url: str | None, content: str) -> bool:
    """Save the HTML content and fetch timestamp metadata to the matching cache file."""
    try:
        cache_file = cache_file_for_url(url) if url is not None else CACHE_FILE
        metadata_file = cache_metadata_file_for_url(url) if url is not None else CACHE_FILE.with_suffix(".meta.json")
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(content, encoding="utf-8")
        fetched_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        metadata_file.write_text(json.dumps({"fetched_at": fetched_at}, ensure_ascii=False), encoding="utf-8")
        return True
    except Exception as e:
        print(f"Error: Could not write cache file - {e}")
        return False


def make_absolute_url(page_url: str, href: str) -> str:
    """Convert a relative href into an absolute URL using urljoin."""
    return urljoin(page_url, href)


def extract_book_urls(page_html: str, page_url: str) -> list[str]:
    """Parse a catalogue page and extract each book's absolute URL."""
    soup = BeautifulSoup(page_html, "html.parser")
    urls: list[str] = []
    for anchor in soup.select("article.product_pod h3 a[href]"):
        href = anchor.get("href")
        if href:
            urls.append(make_absolute_url(page_url, href))
    return urls


def find_next_page_url(page_html: str, page_url: str) -> str | None:
    """Find the catalogue's next pagination URL using the site's next link."""
    soup = BeautifulSoup(page_html, "html.parser")
    next_anchor = soup.select_one("li.next a[href]")
    if next_anchor is None:
        return None
    href = next_anchor.get("href")
    if not href:
        return None
    return make_absolute_url(page_url, href)


def deduplicate_urls(urls: list[str]) -> list[str]:
    """Deduplicate while preserving order."""
    seen: set[str] = set()
    ordered: list[str] = []
    for url in urls:
        if url not in seen:
            seen.add(url)
            ordered.append(url)
    return ordered


def discover_catalogue_pages(start_url: str = TARGET_URL, max_pages: int = 3) -> dict[str, int | list[str]]:
    """Follow the catalogue's next link and collect all book URLs from the first pages."""
    current_url = start_url
    visited_pages = 0
    discovered_urls: list[str] = []

    while visited_pages < max_pages:
        page_html = fetch_page(current_url)
        if page_html is None:
            raise RuntimeError(f"Unable to fetch catalogue page: {current_url}")

        discovered_urls.extend(extract_book_urls(page_html, current_url))
        visited_pages += 1

        if visited_pages >= max_pages:
            break

        next_url = find_next_page_url(page_html, current_url)
        if not next_url:
            break
        current_url = next_url

    unique_urls = deduplicate_urls(discovered_urls)
    return {
        "catalogue_pages": visited_pages,
        "discovered": len(discovered_urls),
        "unique_urls": len(unique_urls),
        "urls": unique_urls,
    }


def extract_book_detail_product(product_html: str) -> BeautifulSoup:
    """Return the product container for a detail page."""
    soup = BeautifulSoup(product_html, "html.parser")
    product_area = soup.select_one("article.product_page") or soup.select_one("div.product_main") or soup
    return product_area


def extract_title(product_area: BeautifulSoup) -> str | None:
    """Extract the title from the product area."""
    title_el = product_area.select_one("div.product_main h1") or product_area.select_one("h1")
    if title_el is None:
        return None
    return title_el.get_text(" ", strip=True) or None


def extract_price_text(product_area: BeautifulSoup) -> str | None:
    """Extract the product price as text from the product area."""
    price_el = product_area.select_one("p.price_color")
    if price_el is None:
        return None
    return price_el.get_text(" ", strip=True) or None


def extract_availability_text(product_area: BeautifulSoup) -> str | None:
    """Extract the availability text from the product area."""
    availability_el = product_area.select_one("p.availability") or product_area.select_one("p.instock.availability")
    if availability_el is None:
        return None
    text = availability_el.get_text(" ", strip=True)
    return text or None


def extract_rating_text(product_area: BeautifulSoup) -> str | None:
    """Extract the product rating text from the appropriate rating element."""
    rating_el = product_area.select_one("p.star-rating")
    if rating_el is None:
        return None
    classes = rating_el.get("class", [])
    for value in classes:
        if value.lower() in {"one", "two", "three", "four", "five"}:
            return value.title()
    return None


def extract_description(product_area: BeautifulSoup) -> str | None:
    """Extract the product description from the product area if present."""
    description_heading = product_area.select_one("#product_description")
    if description_heading is None:
        return None

    description_paragraph = description_heading.find_next("p")
    if description_paragraph is None:
        return None

    text = description_paragraph.get_text(" ", strip=True)
    return text or None


def extract_detail_record(product_url: str, product_html: str, source_page: str, fetched_at: str | None = None) -> dict[str, str | None]:
    """Create one raw record for a single book detail page."""
    product_area = extract_book_detail_product(product_html)
    resolved_fetched_at = fetched_at or load_cache_metadata(product_url) or datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return {
        "title": extract_title(product_area),
        "product_url": product_url,
        "price_text": extract_price_text(product_area),
        "availability_text": extract_availability_text(product_area),
        "rating_text": extract_rating_text(product_area),
        "description": extract_description(product_area),
        "source_page": source_page,
        "fetched_at": resolved_fetched_at,
    }


def extract_book_details(source_result: dict[str, int | list[str]]) -> list[dict[str, str | None]]:
    """Fetch, parse, and return raw records for every discovered book URL."""
    urls = source_result.get("urls", [])
    detail_records: list[dict[str, str | None]] = []

    for product_url in urls:
        product_html = fetch_page(product_url)
        if product_html is None:
            raise RuntimeError(f"Unable to fetch detail page: {product_url}")

        source_page = source_result.get("source_pages", {}).get(product_url, "") if isinstance(source_result.get("source_pages"), dict) else ""
        if not source_page:
            source_page = TARGET_URL

        fetched_at = load_cache_metadata(product_url)
        detail_records.append(extract_detail_record(product_url, product_html, source_page, fetched_at=fetched_at))

    return detail_records


def main() -> None:
    """Entry point for the polite scraper project."""
    cached_content = load_from_cache(TARGET_URL)

    if cached_content is not None:
        cache_size = len(cached_content.encode("utf-8"))
        print(f"CACHE HIT — loaded catalogue page ({cache_size} bytes)")
    else:
        fetched_content = fetch_page(TARGET_URL)
        if fetched_content is not None:
            content_size = len(fetched_content.encode("utf-8"))
            print(f"FETCH — saved catalogue page ({content_size} bytes)")
        else:
            print("Error: Failed to fetch the page")
            sys.exit(1)

    result = discover_catalogue_pages(TARGET_URL, max_pages=3)
    print(f"catalogue_pages={result['catalogue_pages']}")
    print(f"discovered={result['discovered']}")
    print(f"unique_urls={result['unique_urls']}")

    source_pages: dict[str, str] = {}
    current_url = TARGET_URL
    for _ in range(3):
        page_html = fetch_page(current_url)
        if page_html is None:
            break

        for book_url in extract_book_urls(page_html, current_url):
            source_pages.setdefault(book_url, current_url)

        next_url = find_next_page_url(page_html, current_url)
        if next_url is None:
            break
        current_url = next_url

    result_with_sources = {**result, "source_pages": source_pages}
    detail_records = extract_book_details(result_with_sources)
    print(f"detail_pages={len(detail_records)}")
    if detail_records:
        print(detail_records[0])


if __name__ == "__main__":
    main()
