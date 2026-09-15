from __future__ import annotations

import sqlite3
from difflib import SequenceMatcher
from itertools import combinations
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

    for i in range(len(tokens) - 1):
        if tokens[i] in {"می", "نمی"}:
            joined = tokens[:i] + [tokens[i] + tokens[i + 1]] + tokens[i + 2 :]
            variants.add(tuple(joined))

    for i, token in enumerate(tokens):
        if token.startswith("نمی") and len(token) > 3:
            split = tokens[:i] + ["نمی", token[3:]] + tokens[i + 1 :]
            variants.add(tuple(split))
        elif token.startswith("می") and len(token) > 2:
            split = tokens[:i] + ["می", token[2:]] + tokens[i + 1 :]
            variants.add(tuple(split))

    ordered = [normalized]
    ordered.extend(
        " ".join(parts)
        for parts in sorted(variants)
        if " ".join(parts) != normalized
    )
    return ordered


def _mode_expression(normalized: str, mode: SearchMode) -> str:
    if mode == "exact":
        return f"normalized_text:{_fts_phrase(normalized)}"

    terms = [part for part in normalized.split() if part]
    if not terms:
        return ""

    operator = " AND " if mode == "all" else " OR "
    return operator.join(
        f"normalized_text:{_fts_phrase(term)}" for term in terms
    )


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
    """Search normalized primary text with optional filters.

    Modes:
    - ``exact``: the normalized query must appear as one phrase.
    - ``all``: every normalized term must appear, in any order.
    - ``any``: at least one normalized term must appear.

    This searches only indexed primary text (verse/prose ``Text`` fields), not
    AI-generated PoemSummary/CoupletSummary commentary.
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


def _token_f1(left: str, right: str) -> float:
    left_tokens = set(left.split())
    right_tokens = set(right.split())
    if not left_tokens or not right_tokens:
        return 0.0
    common = len(left_tokens & right_tokens)
    if common == 0:
        return 0.0
    return (2.0 * common) / (len(left_tokens) + len(right_tokens))


def _window_similarity(query: str, candidate: str) -> float:
    """Compare a query with the best similarly-sized token window."""
    q_tokens = query.split()
    c_tokens = candidate.split()
    if not q_tokens or not c_tokens:
        return 0.0

    if len(c_tokens) <= len(q_tokens) + 2:
        return SequenceMatcher(None, query, candidate).ratio()

    best = 0.0
    low = max(1, len(q_tokens) - 2)
    high = min(len(c_tokens), len(q_tokens) + 2)
    for size in range(low, high + 1):
        for start in range(0, len(c_tokens) - size + 1):
            window = " ".join(c_tokens[start : start + size])
            best = max(best, SequenceMatcher(None, query, window).ratio())
    return best


def _fuzzy_similarity(query: str, candidate: str) -> float:
    """Return a 0..1 similarity score tolerant of spacing and partial recall."""
    scores: list[float] = []
    for variant in _spacing_variants(query) or [query]:
        token_score = _token_f1(variant, candidate)
        compact_score = SequenceMatcher(
            None,
            variant.replace(" ", ""),
            candidate.replace(" ", ""),
        ).ratio()
        window_score = _window_similarity(variant, candidate)
        scores.append(
            0.30 * token_score
            + 0.35 * compact_score
            + 0.35 * window_score
        )
    return max(scores, default=0.0)


def _candidate_pairs(normalized: str, max_pairs: int = 8) -> list[str]:
    """Build a few AND-pair queries for fuzzy candidate discovery.

    This helps when several remembered words differ from the source. Very common
    Persian function words are excluded, while short content verbs such as
    ``کن`` remain useful.
    """
    stopwords = {
        "و", "در", "از", "به", "که", "را", "با", "بر", "برای", "تا",
        "این", "آن", "یک", "من", "تو", "او", "ما", "شما", "ایشان",
        "می", "نمی",
    }
    variants = _spacing_variants(normalized) or [normalized]
    terms: list[str] = []
    for variant in variants:
        for term in variant.split():
            if len(term) >= 2 and term not in stopwords and term not in terms:
                terms.append(term)

    if len(terms) < 2:
        return []

    pairs = list(combinations(terms[:6], 2))
    pairs.sort(key=lambda pair: -(len(pair[0]) + len(pair[1])))
    return [" ".join(pair) for pair in pairs[:max_pairs]]


def smart_search(
    conn: sqlite3.Connection,
    query: str,
    limit: int = 10,
    *,
    poet: int | str | None = None,
    category_id: int | None = None,
    fuzzy_threshold: float = 0.45,
    candidate_limit: int = 500,
) -> list[dict[str, object]]:
    """Search primary text with exact -> all-words -> fuzzy fallback.

    Each returned dictionary contains the normal search fields plus:
    - ``match_type``: ``exact``, ``all`` or ``fuzzy``
    - ``similarity``: 0..1 lexical similarity (exact is always 1.0)

    Fuzzy matching is deliberately a fallback. FTS5 first narrows the corpus to
    a few hundred candidates, then Python scores only those candidates. This
    avoids scanning millions of rows and keeps approximate matches explainable.
    """
    if limit <= 0:
        return []

    normalized = normalize_persian(query)
    if not normalized:
        return []

    candidates: dict[tuple[int, int], dict[str, object]] = {}

    def add_rows(rows: list[sqlite3.Row], match_type: str) -> None:
        for row in rows:
            key = (int(row["poem_id"]), int(row["verse_order"]))
            item = candidates.get(key)
            if item is None:
                item = dict(row)
                item["match_type"] = match_type
                item["similarity"] = (
                    1.0
                    if match_type == "exact"
                    else _fuzzy_similarity(normalized, str(row["normalized_text"]))
                )
                candidates[key] = item
            elif match_type == "exact":
                item["match_type"] = "exact"
                item["similarity"] = 1.0
            elif match_type == "all" and item["match_type"] == "fuzzy":
                item["match_type"] = "all"

    exact_rows = search_verses(
        conn,
        query,
        limit=max(limit * 4, 40),
        mode="exact",
        poet=poet,
        category_id=category_id,
        diversify=False,
    )
    add_rows(exact_rows, "exact")

    all_rows = search_verses(
        conn,
        query,
        limit=max(limit * 8, 80),
        mode="all",
        poet=poet,
        category_id=category_id,
        diversify=False,
    )
    add_rows(all_rows, "all")

    any_rows = search_verses(
        conn,
        query,
        limit=max(candidate_limit, limit * 20),
        mode="any",
        poet=poet,
        category_id=category_id,
        diversify=False,
    )
    add_rows(any_rows, "fuzzy")

    # When the user's recollection has multiple changed words, broad OR ranking
    # can miss the right line. A handful of content-word pairs gives FTS another
    # cheap route to plausible candidates without scanning the entire corpus.
    for pair_query in _candidate_pairs(normalized):
        pair_rows = search_verses(
            conn,
            pair_query,
            limit=80,
            mode="all",
            poet=poet,
            category_id=category_id,
            diversify=False,
        )
        add_rows(pair_rows, "fuzzy")

    priority = {"exact": 0, "all": 1, "fuzzy": 2}
    filtered = [
        item
        for item in candidates.values()
        if item["match_type"] != "fuzzy"
        or float(item["similarity"]) >= fuzzy_threshold
    ]
    filtered.sort(
        key=lambda item: (
            priority[str(item["match_type"])],
            -float(item["similarity"]),
            float(item.get("score") or 0.0),
            int(item["poem_id"]),
            int(item["verse_order"]),
        )
    )

    selected: list[dict[str, object]] = []
    seen_poems: set[int] = set()
    for item in filtered:
        poem_id = int(item["poem_id"])
        if poem_id in seen_poems:
            continue
        seen_poems.add(poem_id)
        selected.append(item)
        if len(selected) >= limit:
            break

    return selected
