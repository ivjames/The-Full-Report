import argparse
import hashlib
import re
import zipfile
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

try:
    from playwright.sync_api import sync_playwright
except Exception:  # pragma: no cover - optional dependency
    sync_playwright = None

from config import FILES_DIR, SCRAPE_CONFIG
from db import init_db, insert_file, upsert_categories


DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/121.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "DNT": "1",
}


def build_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(DEFAULT_HEADERS)
    return session


def prime_session(session: requests.Session) -> None:
    try:
        session.get(SCRAPE_CONFIG.base_url, timeout=30)
    except requests.RequestException:
        return


def ensure_playwright_available() -> None:
    if sync_playwright is None:
        raise RuntimeError(
            "Playwright is required for DOJ pages that block direct requests. "
            "Install the playwright package and its browsers."
        )


def fetch_bytes_via_browser(url: str, *, referer: str | None = None) -> bytes:
    ensure_playwright_available()
    assert sync_playwright is not None
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        extra_headers = dict(DEFAULT_HEADERS)
        if referer:
            extra_headers["Referer"] = referer
        context = browser.new_context(extra_http_headers=extra_headers)
        page = context.new_page()
        response = page.goto(url, wait_until="networkidle")
        if response is None or response.status >= 400:
            browser.close()
            status = response.status if response else "unknown"
            raise RuntimeError(f"Browser fetch failed with status {status} for {url}")
        payload = response.body()
        browser.close()
        return payload


def fetch_html_via_browser(url: str) -> str:
    ensure_playwright_available()
    assert sync_playwright is not None
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        extra_headers = dict(DEFAULT_HEADERS)
        extra_headers["Referer"] = SCRAPE_CONFIG.base_url
        context = browser.new_context(extra_http_headers=extra_headers)
        page = context.new_page()
        response = page.goto(url, wait_until="networkidle")
        if response is None or response.status >= 400:
            browser.close()
            status = response.status if response else "unknown"
            raise RuntimeError(f"Browser fetch failed with status {status} for {url}")
        html = page.content()
        browser.close()
        return html


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def derive_title(link_tag, fallback: str) -> str:
    title_candidate = link_tag.get("data-title") or link_tag.get_text(strip=True)
    return title_candidate or fallback


def parse_listing(html: str, base_url: str) -> list[dict[str, str | None]]:
    soup = BeautifulSoup(html, "html.parser")
    results: list[dict[str, str | None]] = []

    for link in soup.select(SCRAPE_CONFIG.file_link_selector):
        href = link.get("href")
        if not href:
            continue
        dataset = derive_dataset_label(href)
        results.append(
            {
                "dataset": dataset,
                "source_url": urljoin(base_url, href),
            }
        )

    return results


def fetch_response(
    session: requests.Session, url: str, *, referer: str | None = None
) -> requests.Response:
    headers: dict[str, str] = {}
    if referer:
        headers["Referer"] = referer
    response = session.get(url, timeout=30, headers=headers)
    if response.status_code == 403:
        prime_session(session)
        retry_headers = {"Referer": referer or SCRAPE_CONFIG.base_url}
        response = session.get(
            url,
            timeout=30,
            headers=retry_headers,
        )
    response.raise_for_status()
    return response


def download_file(session: requests.Session, url: str) -> tuple[bytes, str]:
    try:
        response = fetch_response(session, url, referer=SCRAPE_CONFIG.base_url)
        payload = response.content
    except requests.HTTPError as exc:
        if exc.response is None or exc.response.status_code != 403:
            raise
        payload = fetch_bytes_via_browser(url, referer=SCRAPE_CONFIG.base_url)
    return payload, sha256_bytes(payload)


def safe_extract(zip_path: Path, target_dir: Path) -> list[Path]:
    extracted: list[Path] = []
    target_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as archive:
        for member in archive.infolist():
            if member.is_dir():
                continue
            member_path = Path(member.filename)
            destination = target_dir / member_path
            resolved = destination.resolve()
            if not str(resolved).startswith(str(target_dir.resolve())):
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as source, destination.open("wb") as dest_handle:
                dest_handle.write(source.read())
            extracted.append(destination)
    return extracted


def ingest_listings(
    limit: int | None,
    listing_html_paths: list[Path] | None,
    skip_download: bool,
) -> None:
    init_db()
    session = build_session()
    prime_session(session)
    count = 0
    listing_sources: list[tuple[str, str]] = []

    if listing_html_paths:
        for html_path in listing_html_paths:
            listing_sources.append(
                (str(html_path), html_path.read_text(encoding="utf-8"))
            )
    else:
        for path in SCRAPE_CONFIG.listing_paths:
            listing_url = urljoin(SCRAPE_CONFIG.base_url, path)
            try:
                response = fetch_response(
                    session, listing_url, referer=SCRAPE_CONFIG.base_url
                )
                html = response.text
            except requests.HTTPError as exc:
                if exc.response is None or exc.response.status_code != 403:
                    raise
                html = fetch_html_via_browser(listing_url)
            listing_sources.append((listing_url, html))

    for listing_id, html in listing_sources:
        entries = parse_listing(html, SCRAPE_CONFIG.base_url)
        for entry in entries:
            if limit and count >= limit:
                return
            if skip_download:
                filename = Path(entry["source_url"]).name or f"file-{count}.bin"
                insert_file(
                    title=entry["title"] or filename,
                    category=entry["category"],
                    source_url=entry["source_url"],
                    local_path=None,
                    sha256=None,
                )
                count += 1
                continue
            payload, checksum = download_file(session, entry["source_url"])
            filename = Path(entry["source_url"]).name or f"file-{count}.bin"
            saved_path = save_payload(payload, filename)
            insert_file(
                title=extracted_path.name,
                category=dataset,
                source_url=source_url,
                source_path=str(extracted_path.relative_to(target_dir)),
                local_path=str(extracted_path),
                sha256=file_checksum,
                file_size=extracted_path.stat().st_size,
                file_type=extracted_path.suffix.lstrip(".") or None,
                batch_checksum=zip_checksum,
            )
            count += 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest files into the database.")
    parser.add_argument("--limit", type=int, default=None, help="Limit files ingested")
    parser.add_argument(
        "--listing-html",
        action="append",
        type=Path,
        default=None,
        help="Path to a locally saved listing HTML file (can be repeated).",
    )
    parser.add_argument(
        "--skip-download",
        action="store_true",
        help="Only store metadata; do not download files.",
    )
    args = parser.parse_args()
    ingest_listings(
        limit=args.limit,
        listing_html_paths=args.listing_html,
        skip_download=args.skip_download,
    )


if __name__ == "__main__":
    main()
