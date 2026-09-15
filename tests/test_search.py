from pathlib import Path

from ganjoor_bot.db import connect, initialize
from ganjoor_bot.normalize import normalize_persian
from ganjoor_bot.search import search_verses


def _insert_verse(conn, poem_id: int, poet_id: int, poet: str, title: str, verse_order: int, text: str, category_id: int | None = None):
    conn.execute(
        "INSERT OR IGNORE INTO poets(id, nickname, source_path) VALUES (?, ?, ?)",
        (poet_id, poet, f"poets/{poet_id}/poet.json"),
    )
    if category_id is not None:
        conn.execute(
            "INSERT OR IGNORE INTO categories(id, poet_id, title, source_path) VALUES (?, ?, ?, ?)",
            (category_id, poet_id, f"cat-{category_id}", f"poets/{poet_id}/cat-{category_id}/_cat.json"),
        )
    conn.execute(
        "INSERT OR IGNORE INTO poems(id, poet_id, category_id, title, title_normalized, source_path) VALUES (?, ?, ?, ?, ?, ?)",
        (poem_id, poet_id, category_id, title, normalize_persian(title), f"poets/{poet_id}/{poem_id}.json"),
    )
    normalized = normalize_persian(text)
    conn.execute(
        "INSERT INTO verses(poem_id, verse_order, text, normalized_text) VALUES (?, ?, ?, ?)",
        (poem_id, verse_order, text, normalized),
    )
    conn.execute(
        "INSERT INTO verse_fts(text, normalized_text, poem_id, verse_order) VALUES (?, ?, ?, ?)",
        (text, normalized, poem_id, verse_order),
    )


def test_search_matches_typing_variants(tmp_path: Path):
    conn = connect(tmp_path / "test.sqlite")
    initialize(conn)
    _insert_verse(conn, 10, 1, "حافظ", "غزل", 1, "که عشق آسان نمود اول ولی افتاد مشکل‌ها")
    conn.commit()

    rows = search_verses(conn, "عشق آسان")
    assert rows
    assert rows[0]["poet"] == "حافظ"


def test_search_matches_mi_spacing_variants(tmp_path: Path):
    conn = connect(tmp_path / "test.sqlite")
    initialize(conn)
    _insert_verse(conn, 10, 1, "سعدی", "بوستان", 1, "تو نیکی می‌کن و در دجله انداز")
    _insert_verse(conn, 11, 1, "سعدی", "بوستان ۲", 1, "من این کار را نمی‌کنم")
    conn.commit()

    for query in ("تو نیکی می کن و در دجله انداز", "تو نیکی می‌کن و در دجله انداز", "تو نیکی میکن و در دجله انداز"):
        rows = search_verses(conn, query, mode="exact")
        assert rows
        assert rows[0]["poem_id"] == 10

    for query in ("نمی کنم", "نمی‌کنم", "نمیکنم"):
        rows = search_verses(conn, query, mode="exact")
        assert rows
        assert rows[0]["poem_id"] == 11


def test_search_modes(tmp_path: Path):
    conn = connect(tmp_path / "test.sqlite")
    initialize(conn)
    _insert_verse(conn, 10, 1, "حافظ", "غزل ۱", 1, "عشق آسان نمود")
    _insert_verse(conn, 11, 1, "حافظ", "غزل ۲", 1, "عشق مشکل است")
    _insert_verse(conn, 12, 2, "سعدی", "غزل ۳", 1, "کار آسان شد")
    conn.commit()

    exact = search_verses(conn, "عشق آسان", mode="exact")
    assert [row["poem_id"] for row in exact] == [10]

    all_rows = search_verses(conn, "آسان عشق", mode="all")
    assert [row["poem_id"] for row in all_rows] == [10]

    any_rows = search_verses(conn, "عشق آسان", mode="any", limit=10)
    assert {row["poem_id"] for row in any_rows} == {10, 11, 12}


def test_search_poet_and_category_filters(tmp_path: Path):
    conn = connect(tmp_path / "test.sqlite")
    initialize(conn)
    _insert_verse(conn, 10, 1, "حافظ", "غزل حافظ", 1, "دل می رود ز دستم", category_id=100)
    _insert_verse(conn, 20, 2, "سعدی", "غزل سعدی", 1, "دل از دست رفت", category_id=200)
    conn.commit()

    by_poet = search_verses(conn, "دل", mode="any", poet="حافظ")
    assert len(by_poet) == 1
    assert by_poet[0]["poet"] == "حافظ"

    by_category = search_verses(conn, "دل", mode="any", category_id=200)
    assert len(by_category) == 1
    assert by_category[0]["poet"] == "سعدی"


def test_search_diversifies_poems(tmp_path: Path):
    conn = connect(tmp_path / "test.sqlite")
    initialize(conn)
    _insert_verse(conn, 10, 1, "حافظ", "غزل ۱", 1, "دوش دیدم الف")
    _insert_verse(conn, 10, 1, "حافظ", "غزل ۱", 2, "دوش دیدم ب")
    _insert_verse(conn, 20, 2, "سعدی", "غزل ۲", 1, "دوش دیدم ج")
    conn.commit()

    diversified = search_verses(conn, "دوش دیدم", limit=2)
    assert [row["poem_id"] for row in diversified] == [10, 20]

    every_verse = search_verses(conn, "دوش دیدم", limit=2, diversify=False)
    assert len(every_verse) == 2
