from pathlib import Path

from ganjoor_bot.db import connect, initialize
from ganjoor_bot.normalize import normalize_persian
from ganjoor_bot.search import search_verses


def test_search_matches_typing_variants(tmp_path: Path):
    conn = connect(tmp_path / "test.sqlite")
    initialize(conn)
    conn.execute("INSERT INTO poets(id, nickname, source_path) VALUES (1, 'حافظ', 'poets/hafez/poet.json')")
    conn.execute("INSERT INTO poems(id, poet_id, title, title_normalized, source_path) VALUES (10, 1, 'غزل', 'غزل', 'poets/hafez/10.json')")
    original = "که عشق آسان نمود اول ولی افتاد مشکل‌ها"
    normalized = normalize_persian(original)
    conn.execute("INSERT INTO verses(poem_id, verse_order, text, normalized_text) VALUES (10, 1, ?, ?)", (original, normalized))
    conn.execute("INSERT INTO verse_fts(text, normalized_text, poem_id, verse_order) VALUES (?, ?, 10, 1)", (original, normalized))
    conn.commit()

    rows = search_verses(conn, "عشق آسان")
    assert rows
    assert rows[0]["poet"] == "حافظ"
