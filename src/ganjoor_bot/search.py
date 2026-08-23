from __future__ import annotations

import sqlite3

from .normalize import normalize_persian


def _fts_phrase(text: str) -> str:
    escaped = text.replace('"', '""')
    return f'"{escaped}"'


def search_verses(conn: sqlite3.Connection, query: str, limit: int = 20) -> list[sqlite3.Row]:
    normalized = normalize_persian(query)
    if not normalized:
        return []

    sql = """
        SELECT
            v.poem_id,
            v.verse_order,
            v.text,
            p.title AS poem_title,
            po.nickname AS poet
        FROM verse_fts f
        JOIN verses v
          ON v.poem_id = CAST(f.poem_id AS INTEGER)
         AND v.verse_order = CAST(f.verse_order AS INTEGER)
        JOIN poems p ON p.id = v.poem_id
        JOIN poets po ON po.id = p.poet_id
        WHERE verse_fts MATCH ?
        ORDER BY bm25(verse_fts)
        LIMIT ?
    """
    return list(conn.execute(sql, (_fts_phrase(normalized), limit)))
