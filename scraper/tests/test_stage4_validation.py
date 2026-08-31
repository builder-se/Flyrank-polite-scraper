import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from src.main import (
    NormalizedBook,
    InvalidRecord,
    normalize_price,
    normalize_record,
    validate_and_normalize_records,
    write_output_files,
)


class TestPriceNormalization:
    """Test price normalization from text to float."""

    def test_gbp_price_with_pound_symbol(self):
        """Test converting '£51.77' to 51.77"""
        result = normalize_price("£51.77")
        assert result == 51.77
        assert isinstance(result, float)

    def test_gbp_price_with_mojibake_encoding(self):
        """Test handling mojibake encoding like 'Â£51.77'"""
        result = normalize_price("Â£51.77")
        assert result == 51.77
        assert isinstance(result, float)

    def test_gbp_price_with_whitespace(self):
        """Test handling whitespace around price"""
        result = normalize_price("  £51.77  ")
        assert result == 51.77

    def test_usd_price_with_dollar_symbol(self):
        """Test converting '$12.34' to 12.34"""
        result = normalize_price("$12.34")
        assert result == 12.34

    def test_euro_price_with_euro_symbol(self):
        """Test converting '€99.99' to 99.99"""
        result = normalize_price("€99.99")
        assert result == 99.99

    def test_price_with_multiple_symbols(self):
        """Test price with both symbol and whitespace"""
        result = normalize_price("  £  51.77  ")
        # The regex will find 51.77 even with spaces
        assert result == 51.77

    def test_invalid_price_returns_none(self):
        """Test that non-numeric price returns None"""
        result = normalize_price("not-a-price")
        assert result is None

    def test_empty_price_returns_none(self):
        """Test that empty string returns None"""
        result = normalize_price("")
        assert result is None

    def test_none_price_returns_none(self):
        """Test that None returns None"""
        result = normalize_price(None)
        assert result is None

    def test_price_with_single_number(self):
        """Test handling prices without decimals"""
        result = normalize_price("£10")
        assert result == 10.0


class TestRawValuePreservation:
    """Test that raw values are preserved alongside normalized values."""

    def test_price_text_and_gbp_both_present(self):
        """Verify price_text raw value preserved alongside normalized price_gbp"""
        raw_record = {
            "title": "Test Book",
            "product_url": "https://books.toscrape.com/catalogue/test-book_1/index.html",
            "price_text": "£51.77",
            "availability_text": "In stock",
            "rating_text": "Four",
            "description": "A test book",
            "source_page": "https://books.toscrape.com/",
            "fetched_at": "2026-08-31T10:00:00Z",
        }
        
        normalized = normalize_record(raw_record)
        
        assert normalized is not None
        assert normalized.price_text == "£51.77"
        assert normalized.price_gbp == 51.77
        assert isinstance(normalized.price_gbp, float)


class TestURLValidation:
    """Test URL validation and canonicalization."""

    def test_https_url_passes_validation(self):
        """Verify valid HTTPS URL passes Pydantic validation"""
        book = NormalizedBook(
            title="Test",
            product_url="https://books.toscrape.com/catalogue/test_1/index.html",
            price_text="£12.00",
            price_gbp=12.00,
            source_page="https://books.toscrape.com/",
            fetched_at="2026-08-31T10:00:00Z",
        )
        assert book.product_url.startswith("https://")

    def test_http_url_fails_validation(self):
        """Verify HTTP URLs are rejected"""
        with pytest.raises(ValueError):
            NormalizedBook(
                title="Test",
                product_url="http://books.toscrape.com/catalogue/test_1/index.html",
                price_text="£12.00",
                price_gbp=12.00,
                source_page="https://books.toscrape.com/",
                fetched_at="2026-08-31T10:00:00Z",
            )

    def test_relative_url_fails_validation(self):
        """Verify relative URLs are rejected"""
        with pytest.raises(ValueError):
            NormalizedBook(
                title="Test",
                product_url="catalogue/test_1/index.html",
                price_text="£12.00",
                price_gbp=12.00,
                source_page="https://books.toscrape.com/",
                fetched_at="2026-08-31T10:00:00Z",
            )


