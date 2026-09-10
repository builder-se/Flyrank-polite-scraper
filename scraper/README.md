# FlyRank Polite Scraper

A small, cache-aware Python scraper for the public [Books to Scrape](https://books.toscrape.com/) practice website.

The scraper discovers books from up to three catalogue pages, fetches each detail page, extracts the required fields, validates and normalizes the records with Pydantic, and writes JSON output for downstream use.

This project is intended for the Books to Scrape learning environment only. Before using any scraper on another website, review its terms, robots policy, and access requirements.

## Stage 0 classification and lane

- **Target classification:** public, static HTML catalogue with publicly visible book metadata.
- **Lane:** polite public-web data collection for a learning assignment, not a general-purpose crawler.

The repository includes JSON evidence from a successful run. Cached HTML is local working data and is excluded from Git.

## Quick start

From the repository root, run the following in PowerShell:

```powershell
Set-Location scraper
python -m venv .venv
& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt
& .\.venv\Scripts\python.exe src\main.py
```

The first run may use the network. Later runs reuse cached pages when available.

## Requirements

- Python 3.10 or newer
- PowerShell on Windows, or an equivalent shell on another operating system
- Internet access when a required page is not already cached

The project uses these Python packages:

- `requests` for HTTP requests
- `beautifulsoup4` for HTML parsing
- `pydantic` for record validation
- `pytest` for automated tests

## Installation

Run these commands from the repository root:

```powershell
Set-Location scraper
python -m venv .venv
& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Use the virtual-environment interpreter for all commands. This avoids accidentally using a different Python installation.

## Running the scraper

Run the normal scraper from the `scraper` directory:

```powershell
& .\.venv\Scripts\python.exe src\main.py
```

The command prints discovery and validation checkpoints, including:

- Number of catalogue pages visited
- Number of discovered and unique product URLs
- Number of detail pages processed
- Number of valid and invalid records

### One copy-pasteable run

From the repository root, this complete PowerShell block installs dependencies, runs the scraper, and runs the tests:

```powershell
Set-Location scraper; python -m venv .venv; & .\.venv\Scripts\python.exe -m pip install -r requirements.txt; & .\.venv\Scripts\python.exe src\main.py; & .\.venv\Scripts\python.exe -m pytest
```

### Run with existing cache

No extra option is needed. Cached HTML is read before a network request, so rerunning the command is usually faster and avoids repeated requests.

### Run from a clean cache

To force a fresh network run, remove the generated cache and output files, then run the scraper again:

```powershell
Remove-Item -Recurse -Force cache\*, output\*
& .\.venv\Scripts\python.exe src\main.py
```

The directories are recreated automatically. Only remove these folders when you are sure you do not need the existing generated data.

## Testing

Run the complete automated test suite from the `scraper` directory:

```powershell
& .\.venv\Scripts\python.exe -m pytest
```

Run with more detailed output:

```powershell
& .\.venv\Scripts\python.exe -m pytest -v
```

Run a specific test module:

```powershell
& .\.venv\Scripts\python.exe -m pytest tests\test_stage4_validation.py
```

The tests cover catalogue discovery, HTML extraction, price and record validation, retry behavior, cache handling, report generation, and survival of an individual failed detail page.

## Stage 5 checkpoint

The standalone checkpoint verifies that one failed detail page does not discard successful records:

```powershell
& .\.venv\Scripts\python.exe stage5_check.py
```

## Generated files

After a run, the scraper writes these files under `output/`:

| File | Purpose |
| --- | --- |
| `books.json` | Validated and normalized book records |
| `errors.json` | Records that failed fetching or normalization, with reasons |
| `runreport.json` | Canonical run summary |
| `run-report.json` | Backward-compatible alias of the run summary |

Cached pages and their fetch timestamps are stored under `cache/` as HTML and `.meta.json` files.

## Output record schema

Each valid entry in `books.json` has this shape:

```json
{
  "title": "string",
  "product_url": "https://...",
  "price_text": "string",
  "price_gbp": 0.0,
  "availability_text": "string or null",
  "rating_text": "string or null",
  "description": "string or null",
  "source_page": "string",
  "fetched_at": "ISO-8601 UTC timestamp string"
}
```

`price_text` preserves the scraped value, while `price_gbp` contains its numeric value. Records are deduplicated by `product_url`. Invalid or duplicate records are preserved in `errors.json` with diagnostic information.

## Run report

The run report contains:

- `start_time`: UTC start timestamp
- `duration`: elapsed time in seconds when produced by the programmatic runner
- `pages_fetched`: pages fetched from the network
- `cache_hits`: pages loaded from local cache
- `valid_records`: records written to `books.json`
- `invalid_records`: records rejected during normalization
- `failed_pages`: detail pages that could not be fetched or processed

The scraper continues after an individual detail-page failure. A catalogue discovery failure is fatal because the scraper cannot determine which detail pages to visit.

### Sample evidence

This is a real `output/run-report.json` produced by the scraper:

```json
{
  "cache_hits": 63,
  "duration": 0.0,
  "failed_pages": 0,
  "invalid_records": 0,
  "pages_fetched": 0,
  "start_time": "2026-09-10T18:18:18Z",
  "valid_records": 60
}
```

The JSON evidence files are committed; cached HTML pages are not.

## Politeness and scope

The current implementation uses these controls:

- Target: `https://books.toscrape.com/`
- Maximum catalogue pages: 3
- Request delay: 0.5 seconds
- Request timeout: 5 seconds
- User-Agent: `FlyRankInternshipA9/1.0 (+https://github.com/)`
- Retry policy: one retry for timeouts and HTTP 5xx responses
- No retry for HTTP 403 or 404 responses
- Cached Books to Scrape pages are reused before making network requests

The expected sample is up to 60 books, based on 20 books per catalogue page. The exact result depends on source availability and parsing results.

## Browser and ethics

This assignment needs no browser because the data is already in the HTML the server sends, so a browser would only add cost.

Use an official API when one exists. Never bypass logins, paywalls, or blocks, and collect only the fields needed for the assignment.

## Project layout

```text
scraper/
|-- src/
|   |-- __init__.py          Python package marker
|   `-- main.py              Scraper, parsing, validation, and output logic
|-- tests/                   Automated tests
|-- cache/                   Generated cached HTML and fetch metadata
|-- output/                  Generated JSON results and reports
|-- requirements.txt         Runtime and test dependencies
|-- stage5_check.py          Failure-survival checkpoint
`-- README.md                Project documentation
```

## Troubleshooting

### `ModuleNotFoundError`

Make sure the virtual environment is activated or use its interpreter explicitly:

```powershell
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### The run returns cached data

Delete the contents of `cache/` and run the clean-cache command above.

### Network or HTTP errors

Check your internet connection and rerun the command. A failed individual detail page is recorded in `output/errors.json`; the rest of the run can still succeed.

### Selectors no longer match

The scraper is tailored to the current Books to Scrape HTML structure. If the site markup changes, update the extraction functions in `src/main.py` and add or update focused tests.

## Limitations

- There is no command-line configuration interface; the target, page limit, timeout, and delay are constants in `src/main.py`.
- The scraper is not a general-purpose crawler.
- Prices are stored as floating-point GBP values for this learning project; financial applications should use a decimal type.
- The project does not use a browser because the required data is available in the server HTML.