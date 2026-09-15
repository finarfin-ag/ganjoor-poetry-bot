from __future__ import annotations

import math
import sqlite3
from typing import Any


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


def list_poets(
    conn: sqlite3.Connection,
    *,
    page: int = 0,
    page_size: int = 12,
) -> dict[str, Any]:
    """Return poets alphabetically with poem counts and pagination metadata."""
    total = int(conn.execute("SELECT COUNT(*) FROM poets").fetchone()[0])
    meta = _page_meta(total, page, page_size)
    offset = int(meta["page"]) * int(meta["page_size"])

    rows = conn.execute(
        """
        SELECT
            po.id,
            po.nickname,
            po.name,
            COUNT(p.id) AS poem_count
        FROM poets po
        LEFT JOIN poems p ON p.poet_id = po.id
        GROUP BY po.id, po.nickname, po.name
        ORDER BY po.nickname, po.id
        LIMIT ? OFFSET ?
        """,
        (meta["page_size"], offset),
    ).fetchall()
    return {**meta, "items": [dict(row) for row in rows]}


def get_poet(conn: sqlite3.Connection, poet_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT
            po.id,
            po.nickname,
            po.name,
            po.description,
            COUNT(p.id) AS poem_count
        FROM poets po
        LEFT JOIN poems p ON p.poet_id = po.id
        WHERE po.id = ?
        GROUP BY po.id, po.nickname, po.name, po.description
        """,
        (poet_id,),
    ).fetchone()
    return dict(row) if row else None


def list_root_categories(conn: sqlite3.Connection, poet_id: int) -> list[dict[str, Any]]:
    """Return top-level categories for one poet."""
    rows = conn.execute(
        """
        SELECT
            c.id,
            c.poet_id,
            c.parent_id,
            c.title,
            (SELECT COUNT(*) FROM categories child WHERE child.parent_id = c.id) AS child_count,
            (SELECT COUNT(*) FROM poems p WHERE p.category_id = c.id) AS direct_poem_count
        FROM categories c
        WHERE c.poet_id = ? AND c.parent_id IS NULL
        ORDER BY c.title, c.id
        """,
        (poet_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def get_category(conn: sqlite3.Connection, category_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT
            c.id,
            c.poet_id,
            c.parent_id,
            c.title,
            c.description,
            (SELECT COUNT(*) FROM categories child WHERE child.parent_id = c.id) AS child_count,
            (SELECT COUNT(*) FROM poems p WHERE p.category_id = c.id) AS direct_poem_count
        FROM categories c
        WHERE c.id = ?
        """,
        (category_id,),
    ).fetchone()
    return dict(row) if row else None


def list_category_children(conn: sqlite3.Connection, category_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT
            c.id,
            c.poet_id,
            c.parent_id,
            c.title,
            (SELECT COUNT(*) FROM categories child WHERE child.parent_id = c.id) AS child_count,
            (SELECT COUNT(*) FROM poems p WHERE p.category_id = c.id) AS direct_poem_count
        FROM categories c
        WHERE c.parent_id = ?
        ORDER BY c.title, c.id
        """,
        (category_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def list_poems_in_category(
    conn: sqlite3.Connection,
    category_id: int,
    *,
    page: int = 0,
    page_size: int = 10,
) -> dict[str, Any]:
    total = int(
        conn.execute(
            "SELECT COUNT(*) FROM poems WHERE category_id = ?",
            (category_id,),
        ).fetchone()[0]
    )
    meta = _page_meta(total, page, page_size)
    offset = int(meta["page"]) * int(meta["page_size"])
    rows = conn.execute(
        """
        SELECT id, poet_id, category_id, title, metre, rhyme
        FROM poems
        WHERE category_id = ?
        ORDER BY id
        LIMIT ? OFFSET ?
        """,
        (category_id, meta["page_size"], offset),
    ).fetchall()
    return {**meta, "items": [dict(row) for row in rows]}


def list_poems_by_poet(
    conn: sqlite3.Connection,
    poet_id: int,
    *,
    page: int = 0,
    page_size: int = 10,
) -> dict[str, Any]:
    """Fallback flat listing for poets whose corpus has no category tree."""
    total = int(
        conn.execute("SELECT COUNT(*) FROM poems WHERE poet_id = ?", (poet_id,)).fetchone()[0]
    )
    meta = _page_meta(total, page, page_size)
    offset = int(meta["page"]) * int(meta["page_size"])
    rows = conn.execute(
        """
        SELECT id, poet_id, category_id, title, metre, rhyme
        FROM poems
        WHERE poet_id = ?
        ORDER BY id
        LIMIT ? OFFSET ?
        """,
        (poet_id, meta["page_size"], offset),
    ).fetchall()
    return {**meta, "items": [dict(row) for row in rows]}


def get_poem(conn: sqlite3.Connection, poem_id: int) -> dict[str, Any] | None:
    """Return one complete work with original verse/prose text in source order."""
    poem_row = conn.execute(
        """
        SELECT
            p.id,
            p.poet_id,
            p.category_id,
            p.title,
            p.metre_id,
            p.metre,
            p.rhyme,
            po.nickname AS poet,
            c.title AS category_title
        FROM poems p
        JOIN poets po ON po.id = p.poet_id
        LEFT JOIN categories c ON c.id = p.category_id
        WHERE p.id = ?
        """,
        (poem_id,),
    ).fetchone()
    if poem_row is None:
        return None

    verses = conn.execute(
        """
        SELECT verse_order, position, couplet_index, section_index, text
        FROM verses
        WHERE poem_id = ?
        ORDER BY verse_order, id
        """,
        (poem_id,),
    ).fetchall()
    result = dict(poem_row)
    result["verses"] = [dict(row) for row in verses]
    return result


def format_poem(poem: dict[str, Any]) -> str:
    """Format a complete poem/prose work for Telegram or other clients."""
    heading = f"{poem.get('poet') or ''} — {poem.get('title') or ''}".strip(" —")
    lines = [heading, ""] if heading else []
    lines.extend(str(v.get("text") or "") for v in poem.get("verses", []) if v.get("text"))

    metre = str(poem.get("metre") or "").strip()
    rhyme = str(poem.get("rhyme") or "").strip()
    metadata: list[str] = []
    if metre:
        metadata.append(f"وزن: {metre}")
    if rhyme:
        metadata.append(f"قافیه: {rhyme}")
    if metadata:
        lines.extend(["", *metadata])
    return "\n".join(lines).strip()