class TestPydanticValidation:
    """Test that Pydantic validation works correctly."""

    def test_valid_record_passes_validation(self):
        """Verify a complete valid record passes all Pydantic checks"""
        book = NormalizedBook(
            title="Example Book",
            product_url="https://books.toscrape.com/catalogue/example-book_1/index.html",
            price_text="£51.77",
            price_gbp=51.77,
            availability_text="In stock (7 available)",
            rating_text="Three",
            description="A detailed description",
            source_page="https://books.toscrape.com/",
            fetched_at="2026-08-31T10:00:00Z",
        )
        assert book.title == "Example Book"
        assert book.price_gbp == 51.77

    def test_required_fields_present(self):
        """Verify that all required fields are present in schema"""
        book = NormalizedBook(
            title="Test",
            product_url="https://books.toscrape.com/test_1/index.html",
            price_text="£10.00",
            price_gbp=10.00,
            source_page="https://books.toscrape.com/",
            fetched_at="2026-08-31T10:00:00Z",
        )
        assert book.title is not None
        assert book.product_url is not None
        assert book.price_gbp is not None

    def test_missing_required_field_fails(self):
        """Verify that missing required fields cause validation error"""
        with pytest.raises(Exception):
            NormalizedBook(
                title="Test",
                # product_url missing!
                price_text="£10.00",
                price_gbp=10.00,
                source_page="https://books.toscrape.com/",
                fetched_at="2026-08-31T10:00:00Z",
            )


class TestOptionalDescription:
    """Test that optional description field works correctly."""

    def test_description_can_be_none(self):
        """Verify that description can be None"""
        book = NormalizedBook(
            title="Test",
            product_url="https://books.toscrape.com/test_1/index.html",
            price_text="£10.00",
            price_gbp=10.00,
            description=None,
            source_page="https://books.toscrape.com/",
            fetched_at="2026-08-31T10:00:00Z",
        )
        assert book.description is None

    def test_description_can_be_string(self):
        """Verify that description can be a string"""
        book = NormalizedBook(
            title="Test",
            product_url="https://books.toscrape.com/test_1/index.html",
            price_text="£10.00",
            price_gbp=10.00,
            description="A meaningful description",
            source_page="https://books.toscrape.com/",
            fetched_at="2026-08-31T10:00:00Z",
        )
        assert book.description == "A meaningful description"


class TestNormalizationFunction:
    """Test the normalize_record function."""

    def test_normalize_complete_record(self):
        """Test normalizing a complete raw record"""
        raw = {
            "title": "Sapiens",
            "product_url": "https://books.toscrape.com/catalogue/sapiens_1/index.html",
            "price_text": "£45.00",
            "availability_text": "In stock",
            "rating_text": "Four",
            "description": "A history of humankind",
            "source_page": "https://books.toscrape.com/",
            "fetched_at": "2026-08-31T10:00:00Z",
        }
        
        normalized = normalize_record(raw)
        
        assert normalized is not None
        assert normalized.title == "Sapiens"
        assert normalized.price_gbp == 45.00
        assert isinstance(normalized.price_gbp, float)

    def test_normalize_missing_price_fails(self):
        """Test that missing price causes normalization to fail"""
        raw = {
            "title": "Test",
            "product_url": "https://books.toscrape.com/test_1/index.html",
            "price_text": None,  # Missing price!
            "source_page": "https://books.toscrape.com/",
            "fetched_at": "2026-08-31T10:00:00Z",
        }
        
        normalized = normalize_record(raw)
        assert normalized is None

    def test_normalize_missing_product_url_fails(self):
        """Test that missing product_url causes normalization to fail"""
        raw = {
            "title": "Test",
            "product_url": None,  # Missing URL!
            "price_text": "£10.00",
            "source_page": "https://books.toscrape.com/",
            "fetched_at": "2026-08-31T10:00:00Z",
        }
        
        normalized = normalize_record(raw)
        assert normalized is None

    def test_normalize_invalid_price_fails(self):
        """Test that unparseable price causes normalization to fail"""
        raw = {
            "title": "Test",
            "product_url": "https://books.toscrape.com/test_1/index.html",
            "price_text": "invalid-price-text",
            "source_page": "https://books.toscrape.com/",
            "fetched_at": "2026-08-31T10:00:00Z",
        }
        
        normalized = normalize_record(raw)
        assert normalized is None


