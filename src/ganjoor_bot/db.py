from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schema" / "schema.sql"


def connect(path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    # NORMAL is durable enough for a rebuildable corpus database and avoids the
    # much higher fsync cost of FULL during a large import.
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA temp_store = MEMORY")
    # Negative cache_size is KiB. 64 MiB is conservative for our small VPS.
    conn.execute("PRAGMA cache_size = -65536")
    return conn


def initialize(conn: sqlite3.Connection, schema_path: str | Path | None = None) -> None:
    path = Path(schema_path) if schema_path else SCHEMA_PATH
    conn.executescript(path.read_text(encoding="utf-8"))
    conn.commit()
