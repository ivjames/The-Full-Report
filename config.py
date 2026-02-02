from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ScrapeConfig:
    base_url: str
    listing_paths: tuple[str, ...]
    file_link_selector: str
    dataset_label_pattern: str
    dataset_label_prefix: str


DATA_DIR = Path("data")
FILES_DIR = DATA_DIR / "files"
DB_PATH = DATA_DIR / "epstein_files.sqlite3"

SCRAPE_CONFIG = ScrapeConfig(
    base_url="https://www.justice.gov",
    listing_paths=("/epstein/doj-disclosures",),
    file_link_selector="a[href$='.zip'], a[href$='.ZIP']",
    dataset_label_pattern=r"DataSet\s*(\d+)",
    dataset_label_prefix="Dataset",
)
