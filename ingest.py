import argparse
import hashlib
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from config import FILES_DIR, SCRAPE_CONFIG
from db import init_db, insert_file, upsert_categories


def build_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": "Full-Report-Indexer/1.0"})
    return session


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def derive_title(link_tag, fallback: str) -> str:
    title_candidate = link_tag.get("data-title") or link_tag.get_text(strip=True)
    return title_candidate or fallback


def parse_listing(html: str, base_url: str) -> list[dict[str, str | None]]:
    soup = BeautifulSoup(html, "html.parser")
    results: list[dict[str, str | None]] = []
    category_elements = soup.select(SCRAPE_CONFIG.category_selector)
    categories = {el.get("data-category") for el in category_elements if el.get("data-category")}

    for link in soup.select(SCRAPE_CONFIG.file_link_selector):
        href = link.get("href")
        if not href:
            continue
        title = derive_title(link, href)
        category = link.get("data-category") or link.get("data-tag")
        results.append(
            {
                "title": title,
                "category": category,
                "source_url": urljoin(base_url, href),
            }
        )

    upsert_categories(sorted(categories))
    return results


def download_file(session: requests.Session, url: str) -> tuple[bytes, str]:
    response = session.get(url, timeout=30)
    response.raise_for_status()
    payload = response.content
    return payload, sha256_bytes(payload)


def save_payload(payload: bytes, filename: str) -> Path:
    FILES_DIR.mkdir(parents=True, exist_ok=True)
    path = FILES_DIR / filename
    path.write_bytes(payload)
    return path


def ingest_listings(limit: int | None) -> None:
    init_db()
    session = build_session()
    count = 0
    for path in SCRAPE_CONFIG.listing_paths:
        listing_url = urljoin(SCRAPE_CONFIG.base_url, path)
        response = session.get(listing_url, timeout=30)
        response.raise_for_status()
        entries = parse_listing(response.text, SCRAPE_CONFIG.base_url)
        for entry in entries:
            if limit and count >= limit:
                return
            payload, checksum = download_file(session, entry["source_url"])
            filename = Path(entry["source_url"]).name or f"file-{count}.bin"
            saved_path = save_payload(payload, filename)
            insert_file(
                title=entry["title"] or filename,
                category=entry["category"],
                source_url=entry["source_url"],
                local_path=str(saved_path),
                sha256=checksum,
            )
            count += 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest files into the database.")
    parser.add_argument("--limit", type=int, default=None, help="Limit files ingested")
    args = parser.parse_args()
    ingest_listings(limit=args.limit)


if __name__ == "__main__":
    main()
