from __future__ import annotations

import math
import sqlite3
from pathlib import Path
from typing import Any


def connect_state(path: str | Path) -> sqlite3.Connection:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    initialize_state(conn)
    return conn


def initialize_state(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            telegram_user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS collections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(telegram_user_id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, name)
        );

        CREATE TABLE IF NOT EXISTS bookmarks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(telegram_user_id) ON DELETE CASCADE,
            poem_id INTEGER NOT NULL,
            collection_id INTEGER REFERENCES collections(id) ON DELETE SET NULL,
            bookmark_type TEXT NOT NULL DEFAULT 'poem',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, poem_id)
        );

        CREATE INDEX IF NOT EXISTS idx_collections_user
            ON collections(user_id, name);
        CREATE INDEX IF NOT EXISTS idx_bookmarks_user
            ON bookmarks(user_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_bookmarks_collection
            ON bookmarks(user_id, collection_id, created_at DESC);
        """
    )
    conn.commit()


def touch_user(
    conn: sqlite3.Connection,
    user_id: int,
    *,
    username: str | None = None,
    first_name: str | None = None,
    last_name: str | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO users(telegram_user_id, username, first_name, last_name)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(telegram_user_id) DO UPDATE SET
            username = excluded.username,
            first_name = excluded.first_name,
            last_name = excluded.last_name,
            updated_at = CURRENT_TIMESTAMP
        """,
        (int(user_id), username, first_name, last_name),
    )
    conn.commit()


def create_collection(conn: sqlite3.Connection, user_id: int, name: str) -> int:
    clean = " ".join(name.split()).strip()
    if not clean:
        raise ValueError("Collection name cannot be empty")
    if len(clean) > 60:
        raise ValueError("Collection name is too long")
    cursor = conn.execute(
        "INSERT INTO collections(user_id, name) VALUES (?, ?)",
        (int(user_id), clean),
    )
    conn.commit()
    return int(cursor.lastrowid)


def rename_collection(
    conn: sqlite3.Connection,
    user_id: int,
    collection_id: int,
    name: str,
) -> bool:
    clean = " ".join(name.split()).strip()
    if not clean:
        raise ValueError("Collection name cannot be empty")
    if len(clean) > 60:
        raise ValueError("Collection name is too long")
    cursor = conn.execute(
        "UPDATE collections SET name = ? WHERE id = ? AND user_id = ?",
        (clean, int(collection_id), int(user_id)),
    )
    conn.commit()
    return cursor.rowcount > 0


def delete_collection(conn: sqlite3.Connection, user_id: int, collection_id: int) -> bool:
    cursor = conn.execute(
        "DELETE FROM collections WHERE id = ? AND user_id = ?",
        (int(collection_id), int(user_id)),
    )
    conn.commit()
    return cursor.rowcount > 0


