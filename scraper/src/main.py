import sys
import time
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
    """Save the HTML content to the matching cache file."""
    try:
        cache_file = cache_file_for_url(url) if url is not None else CACHE_FILE
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(content, encoding="utf-8")
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


if __name__ == "__main__":
    main()
