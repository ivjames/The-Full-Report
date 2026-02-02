from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ScrapeConfig:
    base_url: str
    listing_paths: tuple[str, ...]
    file_link_selector: str
    category_selector: str
    title_selector: str


DATA_DIR = Path("data")
FILES_DIR = DATA_DIR / "files"
DB_PATH = DATA_DIR / "epstein_files.sqlite3"

SCRAPE_CONFIG = ScrapeConfig(
    base_url="https://www.justice.gov",
    listing_paths=("/epstein/court-records", "/epstein/doj-disclosures",),
    file_link_selector="a[href]",
    category_selector="[data-category]",
    title_selector="[data-title]",
)