def list_collections(conn: sqlite3.Connection, user_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT
            c.id,
            c.name,
            COUNT(b.id) AS bookmark_count
        FROM collections c
        LEFT JOIN bookmarks b
          ON b.collection_id = c.id
         AND b.user_id = c.user_id
        WHERE c.user_id = ?
        GROUP BY c.id, c.name
        ORDER BY c.name, c.id
        """,
        (int(user_id),),
    ).fetchall()
    return [dict(row) for row in rows]


def get_collection(
    conn: sqlite3.Connection,
    user_id: int,
    collection_id: int,
) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT id, name FROM collections WHERE id = ? AND user_id = ?",
        (int(collection_id), int(user_id)),
    ).fetchone()
    return dict(row) if row else None


def add_bookmark(
    conn: sqlite3.Connection,
    user_id: int,
    poem_id: int,
    *,
    collection_id: int | None = None,
    bookmark_type: str = "poem",
) -> tuple[int, bool]:
    if collection_id is not None:
        collection = get_collection(conn, user_id, collection_id)
        if collection is None:
            raise ValueError("Collection does not belong to this user")

    existing = conn.execute(
        "SELECT id FROM bookmarks WHERE user_id = ? AND poem_id = ?",
        (int(user_id), int(poem_id)),
    ).fetchone()
    if existing:
        if collection_id is not None:
            conn.execute(
                "UPDATE bookmarks SET collection_id = ?, bookmark_type = ? WHERE id = ?",
                (int(collection_id), bookmark_type, int(existing["id"])),
            )
            conn.commit()
        return int(existing["id"]), False

    cursor = conn.execute(
        """
        INSERT INTO bookmarks(user_id, poem_id, collection_id, bookmark_type)
        VALUES (?, ?, ?, ?)
        """,
        (int(user_id), int(poem_id), collection_id, bookmark_type),
    )
    conn.commit()
    return int(cursor.lastrowid), True


def remove_bookmark(conn: sqlite3.Connection, user_id: int, poem_id: int) -> bool:
    cursor = conn.execute(
        "DELETE FROM bookmarks WHERE user_id = ? AND poem_id = ?",
        (int(user_id), int(poem_id)),
    )
    conn.commit()
    return cursor.rowcount > 0


def move_bookmark(
    conn: sqlite3.Connection,
    user_id: int,
    poem_id: int,
    collection_id: int | None,
) -> bool:
    if collection_id is not None and get_collection(conn, user_id, collection_id) is None:
        return False
    cursor = conn.execute(
        """
        UPDATE bookmarks
        SET collection_id = ?
        WHERE user_id = ? AND poem_id = ?
        """,
        (collection_id, int(user_id), int(poem_id)),
    )
    conn.commit()
    return cursor.rowcount > 0


def get_bookmark(
    conn: sqlite3.Connection,
    user_id: int,
    poem_id: int,
) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT b.id, b.poem_id, b.collection_id, b.bookmark_type, b.created_at,
               c.name AS collection_name
        FROM bookmarks b
        LEFT JOIN collections c ON c.id = b.collection_id
        WHERE b.user_id = ? AND b.poem_id = ?
        """,
        (int(user_id), int(poem_id)),
    ).fetchone()
    return dict(row) if row else None


def _page_meta(total: int, page: int, page_size: int) -> dict[str, int | bool]:
    page_size = max(1, int(page_size))
    pages = max(1, math.ceil(total / page_size)) if total else 1
    page = min(max(0, int(page)), pages - 1)
    return {
        "page": page,
        "page_size": page_size,
        "pages": pages,
        "total": total,
        "has_prev": page > 0,
        "has_next": page + 1 < pages,
    }


def list_bookmarks(
    conn: sqlite3.Connection,
    user_id: int,
    *,
    collection: str | int = "all",
    page: int = 0,
    page_size: int = 10,
) -> dict[str, Any]:
    clauses = ["b.user_id = ?"]
    params: list[Any] = [int(user_id)]

    if collection == "none":
        clauses.append("b.collection_id IS NULL")
    elif collection != "all":
        clauses.append("b.collection_id = ?")
        params.append(int(collection))

    where = " AND ".join(clauses)
    total = int(
        conn.execute(
            f"SELECT COUNT(*) FROM bookmarks b WHERE {where}",
            params,
        ).fetchone()[0]
    )
    meta = _page_meta(total, page, page_size)
    offset = int(meta["page"]) * int(meta["page_size"])

    rows = conn.execute(
        f"""
        SELECT b.id, b.poem_id, b.collection_id, b.bookmark_type, b.created_at,
               c.name AS collection_name
        FROM bookmarks b
        LEFT JOIN collections c ON c.id = b.collection_id
        WHERE {where}
        ORDER BY b.created_at DESC, b.id DESC
        LIMIT ? OFFSET ?
        """,
        [*params, meta["page_size"], offset],
    ).fetchall()
    return {**meta, "items": [dict(row) for row in rows]}


def bookmark_counts(conn: sqlite3.Connection, user_id: int) -> dict[str, int]:
    row = conn.execute(
        """
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN collection_id IS NULL THEN 1 ELSE 0 END) AS uncategorized
        FROM bookmarks
        WHERE user_id = ?
        """,
        (int(user_id),),
    ).fetchone()
    return {
        "total": int(row["total"] or 0),
        "uncategorized": int(row["uncategorized"] or 0),
    }