class TestErrorHandling:
    """Test error collection and reporting."""

    def test_invalid_record_goes_to_errors(self):
        """Verify invalid records go to errors list, not books"""
        raw_records = [
            {
                "title": "Valid Book",
                "product_url": "https://books.toscrape.com/valid_1/index.html",
                "price_text": "£10.00",
                "source_page": "https://books.toscrape.com/",
                "fetched_at": "2026-08-31T10:00:00Z",
            },
            {
                "title": "Invalid Book",
                "product_url": "https://books.toscrape.com/invalid_2/index.html",
                "price_text": "not-a-price",  # Invalid!
                "source_page": "https://books.toscrape.com/",
                "fetched_at": "2026-08-31T10:00:00Z",
            },
        ]
        
        valid_books, errors = validate_and_normalize_records(raw_records)
        
        assert len(valid_books) == 1
        assert len(errors) == 1
        assert errors[0]["product_url"] == "https://books.toscrape.com/invalid_2/index.html"
        assert "reason" in errors[0]
        assert "record" in errors[0]

    def test_error_entry_contains_diagnostic_info(self):
        """Verify error entries contain product_url and reason"""
        raw_records = [
            {
                "title": "Bad Book",
                "product_url": "https://books.toscrape.com/bad_1/index.html",
                "price_text": "unknown",
                "source_page": "https://books.toscrape.com/",
                "fetched_at": "2026-08-31T10:00:00Z",
            },
        ]
        
        valid_books, errors = validate_and_normalize_records(raw_records)
        
        assert len(errors) == 1
        error = errors[0]
        assert error["product_url"] is not None
        assert error["reason"] is not None
        assert error["record"] is not None


class TestDeduplication:
    """Test deduplication by product_url."""

    def test_duplicate_product_urls_keep_first(self):
        """Verify that duplicate URLs result in only one valid record"""
        raw_records = [
            {
                "title": "Book Title",
                "product_url": "https://books.toscrape.com/duplicate_1/index.html",
                "price_text": "£10.00",
                "source_page": "https://books.toscrape.com/",
                "fetched_at": "2026-08-31T10:00:00Z",
            },
            {
                "title": "Same Book Title",
                "product_url": "https://books.toscrape.com/duplicate_1/index.html",
                "price_text": "£12.00",
                "source_page": "https://books.toscrape.com/",
                "fetched_at": "2026-08-31T10:00:01Z",
            },
        ]
        
        valid_books, errors = validate_and_normalize_records(raw_records)
        
        # Should have 1 valid and 1 duplicate error
        assert len(valid_books) == 1
        assert len(errors) == 1
        assert valid_books[0].product_url == "https://books.toscrape.com/duplicate_1/index.html"
        assert "Duplicate" in errors[0]["reason"]

    def test_different_urls_both_valid(self):
        """Verify that different URLs both pass through"""
        raw_records = [
            {
                "title": "Book 1",
                "product_url": "https://books.toscrape.com/book1_1/index.html",
                "price_text": "£10.00",
                "source_page": "https://books.toscrape.com/",
                "fetched_at": "2026-08-31T10:00:00Z",
            },
            {
                "title": "Book 2",
                "product_url": "https://books.toscrape.com/book2_2/index.html",
                "price_text": "£12.00",
                "source_page": "https://books.toscrape.com/",
                "fetched_at": "2026-08-31T10:00:00Z",
            },
        ]
        
        valid_books, errors = validate_and_normalize_records(raw_records)
        
        assert len(valid_books) == 2
        assert len(errors) == 0


class TestIdempotency:
    """Test that repeated processing produces the same results."""

    def test_processing_same_records_twice_produces_same_output(self, tmp_path):
        """Verify running validation twice on same input produces same output"""
        raw_records = [
            {
                "title": "Book A",
                "product_url": "https://books.toscrape.com/booka_1/index.html",
                "price_text": "£15.00",
                "source_page": "https://books.toscrape.com/",
                "fetched_at": "2026-08-31T10:00:00Z",
            },
            {
                "title": "Book B",
                "product_url": "https://books.toscrape.com/bookb_2/index.html",
                "price_text": "£20.00",
                "source_page": "https://books.toscrape.com/",
                "fetched_at": "2026-08-31T10:00:00Z",
            },
        ]
        
        # Run validation twice
        valid_books_1, errors_1 = validate_and_normalize_records(raw_records)
        valid_books_2, errors_2 = validate_and_normalize_records(raw_records)
        
        # Should produce identical results
        assert len(valid_books_1) == len(valid_books_2) == 2
        assert len(errors_1) == len(errors_2) == 0
        
        # Check that URLs are identical
        urls_1 = sorted([b.product_url for b in valid_books_1])
        urls_2 = sorted([b.product_url for b in valid_books_2])
        assert urls_1 == urls_2


