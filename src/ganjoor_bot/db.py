from __future__ import annotations

import os
import sqlite3
from pathlib import Path

SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schema" / "schema.sql"


def connect(path: str | Path) -> sqlite3.Connection:
    """Open a corpus database for either build-time writes or runtime reads.

    The corpus is writable while it is being built, so WAL mode is useful there.
    In production the Telegram service intentionally runs as an unprivileged user
    and only needs to read the corpus. In that case attempting to switch the
    database to WAL would require creating ``-wal``/``-shm`` files next to the
    database and fails on a read-only deployment. Detect that situation and make
    the connection explicitly query-only instead.
    """
    db_path = Path(path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")

    can_write_database = os.access(db_path, os.W_OK)
    can_write_directory = os.access(db_path.parent, os.W_OK)

    if can_write_database and can_write_directory:
        conn.execute("PRAGMA journal_mode = WAL")
        # NORMAL is durable enough for a rebuildable corpus database and avoids
        # the much higher fsync cost of FULL during a large import.
        conn.execute("PRAGMA synchronous = NORMAL")
    else:
        # Runtime clients such as the Telegram bot never mutate the corpus.
        conn.execute("PRAGMA query_only = ON")

    conn.execute("PRAGMA temp_store = MEMORY")
    # Negative cache_size is KiB. 64 MiB is conservative for our small VPS.
    conn.execute("PRAGMA cache_size = -65536")
    return conn


def initialize(conn: sqlite3.Connection, schema_path: str | Path | None = None) -> None:
    path = Path(schema_path) if schema_path else SCHEMA_PATH
    conn.executescript(path.read_text(encoding="utf-8"))
    conn.commit()
