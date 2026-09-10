import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from pydantic import BaseModel, Field, HttpUrl, field_validator

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
OUTPUT_DIR = Path(__file__).parent.parent / "output"
BOOKS_FILE = OUTPUT_DIR / "books.json"
ERRORS_FILE = OUTPUT_DIR / "errors.json"
RUN_REPORT_FILE = OUTPUT_DIR / "runreport.json"
LEGACY_RUN_REPORT_FILE = OUTPUT_DIR / "run-report.json"


# ============================================================================
# Stage 4: Pydantic Schema and Validation
# ============================================================================


class NormalizedBook(BaseModel):
    """Validated, normalized book record with canonical URL identity."""

    title: str
    product_url: str
    price_text: str
    price_gbp: float
    availability_text: str | None = None
    rating_text: str | None = None
    description: str | None = None
    source_page: str
    fetched_at: str

    @field_validator("product_url")
    @classmethod
    def validate_https_url(cls, v: str) -> str:
        """Ensure product_url starts with https://"""
        if not v.startswith("https://"):
            raise ValueError("product_url must start with https://")
        return v


class InvalidRecord(BaseModel):
    """Record of an invalid or unparseable book entry."""

    product_url: str | None = None
    reason: str
    record: dict | None = None


def normalize_price(price_text: str) -> float | None:
    """
    Parse price_text like '£51.77' and return a numeric float value.
    
    Handles:
    - Currency prefix (£, $, €, ¥, ₹, and mojibake variants)
    - Decimal notation
    - Whitespace
    - Multiple encoding issues
    
    Returns None if parsing fails.
    """
    if not price_text:
        return None
    
    # Extract all digits and dots/commas using regex
    # This is more robust than trying to list all currency symbols
    cleaned = price_text.strip()
    
    # Try to extract a number pattern: optional minus, digits, optional decimal
    match = re.search(r'-?\d+[.,]\d+|-?\d+', cleaned)
    if not match:
        return None
    
    number_str = match.group(0).replace(',', '.')  # Handle comma decimals
    
    try:
        return float(number_str)
    except (ValueError, TypeError):
        return None


def normalize_record(raw_record: dict[str, str | None]) -> NormalizedBook | None:
    """
    Normalize a raw Stage 3 record into a validated NormalizedBook.
    
    Returns the NormalizedBook on success, None on failure.
    Caller is responsible for error handling.
    """
    try:
        product_url = raw_record.get("product_url")
        price_text = raw_record.get("price_text")
        
        if not product_url:
            return None
        
        if not price_text:
            return None
        
        price_gbp = normalize_price(price_text)
        if price_gbp is None:
            return None
        
        normalized = NormalizedBook(
            title=raw_record.get("title") or "Untitled",
            product_url=product_url,
            price_text=price_text,
            price_gbp=price_gbp,
            availability_text=raw_record.get("availability_text"),
            rating_text=raw_record.get("rating_text"),
            description=raw_record.get("description"),
            source_page=raw_record.get("source_page") or "unknown",
            fetched_at=raw_record.get("fetched_at") or datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        )
        return normalized
    except Exception:
        return None


def validate_and_normalize_records(
    raw_records: list[dict[str, str | None]],
) -> tuple[list[NormalizedBook], list[dict]]:
    """
    Process all raw Stage 3 records through normalization and validation.
    
    Returns:
      (valid_books, errors)
    
    - valid_books: List of NormalizedBook objects (deduplicated by product_url)
    - errors: List of error dicts with product_url, reason, and optional record
    """
    valid_books: list[NormalizedBook] = []
    errors: list[dict] = []
    seen_urls: set[str] = set()
    
    for raw_record in raw_records:
        product_url = raw_record.get("product_url")
        
        # Check for duplicates
        if product_url and product_url in seen_urls:
            errors.append({
                "product_url": product_url,
                "reason": "Duplicate product_url (deduplicated)",
                "record": raw_record,
            })
            continue
        
        # Normalize
        normalized = normalize_record(raw_record)
        if normalized is None:
            errors.append({
                "product_url": product_url,
                "reason": "Failed to normalize record (invalid price or missing required fields)",
                "record": raw_record,
            })
            continue
        
        # Pydantic validation happens in NormalizedBook.__init__
        # If we get here, the record is valid
        if product_url:
            seen_urls.add(product_url)
        valid_books.append(normalized)
    
    return valid_books, errors


