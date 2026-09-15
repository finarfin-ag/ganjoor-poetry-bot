from __future__ import annotations

import sqlite3
from typing import Literal

from .normalize import normalize_persian

SearchMode = Literal["exact", "all", "any"]


def _fts_phrase(text: str) -> str:
    escaped = text.replace('"', '""')
    return f'"{escaped}"'


def _spacing_variants(normalized: str) -> list[str]:
    """Return useful query variants for Persian spacing/half-spacing differences.

    The corpus currently removes ZWNJ during normalization, so ``می‌کن`` becomes
    ``میکن`` while a user may type ``می کن``. We generate both joined and split
    forms for the productive verbal prefixes ``می`` and ``نمی`` without changing
    the stored database or requiring a rebuild.
    """
    tokens = [part for part in normalized.split() if part]
    if not tokens:
        return []

    variants: set[tuple[str, ...]] = {tuple(tokens)}

    # Join explicit prefix + verb: "می کن" -> "میکن".
    for i in range(len(tokens) - 1):
        if tokens[i] in {"می", "نمی"}:
            joined = tokens[:i] + [tokens[i] + tokens[i + 1]] + tokens[i + 2 :]
            variants.add(tuple(joined))

    # Split compact forms too, so a query typed as "میکن" can also match a
    # corpus line written with a normal space as "می کن".
    for i, token in enumerate(tokens):
        if token.startswith("نمی") and len(token) > 3:
            split = tokens[:i] + ["نمی", token[3:]] + tokens[i + 1 :]
            variants.add(tuple(split))
        elif token.startswith("می") and len(token) > 2:
            split = tokens[:i] + ["می", token[2:]] + tokens[i + 1 :]
            variants.add(tuple(split))

    # Keep the user's directly normalized form first for stable ranking.
    ordered = [normalized]
    ordered.extend(" ".join(parts) for parts in sorted(variants) if " ".join(parts) != normalized)
    return ordered


def _mode_expression(normalized: str, mode: SearchMode) -> str:
    if mode == "exact":
        return f"normalized_text:{_fts_phrase(normalized)}"

    terms = [part for part in normalized.split() if part]
    if not terms:
        return ""

    operator = " AND " if mode == "all" else " OR "
    return operator.join(f"normalized_text:{_fts_phrase(term)}" for term in terms)


def _build_match_query(normalized: str, mode: SearchMode) -> str:
    expressions = [
        _mode_expression(variant, mode)
        for variant in _spacing_variants(normalized)
    ]
    expressions = [expr for expr in expressions if expr]
    if not expressions:
        return ""
    if len(expressions) == 1:
        return expressions[0]
    return " OR ".join(f"({expr})" for expr in expressions)


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

    Common Persian ``می``/``نمی`` spacing variants are expanded at query time so
    ``می کن``, ``می‌کن`` and ``میکن`` can match the same indexed text.

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
