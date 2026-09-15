from __future__ import annotations

import random
import sqlite3
from typing import Any

from .normalize import normalize_persian


def _resolve_hafez_id(conn: sqlite3.Connection) -> int:
    """Resolve Hafez without hard-coding a Ganjoor numeric poet id."""
    target = normalize_persian("حافظ")
    for row in conn.execute("SELECT id, nickname, name FROM poets"):
        if normalize_persian(row["nickname"] or "") == target:
            return int(row["id"])
        if normalize_persian(row["name"] or "") == target:
            return int(row["id"])
    raise LookupError("Hafez was not found in the poetry database")


def _hafez_ghazal_ids(conn: sqlite3.Connection, poet_id: int) -> list[int]:
    rows = conn.execute(
        """
        SELECT id
        FROM poems
        WHERE poet_id = ?
          AND (title LIKE 'غزل%' OR title_normalized LIKE 'غزل%')
        ORDER BY id
        """,
        (poet_id,),
    ).fetchall()
    if rows:
        return [int(row["id"]) for row in rows]

    # Defensive fallback for a future upstream title/schema change.
    rows = conn.execute(
        "SELECT id FROM poems WHERE poet_id = ? ORDER BY id",
        (poet_id,),
    ).fetchall()
    return [int(row["id"]) for row in rows]


def get_hafez_fortune(
    conn: sqlite3.Connection,
    *,
    rng: random.Random | random.SystemRandom | None = None,
) -> dict[str, Any]:
    """Return one complete random Hafez ghazal from the local corpus.

    The original verse text is returned verbatim from the corpus. Interpretations
    or AI-generated summaries are intentionally not mixed into this result.
    """
    poet_id = _resolve_hafez_id(conn)
    poem_ids = _hafez_ghazal_ids(conn, poet_id)
    if not poem_ids:
        raise LookupError("No Hafez poems were found in the poetry database")

    chooser = rng or random.SystemRandom()
    poem_id = int(chooser.choice(poem_ids))

    poem = conn.execute(
        """
        SELECT
            p.id,
            p.title,
            p.metre,
            p.rhyme,
            p.category_id,
            po.nickname AS poet,
            c.title AS category_title
        FROM poems p
        JOIN poets po ON po.id = p.poet_id
        LEFT JOIN categories c ON c.id = p.category_id
        WHERE p.id = ?
        """,
        (poem_id,),
    ).fetchone()
    if poem is None:
        raise LookupError(f"Selected Hafez poem {poem_id} disappeared")

    verses = conn.execute(
        """
        SELECT verse_order, position, couplet_index, text
        FROM verses
        WHERE poem_id = ?
        ORDER BY verse_order
        """,
        (poem_id,),
    ).fetchall()

    return {
        "poem_id": poem_id,
        "poet": poem["poet"],
        "title": poem["title"] or "",
        "category_id": poem["category_id"],
        "category_title": poem["category_title"],
        "metre": poem["metre"],
        "rhyme": poem["rhyme"],
        "verses": [
            {
                "verse_order": int(row["verse_order"]),
                "position": row["position"],
                "couplet_index": row["couplet_index"],
                "text": row["text"],
            }
            for row in verses
        ],
    }


def format_fortune_text(fortune: dict[str, Any]) -> str:
    """Format a fortune for a text client while preserving original verse text."""
    lines = [f"{fortune['poet']} — {fortune['title']}", ""]
    lines.extend(str(verse["text"]) for verse in fortune["verses"])

    if fortune.get("metre"):
        lines.extend(["", f"وزن: {fortune['metre']}"])

    return "\n".join(lines).strip()
