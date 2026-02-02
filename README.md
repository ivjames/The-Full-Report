# The-Full-Report

This project provides a lightweight pipeline for indexing a large HTML document archive into a SQLite database, plus a minimal Flask UI for searching and reviewing metadata.

## Features

- Configurable HTML scraping to collect file links and categories.
- Local storage of downloaded files with SHA-256 hashing.
- SQLite-backed UI for searching and filtering by category.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Configure the scraper

Update `config.py` with the base URL and HTML selectors that match the archive you want to ingest.

```python
SCRAPE_CONFIG = ScrapeConfig(
    base_url="https://example.com",
    listing_paths=("/files",),
    file_link_selector="a[href]",
    category_selector="[data-category]",
    title_selector="[data-title]",
)
```

## Ingest data

```bash
python ingest.py --limit 25
```

The script downloads files into `data/files` and stores metadata in `data/epstein_files.sqlite3`.

## Run the UI

```bash
python app.py
```

Visit `http://localhost:8000` to search and filter the ingested files.

## Notes

- Ensure you have permission to download and store the source documents.
- Update selectors as needed for the specific HTML layout you are targeting.
