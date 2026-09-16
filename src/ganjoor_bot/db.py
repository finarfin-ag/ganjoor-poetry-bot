from __future__ import annotations

import os
import sqlite3
from pathlib import Path

SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schema" / "schema.sql"


def _configure_common(conn: sqlite3.Connection) -> sqlite3.Connection:
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def connect(path: str | Path) -> sqlite3.Connection:
    """Open the corpus database in writable build mode or true read-only runtime mode.

    During corpus builds the database and its directory are writable, so WAL and
    import-oriented tuning are useful. In production the Telegram service runs as
    an unprivileged user and only reads the finished corpus. SQLite pragmas such as
    ``journal_mode`` and even ``cache_size`` can attempt writes, so a deployed
    read-only corpus must be opened with SQLite's URI ``mode=ro`` rather than by
    opening normally and trying to convert the connection afterwards.
    """
    db_path = Path(path)

    # A missing database is necessarily a build/new-database case. For an existing
    # database, WAL also needs the containing directory to be writable because
    # SQLite may create -wal/-shm files next to the database.
    is_existing_readonly = db_path.exists() and not (
        os.access(db_path, os.W_OK) and os.access(db_path.parent, os.W_OK)
    )

    if is_existing_readonly:
        uri = db_path.resolve().as_uri() + "?mode=ro"
        conn = _configure_common(sqlite3.connect(uri, uri=True))
        conn.execute("PRAGMA query_only = ON")
        return conn

    conn = _configure_common(sqlite3.connect(db_path))
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
