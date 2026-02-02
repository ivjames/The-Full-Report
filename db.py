import sqlite3
from pathlib import Path
from typing import Iterable

from config import DB_PATH


SCHEMA = """
CREATE TABLE IF NOT EXISTS files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    category TEXT,
    source_url TEXT NOT NULL,
    local_path TEXT,
    sha256 TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
);

CREATE INDEX IF NOT EXISTS idx_files_category ON files(category);
CREATE INDEX IF NOT EXISTS idx_files_title ON files(title);
"""


def get_connection(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path or DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    return connection


def init_db() -> None:
    with get_connection() as connection:
        connection.executescript(SCHEMA)


def upsert_categories(categories: Iterable[str]) -> None:
    with get_connection() as connection:
        connection.executemany(
            "INSERT OR IGNORE INTO categories (name) VALUES (?)",
            [(category,) for category in categories if category],
        )


def insert_file(
    title: str,
    category: str | None,
    source_url: str,
    local_path: str | None,
    sha256: str | None,
) -> None:
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO files (title, category, source_url, local_path, sha256)
            VALUES (?, ?, ?, ?, ?)
            """,
            (title, category, source_url, local_path, sha256),
        )


def fetch_categories() -> list[sqlite3.Row]:
    with get_connection() as connection:
        return connection.execute(
            "SELECT category, COUNT(*) AS total FROM files GROUP BY category"
        ).fetchall()


def search_files(query: str | None, category: str | None) -> list[sqlite3.Row]:
    sql = "SELECT * FROM files"
    clauses = []
    params: list[str] = []
    if query:
        clauses.append("title LIKE ?")
        params.append(f"%{query}%")
    if category:
        clauses.append("category = ?")
        params.append(category)
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY created_at DESC"

    with get_connection() as connection:
        return connection.execute(sql, params).fetchall()


def get_file(file_id: int) -> sqlite3.Row | None:
    with get_connection() as connection:
        return connection.execute(
            "SELECT * FROM files WHERE id = ?",
            (file_id,),
        ).fetchone()
