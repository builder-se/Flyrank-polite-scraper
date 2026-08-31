import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import src.main as main


def build_valid_html(index: int) -> str:
    return f'''
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
    '''


urls = [f'https://books.toscrape.com/catalogue/book-{i}_index.html' for i in range(1, 61)]
urls.append('https://example.invalid/fake-book-for-stage5')


def fake_fetch_with_retry(url, *, stats=None):
    if url.endswith('fake-book-for-stage5'):
        return None
    return build_valid_html(int(url.rsplit('-', 1)[1].split('_', 1)[0]))


main.fetch_with_retry = fake_fetch_with_retry
main.discover_catalogue_pages = lambda *args, **kwargs: {
    'catalogue_pages': 3,
    'discovered': 60,
    'unique_urls': 60,
    'urls': urls,
}

report = main.run_scraper(urls)
books = json.loads(main.BOOKS_FILE.read_text(encoding='utf-8'))

print('VALID_RECORDS', report['valid_records'])
print('FAILED_PAGES', report['failed_pages'])
print('BOOK_COUNT', len(books))
print('FAKE_PRESENT', any(book['product_url'] == 'https://example.invalid/fake-book-for-stage5' for book in books))
print(json.dumps(report, indent=2, sort_keys=True))
