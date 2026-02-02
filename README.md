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
The default configuration targets the DOJ Epstein disclosure page and identifies dataset ZIP links.
Update `config.py` if the archive markup changes or you want to point at another source.

```python
SCRAPE_CONFIG = ScrapeConfig(
    base_url="https://www.justice.gov",
    listing_paths=("/epstein/doj-disclosures",),
    file_link_selector="a[href$='.zip'], a[href$='.ZIP']",
    dataset_label_pattern=r"DataSet\\s*(\\d+)",
    dataset_label_prefix="Dataset",
)
```

## Ingest data

```bash
python ingest.py --limit 25
```

By default the script ingests the most recent dataset ZIP. Use `--all` to ingest every dataset listed on the page.

The script downloads the ZIP files into `data/zips`, extracts files into `data/files`, and stores metadata in `data/epstein_files.sqlite3`.

## Run the UI

```bash
python app.py
```

Visit `http://localhost:8000` to search and filter the ingested files.

## Notes
- Ensure you have permission to download and store the source documents.
- Update selectors as needed for the specific HTML layout you are targeting.
