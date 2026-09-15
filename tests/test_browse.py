from pathlib import Path

from ganjoor_bot.browse import (
    format_poem,
    get_category,
    get_poem,
    get_poet,
    list_category_children,
    list_poems_in_category,
    list_poets,
    list_root_categories,
)
from ganjoor_bot.db import connect, initialize
from ganjoor_bot.normalize import normalize_persian


def _seed(conn):
    conn.execute("INSERT INTO poets(id, nickname, name, source_path) VALUES (1, 'حافظ', 'خواجه حافظ', 'poets/hafez/poet.json')")
    conn.execute("INSERT INTO poets(id, nickname, name, source_path) VALUES (2, 'سعدی', 'سعدی شیرازی', 'poets/saadi/poet.json')")

    conn.execute("INSERT INTO categories(id, poet_id, parent_id, title, source_path) VALUES (10, 1, NULL, 'دیوان حافظ', 'poets/hafez/_cat.json')")
    conn.execute("INSERT INTO categories(id, poet_id, parent_id, title, source_path) VALUES (11, 1, 10, 'غزلیات', 'poets/hafez/ghazal/_cat.json')")

    conn.execute("INSERT INTO poems(id, poet_id, category_id, title, title_normalized, metre, rhyme, source_path) VALUES (100, 1, 11, 'غزل شمارهٔ ۱', ?, 'فاعلاتن', 'ار', 'poets/hafez/ghazal/sh1.json')", (normalize_persian('غزل شمارهٔ ۱'),))
    conn.execute("INSERT INTO poems(id, poet_id, category_id, title, title_normalized, source_path) VALUES (101, 1, 11, 'غزل شمارهٔ ۲', ?, 'poets/hafez/ghazal/sh2.json')", (normalize_persian('غزل شمارهٔ ۲'),))
    conn.execute("INSERT INTO poems(id, poet_id, category_id, title, title_normalized, source_path) VALUES (200, 2, NULL, 'بوستان', ?, 'poets/saadi/boostan.json')", (normalize_persian('بوستان'),))

    for order, text in enumerate(("الا یا ایها الساقی", "که عشق آسان نمود اول"), start=1):
        normalized = normalize_persian(text)
        conn.execute("INSERT INTO verses(poem_id, verse_order, text, normalized_text) VALUES (100, ?, ?, ?)", (order, text, normalized))
        conn.execute("INSERT INTO verse_fts(text, normalized_text, poem_id, verse_order) VALUES (?, ?, 100, ?)", (text, normalized, order))
    conn.commit()


def test_list_poets_and_counts(tmp_path: Path):
    conn = connect(tmp_path / "test.sqlite")
    initialize(conn)
    _seed(conn)

    page = list_poets(conn, page=0, page_size=1)
    assert page["total"] == 2
    assert page["pages"] == 2
    assert len(page["items"]) == 1

    all_items = list_poets(conn, page=0, page_size=10)["items"]
    counts = {item["nickname"]: item["poem_count"] for item in all_items}
    assert counts["حافظ"] == 2
    assert counts["سعدی"] == 1


def test_category_navigation(tmp_path: Path):
    conn = connect(tmp_path / "test.sqlite")
    initialize(conn)
    _seed(conn)

    poet = get_poet(conn, 1)
    assert poet and poet["poem_count"] == 2

    roots = list_root_categories(conn, 1)
    assert [row["title"] for row in roots] == ["دیوان حافظ"]
    assert roots[0]["child_count"] == 1

    children = list_category_children(conn, 10)
    assert [row["title"] for row in children] == ["غزلیات"]
    assert get_category(conn, 11)["direct_poem_count"] == 2


def test_poem_listing_and_full_text(tmp_path: Path):
    conn = connect(tmp_path / "test.sqlite")
    initialize(conn)
    _seed(conn)

    page = list_poems_in_category(conn, 11, page=0, page_size=1)
    assert page["total"] == 2
    assert page["has_next"] is True
    assert page["items"][0]["id"] == 100

    poem = get_poem(conn, 100)
    assert poem is not None
    assert poem["poet"] == "حافظ"
    assert [v["text"] for v in poem["verses"]] == ["الا یا ایها الساقی", "که عشق آسان نمود اول"]

    text = format_poem(poem)
    assert "حافظ — غزل شمارهٔ ۱" in text
    assert "الا یا ایها الساقی" in text
    assert "وزن: فاعلاتن" in text
    assert "قافیه: ار" in text