def write_output_files(valid_books: list[NormalizedBook], errors: list[dict]) -> None:
    """Write validated books and errors to output JSON files."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    # Write books.json
    books_data = [book.model_dump(mode="python") for book in valid_books]
    BOOKS_FILE.write_text(
        json.dumps(books_data, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    
    # Write errors.json
    ERRORS_FILE.write_text(
        json.dumps(errors, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def cache_file_for_url(url: str) -> Path:
    """Return the cache filename for a URL using the same local cache layout."""
    parsed = urlparse(url)
    host = parsed.netloc or "local"
    path = parsed.path.lstrip("/").rstrip("/")
    if not path:
        return CACHE_DIR / ("catalogue-page-1.html" if host == "books.toscrape.com" else f"{host.replace(':', '_')}-catalogue-page-1.html")

    if path.endswith("/index.html"):
        path = path[: -len("/index.html")]
    elif path.endswith("index.html"):
        path = path[: -len("index.html")]

    if not path:
        return CACHE_DIR / ("catalogue-page-1.html" if host == "books.toscrape.com" else f"{host.replace(':', '_')}-catalogue-page-1.html")

    normalised = path.replace("/", "-")
    if host != "books.toscrape.com":
        normalised = f"{host.replace(':', '_')}-{normalised}"
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


def fetch_with_retry(url: str, *, stats: dict | None = None) -> str | None:
    """Fetch a page with a single retry for timeouts and transient 5xx errors."""
    should_use_cache = url.startswith("https://books.toscrape.com") or url.startswith("http://books.toscrape.com")
    cached_content = load_from_cache(url) if should_use_cache else None
    if cached_content is not None:
        if stats is not None:
            stats["cache_hits"] = stats.get("cache_hits", 0) + 1
        return cached_content

    for attempt in range(1, 3):
        try:
            time.sleep(REQUEST_DELAY_SECONDS)
            headers = {"User-Agent": USER_AGENT}
            response = requests.get(url, headers=headers, timeout=TIMEOUT_SECONDS)
        except requests.exceptions.Timeout:
            if attempt == 1:
                continue
            print(f"Error: Request timed out after {TIMEOUT_SECONDS} seconds")
            return None
        except requests.exceptions.RequestException as e:
            print(f"Error: Network error - {e}")
            return None

        if response.status_code == 200:
            save_to_cache(url, response.text)
            if stats is not None:
                stats["pages_fetched"] = stats.get("pages_fetched", 0) + 1
            return response.text

        if 500 <= response.status_code < 600:
            if attempt == 1:
                continue
            print(f"Error: HTTP {response.status_code}")
            return None

        if response.status_code in {403, 404}:
            print(f"Error: HTTP {response.status_code}")
            return None

        print(f"Error: HTTP {response.status_code}")
        return None

    return None


def fetch_page(url: str) -> str | None:
    """Fetch a page or load it from the local cache with polite request spacing."""
    return fetch_with_retry(url)


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


def discover_catalogue_pages(start_url: str = TARGET_URL, max_pages: int = 3, stats: dict | None = None) -> dict[str, int | list[str]]:
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


def extract_book_details(source_result: dict[str, int | list[str]], stats: dict | None = None) -> list[dict[str, str | None]]:
    """Fetch, parse, and return raw records for every discovered book URL."""
    urls = source_result.get("urls", [])
    detail_records: list[dict[str, str | None]] = []

    for product_url in urls:
        product_html = fetch_with_retry(product_url, stats=stats)
        if product_html is None:
            continue

        source_page = source_result.get("source_pages", {}).get(product_url, "") if isinstance(source_result.get("source_pages"), dict) else ""
        if not source_page:
            source_page = TARGET_URL

        fetched_at = load_cache_metadata(product_url)
        detail_records.append(extract_detail_record(product_url, product_html, source_page, fetched_at=fetched_at))

    return detail_records


def process_book(product_url: str, *, source_page: str = TARGET_URL, stats: dict | None = None) -> tuple[NormalizedBook | None, dict | None]:
    """Fetch, parse, and validate a single book page without terminating the overall run."""
    try:
        product_html = fetch_with_retry(product_url, stats=stats)
        if product_html is None:
            return None, {
                "product_url": product_url,
                "reason": "Failed to fetch detail page after retry policy",
                "record": None,
            }

        fetched_at = load_cache_metadata(product_url)
        raw_record = extract_detail_record(product_url, product_html, source_page, fetched_at=fetched_at)
        normalized = normalize_record(raw_record)
        if normalized is None:
            return None, {
                "product_url": product_url,
                "reason": "Failed to normalize record (invalid price or missing required fields)",
                "record": raw_record,
            }
        return normalized, None
    except (requests.exceptions.RequestException, TimeoutError, TypeError, ValueError, AttributeError, IndexError):
        return None, {
            "product_url": product_url,
            "reason": "Expected page/parsing/validation failure while processing book",
            "record": None,
        }


def write_run_report(report: dict, report_path: str | Path | None = None) -> None:
    """Persist the run summary to disk as valid JSON in both canonical and legacy filenames."""
    default_path = Path(report_path) if report_path is not None else OUTPUT_DIR / "runreport.json"
    target_paths = [default_path]
    if default_path.name == "runreport.json":
        target_paths.append(OUTPUT_DIR / "run-report.json")
    elif default_path.name == "run-report.json":
        target_paths.append(OUTPUT_DIR / "runreport.json")

    for path in dict.fromkeys(target_paths):
        resolved_path = Path(path)
        resolved_path.parent.mkdir(parents=True, exist_ok=True)
        resolved_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def run_scraper(urls: list[str] | None = None) -> dict:
    """Run the scraper over a list of book URLs, tolerating one failed page."""
    started_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    start_monotonic = time.perf_counter()
    stats = {"pages_fetched": 0, "cache_hits": 0}

    if urls is None:
        result = discover_catalogue_pages(TARGET_URL, max_pages=3, stats=stats)
        urls = result.get("urls", [])

    valid_books: list[NormalizedBook] = []
    errors: list[dict] = []
    failed_pages = 0
    invalid_records = 0

    for product_url in urls:
        try:
            normalized, error = process_book(product_url, source_page=TARGET_URL, stats=stats)
            if normalized is not None:
                valid_books.append(normalized)
                continue
            if error is not None:
                errors.append(error)
                if "Failed to normalize record" in error.get("reason", ""):
                    invalid_records += 1
                else:
                    failed_pages += 1
        except (TypeError, ValueError):
            errors.append({
                "product_url": product_url,
                "reason": "Unexpected record-processing failure",
                "record": None,
            })
            failed_pages += 1

    write_output_files(valid_books, errors)

    report = {
        "start_time": started_at,
        "duration": round(time.perf_counter() - start_monotonic, 3),
        "pages_fetched": stats.get("pages_fetched", 0),
        "cache_hits": stats.get("cache_hits", 0),
        "valid_records": len(valid_books),
        "invalid_records": invalid_records,
        "failed_pages": failed_pages,
    }
    write_run_report(report, OUTPUT_DIR / "runreport.json")
    return report


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

    stats = {"pages_fetched": 0, "cache_hits": 0}
    result = discover_catalogue_pages(TARGET_URL, max_pages=3, stats=stats)
    print(f"catalogue_pages={result['catalogue_pages']}")
    print(f"discovered={result['discovered']}")
    print(f"unique_urls={result['unique_urls']}")

    source_pages: dict[str, str] = {}
    current_url = TARGET_URL
    for _ in range(3):
        page_html = fetch_with_retry(current_url, stats=stats)
        if page_html is None:
            break

        for book_url in extract_book_urls(page_html, current_url):
            source_pages.setdefault(book_url, current_url)

        next_url = find_next_page_url(page_html, current_url)
        if next_url is None:
            break
        current_url = next_url

    result_with_sources = {**result, "source_pages": source_pages}
    detail_records = extract_book_details(result_with_sources, stats=stats)
    print(f"detail_pages={len(detail_records)}")

    # ========================================================================
    # Stage 4: Normalize and Validate Records
    # ========================================================================
    valid_books, errors = validate_and_normalize_records(detail_records)
    write_output_files(valid_books, errors)

    report = {
        "start_time": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "duration": 0.0,
        "pages_fetched": stats.get("pages_fetched", 0),
        "cache_hits": stats.get("cache_hits", 0),
        "valid_records": len(valid_books),
        "invalid_records": len(errors),
        "failed_pages": 0,
    }
    write_run_report(report, RUN_REPORT_FILE)

    # Print checkpoint summary
    print(f"valid_records={len(valid_books)}")
    print(f"invalid_records={len(errors)}")
    print(f"unique_records={len(valid_books)}")

    if valid_books:
        print(f"Sample normalized record:")
        print(valid_books[0].model_dump())


if __name__ == "__main__":
    main()
