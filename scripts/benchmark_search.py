#!/usr/bin/env python3
from __future__ import annotations

import argparse
import statistics
import time
from pathlib import Path

from ganjoor_bot.db import connect
from ganjoor_bot.normalize import normalize_persian
from ganjoor_bot.search import search_verses

DEFAULT_QUERIES = [
    "عشق آسان",
    "مي آيد",
    "دوش دیدم",
    "بنی آدم",
    "دل می رود ز دستم",
    "تو نیکی می کن و در دجله انداز",
]


def count_phrase_matches(conn, query: str) -> int:
    normalized = normalize_persian(query)
    escaped = normalized.replace('"', '""')
    phrase = f'"{escaped}"'
    return int(
        conn.execute(
            "SELECT COUNT(*) FROM verse_fts WHERE verse_fts MATCH ?",
            (phrase,),
        ).fetchone()[0]
    )


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * fraction)))
    return ordered[index]


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark SQLite FTS5 verse search")
    parser.add_argument("--db", type=Path, default=Path("data/poetry.sqlite"))
    parser.add_argument("--runs", type=int, default=20)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("query", nargs="*", help="Optional queries; defaults to representative Persian phrases")
    args = parser.parse_args()

    queries = args.query or DEFAULT_QUERIES
    conn = connect(args.db)

    print(f"Database: {args.db}")
    print(f"Runs/query: {args.runs} | result limit: {args.limit}")

    # Warm the SQLite page cache and Python code paths once.
    for query in queries:
        search_verses(conn, query, limit=args.limit)

    all_times: list[float] = []
    for query in queries:
        timings: list[float] = []
        result_count = 0
        for _ in range(args.runs):
            start = time.perf_counter()
            result_count = len(search_verses(conn, query, limit=args.limit))
            timings.append((time.perf_counter() - start) * 1000)

        all_times.extend(timings)
        matches = count_phrase_matches(conn, query)
        print(
            f"{query!r}: matches={matches:,}, returned={result_count}, "
            f"median={statistics.median(timings):.2f} ms, "
            f"p95={percentile(timings, 0.95):.2f} ms, min={min(timings):.2f} ms"
        )

    print(
        f"Overall: median={statistics.median(all_times):.2f} ms, "
        f"p95={percentile(all_times, 0.95):.2f} ms"
    )


if __name__ == "__main__":
    main()
