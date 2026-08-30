import sys
from pathlib import Path

try:
    import requests
except ImportError:
    print("Error: 'requests' library is required. Install it with: pip install requests")
    sys.exit(1)

# Constants
USER_AGENT = "FlyRankInternshipA9/1.0 (+https://github.com/)"
TIMEOUT_SECONDS = 5
TARGET_URL = "https://books.toscrape.com/"
CACHE_DIR = Path(__file__).parent.parent / "cache"
CACHE_FILE = CACHE_DIR / "catalogue-page-1.html"


def fetch_page(url: str) -> str | None:
    """
    Fetch the webpage from the given URL.
    
    Returns:
        The HTML content if successful (status 200), None otherwise.
    """
    try:
        headers = {"User-Agent": USER_AGENT}
        response = requests.get(url, headers=headers, timeout=TIMEOUT_SECONDS)
        
        if response.status_code == 200:
            return response.text
        else:
            print(f"Error: HTTP {response.status_code}")
            return None
    except requests.exceptions.Timeout:
        print(f"Error: Request timed out after {TIMEOUT_SECONDS} seconds")
        return None
    except requests.exceptions.RequestException as e:
        print(f"Error: Network error - {e}")
        return None


def load_from_cache() -> str | None:
    """
    Load the cached HTML file.
    
    Returns:
        The HTML content if the cache file exists, None otherwise.
    """
    if CACHE_FILE.exists():
        try:
            return CACHE_FILE.read_text(encoding="utf-8")
        except Exception as e:
            print(f"Error: Could not read cache file - {e}")
            return None
    return None


def save_to_cache(content: str) -> bool:
    """
    Save the HTML content to the cache file.
    
    Returns:
        True if successful, False otherwise.
    """
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        CACHE_FILE.write_text(content, encoding="utf-8")
        return True
    except Exception as e:
        print(f"Error: Could not write cache file - {e}")
        return False


def main() -> None:
    """Entry point for the polite scraper project."""
    # Try to load from cache first
    cached_content = load_from_cache()
    
    if cached_content is not None:
        # Cache hit
        cache_size = len(cached_content.encode("utf-8"))
        print(f"CACHE HIT — loaded catalogue page ({cache_size} bytes)")
    else:
        # Cache miss - fetch from network
        fetched_content = fetch_page(TARGET_URL)
        
        if fetched_content is not None:
            # Save to cache
            if save_to_cache(fetched_content):
                content_size = len(fetched_content.encode("utf-8"))
                print(f"FETCH — saved catalogue page ({content_size} bytes)")
            else:
                print("Error: Failed to save to cache")
                sys.exit(1)
        else:
            print("Error: Failed to fetch the page")
            sys.exit(1)


if __name__ == "__main__":
    main()
