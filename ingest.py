import argparse
import hashlib
import re
import zipfile
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from config import DATA_DIR, FILES_DIR, SCRAPE_CONFIG
from db import init_db, insert_file


def build_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(SCRAPE_CONFIG.request_headers)
    return session


def resolve_listing_url(path_or_url: str) -> str:
    parsed = urlparse(path_or_url)
    if parsed.scheme and parsed.netloc:
        return path_or_url
    return urljoin(SCRAPE_CONFIG.base_url, path_or_url)


def fetch_html(session: requests.Session, url: str) -> str:
    response = session.get(url, timeout=30)
    if response.status_code == 403:
        raise RuntimeError(
            f"Received 403 for {url}. The DOJ disclosures page "
            "(/epstein/doj-disclosures) is accessible; update listing_paths or "
            "pass --listing to target that page."
        )
    response.raise_for_status()
    return response.text


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def derive_dataset_label(href: str) -> str | None:
    match = re.search(SCRAPE_CONFIG.dataset_label_pattern, href, re.IGNORECASE)
    if not match:
        return None
    return f"{SCRAPE_CONFIG.dataset_label_prefix} {match.group(1)}"


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


def download_zip(session: requests.Session, url: str, target_path: Path) -> str:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    with session.get(url, timeout=60, stream=True) as response:
        response.raise_for_status()
        with target_path.open("wb") as handle:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if not chunk:
                    continue
                handle.write(chunk)
                digest.update(chunk)
    return digest.hexdigest()


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
    latest_only: bool,
    listing_paths: tuple[str, ...],
) -> None:
    init_db()
    session = build_session()
    count = 0
    all_entries: list[dict[str, str | None]] = []
    for path in listing_paths:
        listing_url = resolve_listing_url(path)
        html = fetch_html(session, listing_url)
        all_entries.extend(parse_listing(html, SCRAPE_CONFIG.base_url))

    entries = [entry for entry in all_entries if entry.get("source_url")]
    if latest_only and entries:
        def dataset_number(entry: dict[str, str | None]) -> int:
            label = entry.get("dataset") or ""
            match = re.search(r"(\d+)", label)
            return int(match.group(1)) if match else -1

        latest = max(entries, key=dataset_number)
        entries = [latest]

    for entry in entries:
        if limit and count >= limit:
            return
        source_url = entry["source_url"]
        dataset = entry.get("dataset") or "Uncategorized"
        zip_name = Path(source_url).name.replace(" ", "_") or f"dataset-{count}.zip"
        zip_path = DATA_DIR / "zips" / zip_name
        zip_checksum = download_zip(session, source_url, zip_path)
        target_dir = FILES_DIR / (dataset.replace(" ", "_") if dataset else "dataset")
        extracted_files = safe_extract(zip_path, target_dir)
        for extracted_path in extracted_files:
            if limit and count >= limit:
                return
            file_checksum = sha256_path(extracted_path)
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
        "--listing",
        action="append",
        help="Override listing URL(s). Can be passed multiple times.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Ingest all datasets instead of only the most recent",
    )
    args = parser.parse_args()
    listing_paths = tuple(args.listing) if args.listing else SCRAPE_CONFIG.listing_paths
    ingest_listings(
        limit=args.limit,
        latest_only=not args.all,
        listing_paths=listing_paths,
    )


if __name__ == "__main__":
    main()
