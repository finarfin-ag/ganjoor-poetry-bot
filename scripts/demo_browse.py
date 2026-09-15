#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from ganjoor_bot.browse import (
    format_poem,
    get_poem,
    list_category_children,
    list_poems_in_category,
    list_poets,
    list_root_categories,
)
from ganjoor_bot.db import connect
from ganjoor_bot.normalize import normalize_persian


def main() -> None:
    parser = argparse.ArgumentParser(description="Demo poet/category/work browsing on the real corpus")
    parser.add_argument("--db", type=Path, default=Path("data/poetry.sqlite"))
    parser.add_argument("--poet", default="حافظ")
    args = parser.parse_args()

    conn = connect(args.db)
    try:
        target = normalize_persian(args.poet)
        poet = None
        for row in conn.execute("SELECT id, nickname, name FROM poets"):
            if target in {
                normalize_persian(row["nickname"] or ""),
                normalize_persian(row["name"] or ""),
            }:
                poet = row
                break

        first_page = list_poets(conn, page=0, page_size=12)
        print(f"Corpus poets: {first_page['total']} | pages at 12/page: {first_page['pages']}")
        print("First page:")
        for item in first_page["items"]:
            print(f"  {item['id']:>4} | {item['nickname']} | {item['poem_count']} works")

        if poet is None:
            raise SystemExit(f"Poet not found: {args.poet}")

        poet_id = int(poet["id"])
        print("\n" + "=" * 72)
        print(f"POET: {poet['nickname']} (id={poet_id})")
        roots = list_root_categories(conn, poet_id)
        print(f"Root categories: {len(roots)}")
        for category in roots:
            print(
                f"  [{category['id']}] {category['title']} "
                f"children={category['child_count']} direct_works={category['direct_poem_count']}"
            )

        # Descend through the first branch until we reach a category with works.
        current = roots[0] if roots else None
        while current and int(current["direct_poem_count"] or 0) == 0:
            children = list_category_children(conn, int(current["id"]))
            if not children:
                break
            current = children[0]
            print(f"  -> [{current['id']}] {current['title']}")

        if current and int(current["direct_poem_count"] or 0) > 0:
            works = list_poems_in_category(conn, int(current["id"]), page=0, page_size=5)
            print(f"\nSample category: {current['title']} | works={works['total']}")
            for item in works["items"]:
                print(f"  [{item['id']}] {item['title']}")

            if works["items"]:
                poem = get_poem(conn, int(works["items"][0]["id"]))
                if poem:
                    preview = format_poem(poem)
                    print("\n" + "=" * 72)
                    print("FIRST WORK PREVIEW")
                    print("=" * 72)
                    print(preview[:1600])
        else:
            print("No direct works found on the first category branch; Telegram can still use the flat all-works view.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
