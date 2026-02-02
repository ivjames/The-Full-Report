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
    source_path TEXT,
    local_path TEXT,
    sha256 TEXT,
    file_size INTEGER,
    file_type TEXT,
    batch_checksum TEXT,
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
        ensure_columns(connection)


def ensure_columns(connection: sqlite3.Connection) -> None:
    existing = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(files)").fetchall()
    }
    required = {
        "source_path": "TEXT",
        "file_size": "INTEGER",
        "file_type": "TEXT",
        "batch_checksum": "TEXT",
    }
    for column, column_type in required.items():
        if column not in existing:
            connection.execute(
                f"ALTER TABLE files ADD COLUMN {column} {column_type}"
            )


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
    source_path: str | None,
    local_path: str | None,
    sha256: str | None,
    file_size: int | None,
    file_type: str | None,
    batch_checksum: str | None,
) -> None:
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO files (
                title,
                category,
                source_url,
                source_path,
                local_path,
                sha256,
                file_size,
                file_type,
                batch_checksum
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                title,
                category,
                source_url,
                source_path,
                local_path,
                sha256,
                file_size,
                file_type,
                batch_checksum,
            ),
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
