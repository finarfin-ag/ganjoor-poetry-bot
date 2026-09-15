from __future__ import annotations

import sqlite3
from typing import Literal

from .normalize import normalize_persian

SearchMode = Literal["exact", "all", "any"]


def _fts_phrase(text: str) -> str:
    escaped = text.replace('"', '""')
    return f'"{escaped}"'


def _build_match_query(normalized: str, mode: SearchMode) -> str:
    if mode == "exact":
        return f"normalized_text:{_fts_phrase(normalized)}"

    terms = [part for part in normalized.split() if part]
    if not terms:
        return ""

    operator = " AND " if mode == "all" else " OR "
    return operator.join(
        f"normalized_text:{_fts_phrase(term)}" for term in terms
    )


def _resolve_poet_id(conn: sqlite3.Connection, poet: int | str | None) -> int | None:
    if poet is None:
        return None
    if isinstance(poet, int):
        return poet

    target = normalize_persian(poet)
    for row in conn.execute("SELECT id, nickname, name FROM poets"):
        if normalize_persian(row["nickname"] or "") == target:
            return int(row["id"])
        if normalize_persian(row["name"] or "") == target:
            return int(row["id"])

    return -1


def search_verses(
    conn: sqlite3.Connection,
    query: str,
    limit: int = 20,
    *,
    mode: SearchMode = "exact",
    poet: int | str | None = None,
    category_id: int | None = None,
    diversify: bool = True,
) -> list[sqlite3.Row]:
    """Search normalized Persian verse text with optional filters.

    Modes:
    - ``exact``: the normalized query must appear as one phrase.
    - ``all``: every normalized term must appear, in any order.
    - ``any``: at least one normalized term must appear.

    By default results are diversified so a single poem does not occupy several
    top-result slots. Set ``diversify=False`` when every matching verse matters.
    """
    if limit <= 0:
        return []
    if mode not in {"exact", "all", "any"}:
        raise ValueError(f"Unsupported search mode: {mode}")

    normalized = normalize_persian(query)
    if not normalized:
        return []

    match_query = _build_match_query(normalized, mode)
    if not match_query:
        return []

    poet_id = _resolve_poet_id(conn, poet)

    clauses = ["verse_fts MATCH ?"]
    params: list[object] = [match_query]

    if poet_id is not None:
        clauses.append("p.poet_id = ?")
        params.append(poet_id)
    if category_id is not None:
        clauses.append("p.category_id = ?")
        params.append(category_id)

    candidate_limit = max(limit, limit * 8 if diversify else limit)
    params.append(candidate_limit)

    sql = f"""
        SELECT
            v.poem_id,
            v.verse_order,
            v.text,
            v.normalized_text,
            p.title AS poem_title,
            p.category_id,
            c.title AS category_title,
            po.id AS poet_id,
            po.nickname AS poet,
            bm25(verse_fts) AS score
        FROM verse_fts f
        JOIN verses v
          ON v.poem_id = CAST(f.poem_id AS INTEGER)
         AND v.verse_order = CAST(f.verse_order AS INTEGER)
        JOIN poems p ON p.id = v.poem_id
        JOIN poets po ON po.id = p.poet_id
        LEFT JOIN categories c ON c.id = p.category_id
        WHERE {' AND '.join(clauses)}
        ORDER BY score, v.poem_id, v.verse_order
        LIMIT ?
    """

    rows = list(conn.execute(sql, params))
    if not diversify:
        return rows[:limit]

    selected: list[sqlite3.Row] = []
    seen_poems: set[int] = set()
    for row in rows:
        poem_id = int(row["poem_id"])
        if poem_id in seen_poems:
            continue
        seen_poems.add(poem_id)
        selected.append(row)
        if len(selected) >= limit:
            break

    return selected
