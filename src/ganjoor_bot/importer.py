from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Iterable

from .normalize import normalize_persian


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _first(obj: dict[str, Any], *keys: str, default=None):
    for key in keys:
        if key in obj and obj[key] is not None:
            return obj[key]
    return default


def _iter_poem_files(root: Path) -> Iterable[Path]:
    for path in (root / "poets").rglob("*.json"):
        if path.name not in {"poet.json", "_cat.json"}:
            yield path


def import_corpus(
    root: Path,
    conn: sqlite3.Connection,
    progress_every: int = 5000,
    commit_every: int = 1000,
) -> dict[str, int]:
    """Import the static ``ganjoor-data`` export.

    The original source text is preserved while normalized text is stored for
    search. Long imports are committed in batches so an interrupted SSH session
    cannot discard the entire run. A fresh build is still recommended after an
    interruption; the partial database is retained only for diagnosis.
    """
    if progress_every < 0:
        raise ValueError("progress_every must be >= 0")
    if commit_every <= 0:
        raise ValueError("commit_every must be > 0")

    started = time.monotonic()
    manifest = load_json(root / "manifest.json")
    expected_poems = int(manifest.get("PoemsCount", 0) or 0)

    conn.execute(
        "INSERT OR REPLACE INTO metadata(key, value) VALUES (?, ?)",
        ("manifest", json.dumps(manifest, ensure_ascii=False)),
    )
    conn.execute(
        "INSERT OR REPLACE INTO metadata(key, value) VALUES ('build_status', 'importing')"
    )
    for source_key, dest_key in (
        ("SchemaVersion", "upstream_schema_version"),
        ("GeneratedAtUtc", "upstream_generated_at"),
    ):
        if source_key in manifest:
            conn.execute(
                "INSERT OR REPLACE INTO metadata(key, value) VALUES (?, ?)",
                (dest_key, str(manifest[source_key])),
            )

    poet_count = category_count = poem_count = verse_count = 0

    for poet_json in (root / "poets").glob("*/poet.json"):
        poet = load_json(poet_json)
        poet_id = int(_first(poet, "Id", "id"))
        nickname = str(
            _first(
                poet,
                "Nickname",
                "nickname",
                "Name",
                "name",
                default=poet_json.parent.name,
            )
        )
        name = _first(poet, "Name", "name", "FullName", "fullName")
        description = _first(poet, "Description", "description", "Bio", "bio")
        rel = poet_json.relative_to(root).as_posix()
        conn.execute(
            "INSERT OR REPLACE INTO poets(id, nickname, name, description, source_path) VALUES (?, ?, ?, ?, ?)",
            (poet_id, nickname, name, description, rel),
        )
        poet_count += 1

    category_records: list[tuple[int, int, int | None, str, str | None, str]] = []
    for cat_json in (root / "poets").rglob("_cat.json"):
        cat = load_json(cat_json)
        cat_id_raw = _first(cat, "Id", "id")
        poet_id_raw = _first(cat, "PoetId", "poetId")
        if cat_id_raw is None or poet_id_raw is None:
            continue
        parent_raw = _first(cat, "ParentId", "parentId")
        record = (
            int(cat_id_raw),
            int(poet_id_raw),
            int(parent_raw) if parent_raw is not None else None,
            str(_first(cat, "Title", "title", default=cat_json.parent.name)),
            _first(cat, "Description", "description"),
            cat_json.relative_to(root).as_posix(),
        )
        category_records.append(record)
        conn.execute(
            "INSERT OR REPLACE INTO categories(id, poet_id, parent_id, title, description, source_path) VALUES (?, ?, NULL, ?, ?, ?)",
            (record[0], record[1], record[3], record[4], record[5]),
        )
        category_count += 1

    for cat_id, _poet_id, parent_id, _title, _description, _source_path in category_records:
        if parent_id is not None:
            conn.execute("UPDATE categories SET parent_id = ? WHERE id = ?", (parent_id, cat_id))

    # Persist metadata before the long poem import starts.
    conn.commit()
    target = f" / {expected_poems:,}" if expected_poems else ""
    print(
        f"Indexed metadata: {poet_count:,} poets, {category_count:,} categories. "
        f"Starting poem import{target}...",
        flush=True,
    )

    for poem_json in _iter_poem_files(root):
        poem = load_json(poem_json)
        poem_id_raw = _first(poem, "Id", "id")
        category_id_raw = _first(poem, "CatId", "catId", "CategoryId", "categoryId")
        verses = _first(poem, "Verses", "verses")

        if poem_id_raw is None or category_id_raw is None or not isinstance(verses, list):
            continue

        poem_id = int(poem_id_raw)
        category_id = int(category_id_raw)
        cat_row = conn.execute(
            "SELECT poet_id FROM categories WHERE id = ?", (category_id,)
        ).fetchone()
        if cat_row is None:
            raise ValueError(
                f"Poem {poem_id} references missing category {category_id}: {poem_json}"
            )
        poet_id = int(cat_row["poet_id"])

        title = str(_first(poem, "Title", "title", default=""))
        metre_obj = _first(poem, "Metre", "metre")
        metre_id = None
        metre = None
        if isinstance(metre_obj, dict):
            metre_id = _first(metre_obj, "Id", "id")
            metre = _first(metre_obj, "Rhythm", "rhythm")
        elif metre_obj is not None:
            metre = str(metre_obj)
        rhyme = _first(poem, "RhymeLetters", "rhymeLetters", "Rhyme", "rhyme")
        rel = poem_json.relative_to(root).as_posix()
        title_normalized = normalize_persian(title)

        conn.execute(
            "INSERT OR REPLACE INTO poems(id, poet_id, category_id, title, title_normalized, metre_id, metre, rhyme, source_path) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                poem_id,
                poet_id,
                category_id,
                title,
                title_normalized,
                metre_id,
                metre,
                rhyme,
                rel,
            ),
        )
        conn.execute(
            "INSERT INTO poem_fts(title, title_normalized, poem_id) VALUES (?, ?, ?)",
            (title, title_normalized, poem_id),
        )
        poem_count += 1

        for fallback_order, verse in enumerate(verses, start=1):
            text = _first(verse, "Text", "text")
            if not text:
                continue
            order = int(
                _first(
                    verse,
                    "VOrder",
                    "vOrder",
                    "Order",
                    "order",
                    default=fallback_order,
                )
            )
            position = _first(
                verse, "Position", "position", "VersePosition", "versePosition"
            )
            couplet_index = _first(verse, "CoupletIndex", "coupletIndex")
            section_index = _first(
                verse,
                "SectionIndex1",
                "sectionIndex1",
                "SectionIndex",
                "sectionIndex",
            )
            normalized = normalize_persian(str(text))
            conn.execute(
                "INSERT OR REPLACE INTO verses(poem_id, verse_order, position, couplet_index, section_index, text, normalized_text) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    poem_id,
                    order,
                    position,
                    couplet_index,
                    section_index,
                    str(text),
                    normalized,
                ),
            )
            conn.execute(
                "INSERT INTO verse_fts(text, normalized_text, poem_id, verse_order) VALUES (?, ?, ?, ?)",
                (str(text), normalized, poem_id, order),
            )
            verse_count += 1

        if poem_count % commit_every == 0:
            conn.commit()

        if progress_every > 0 and poem_count % progress_every == 0:
            elapsed = max(time.monotonic() - started, 0.001)
            rate = poem_count / elapsed
            print(
                f"Imported {poem_count:,}{target} poems / {verse_count:,} verses "
                f"({rate:,.0f} poems/s)",
                flush=True,
            )

    conn.execute(
        "INSERT OR REPLACE INTO metadata(key, value) VALUES ('build_status', 'complete')"
    )
    conn.execute(
        "INSERT OR REPLACE INTO metadata(key, value) VALUES ('imported_poems', ?)",
        (str(poem_count),),
    )
    conn.execute(
        "INSERT OR REPLACE INTO metadata(key, value) VALUES ('imported_verses', ?)",
        (str(verse_count),),
    )
    conn.commit()

    if expected_poems and poem_count != expected_poems:
        print(
            f"WARNING: manifest lists {expected_poems:,} poems but importer accepted "
            f"{poem_count:,} poem files.",
            flush=True,
        )

    return {
        "poets": poet_count,
        "categories": category_count,
        "poems": poem_count,
        "verses": verse_count,
    }
