#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ganjoor_bot.db import connect, initialize
from ganjoor_bot.importer import import_corpus
from ganjoor_bot.markdown import export_markdown


def main() -> None:
    parser = argparse.ArgumentParser(description="Build SQLite/Markdown artifacts from ganjoor-data")
    parser.add_argument("source", type=Path, help="Path to a ganjoor-data checkout")
    parser.add_argument("--db", type=Path, default=Path("data/poetry.sqlite"))
    parser.add_argument("--markdown", type=Path, default=None)
    args = parser.parse_args()

    args.db.parent.mkdir(parents=True, exist_ok=True)
    if args.db.exists():
        args.db.unlink()

    conn = connect(args.db)
    initialize(conn)
    stats = import_corpus(args.source, conn)
    print("Imported:", stats)

    if args.markdown:
        exported = export_markdown(conn, args.markdown)
        print(f"Exported {exported} Markdown files to {args.markdown}")


if __name__ == "__main__":
    main()