class TestDeterminism:
    """Test that output is deterministic across runs."""

    def test_output_files_are_deterministic(self, tmp_path, monkeypatch):
        """Verify that repeated runs produce identical JSON output"""
        import src.main as main
        
        # Monkey patch output paths
        monkeypatch.setattr(main, "OUTPUT_DIR", tmp_path)
        monkeypatch.setattr(main, "BOOKS_FILE", tmp_path / "books.json")
        monkeypatch.setattr(main, "ERRORS_FILE", tmp_path / "errors.json")
        
        raw_records = [
            {
                "title": "Book A",
                "product_url": "https://books.toscrape.com/booka_1/index.html",
                "price_text": "£15.00",
                "source_page": "https://books.toscrape.com/",
                "fetched_at": "2026-08-31T10:00:00Z",
            },
        ]
        
        # Run twice and collect output
        valid_books_1, errors_1 = validate_and_normalize_records(raw_records)
        write_output_files(valid_books_1, errors_1)
        first_output = (tmp_path / "books.json").read_text()
        
        # Clean up
        (tmp_path / "books.json").unlink()
        (tmp_path / "errors.json").unlink()
        
        # Run again
        valid_books_2, errors_2 = validate_and_normalize_records(raw_records)
        write_output_files(valid_books_2, errors_2)
        second_output = (tmp_path / "books.json").read_text()
        
        # Output should be identical
        assert first_output == second_output


class TestOutputFiles:
    """Test writing of output JSON files."""

    def test_books_json_written(self, tmp_path, monkeypatch):
        """Verify that books.json is created with valid records"""
        import src.main as main
        
        monkeypatch.setattr(main, "OUTPUT_DIR", tmp_path)
        monkeypatch.setattr(main, "BOOKS_FILE", tmp_path / "books.json")
        monkeypatch.setattr(main, "ERRORS_FILE", tmp_path / "errors.json")
        
        raw_records = [
            {
                "title": "Example",
                "product_url": "https://books.toscrape.com/example_1/index.html",
                "price_text": "£10.00",
                "source_page": "https://books.toscrape.com/",
                "fetched_at": "2026-08-31T10:00:00Z",
            },
        ]
        
        valid_books, errors = validate_and_normalize_records(raw_records)
        write_output_files(valid_books, errors)
        
        books_file = tmp_path / "books.json"
        assert books_file.exists()
        
        books_data = json.loads(books_file.read_text())
        assert len(books_data) == 1
        assert books_data[0]["title"] == "Example"
        assert isinstance(books_data[0]["price_gbp"], float)

    def test_errors_json_written(self, tmp_path, monkeypatch):
        """Verify that errors.json is created with error records"""
        import src.main as main
        
        monkeypatch.setattr(main, "OUTPUT_DIR", tmp_path)
        monkeypatch.setattr(main, "BOOKS_FILE", tmp_path / "books.json")
        monkeypatch.setattr(main, "ERRORS_FILE", tmp_path / "errors.json")
        
        raw_records = [
            {
                "title": "Invalid",
                "product_url": "https://books.toscrape.com/invalid_1/index.html",
                "price_text": "not-a-price",
                "source_page": "https://books.toscrape.com/",
                "fetched_at": "2026-08-31T10:00:00Z",
            },
        ]
        
        valid_books, errors = validate_and_normalize_records(raw_records)
        write_output_files(valid_books, errors)
        
        errors_file = tmp_path / "errors.json"
        assert errors_file.exists()
        
        errors_data = json.loads(errors_file.read_text())
        assert len(errors_data) == 1
        assert errors_data[0]["product_url"] == "https://books.toscrape.com/invalid_1/index.html"

    def test_json_is_valid_and_formatted(self, tmp_path, monkeypatch):
        """Verify output JSON is well-formed and readable"""
        import src.main as main
        
        monkeypatch.setattr(main, "OUTPUT_DIR", tmp_path)
        monkeypatch.setattr(main, "BOOKS_FILE", tmp_path / "books.json")
        monkeypatch.setattr(main, "ERRORS_FILE", tmp_path / "errors.json")
        
        raw_records = [
            {
                "title": "Book",
                "product_url": "https://books.toscrape.com/book_1/index.html",
                "price_text": "£10.00",
                "source_page": "https://books.toscrape.com/",
                "fetched_at": "2026-08-31T10:00:00Z",
            },
        ]
        
        valid_books, errors = validate_and_normalize_records(raw_records)
        write_output_files(valid_books, errors)
        
        # Verify JSON is parseable
        books_data = json.loads((tmp_path / "books.json").read_text())
        errors_data = json.loads((tmp_path / "errors.json").read_text())
        
        assert isinstance(books_data, list)
        assert isinstance(errors_data, list)
