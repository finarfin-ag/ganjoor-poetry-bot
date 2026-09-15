#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ganjoor_bot.db import connect
from ganjoor_bot.search import smart_search


DEFAULT_QUERIES = [
    "دل میره ز دستم صاحب دلان خدا را",
    "دلم میرود ز دست صاحبدلان",
    "تو نیکی می کن و در دجله انداز",
    "دوش دیدم که ملائک در میخانه زدند",
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Try smart/fuzzy search against a built database")
    parser.add_argument("--db", type=Path, default=Path("data/poetry.sqlite"))
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("query", nargs="*")
    args = parser.parse_args()

    conn = connect(args.db)
    queries = args.query or DEFAULT_QUERIES

    for query in queries:
        started = time.perf_counter()
        rows = smart_search(conn, query, limit=args.limit)
        elapsed_ms = (time.perf_counter() - started) * 1000

        print("\n" + "=" * 78)
        print(f"QUERY: {query}")
        print(f"RESULTS: {len(rows)} | {elapsed_ms:.1f} ms")
        print("=" * 78)

        for index, row in enumerate(rows, start=1):
            similarity = float(row["similarity"])
            print(
                f"{index}. [{row['match_type']}] {similarity:.3f} | "
                f"{row['poet']} — {row['poem_title']}"
            )
            print(row["text"])


if __name__ == "__main__":
    main()
