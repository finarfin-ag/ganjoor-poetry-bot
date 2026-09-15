import random
from pathlib import Path

from ganjoor_bot.db import connect, initialize
from ganjoor_bot.fortune import format_fortune_text, get_hafez_fortune
from ganjoor_bot.normalize import normalize_persian


def test_hafez_fortune_returns_complete_ghazal(tmp_path: Path):
    conn = connect(tmp_path / "test.sqlite")
    initialize(conn)

    conn.execute(
        "INSERT INTO poets(id, nickname, name, source_path) VALUES (1, 'حافظ', 'خواجه حافظ شیرازی', 'poets/hafez/poet.json')"
    )
    conn.execute(
        "INSERT INTO categories(id, poet_id, title, source_path) VALUES (10, 1, 'غزلیات', 'poets/hafez/ghazal/_cat.json')"
    )
    conn.execute(
        """
        INSERT INTO poems(id, poet_id, category_id, title, title_normalized, metre, rhyme, source_path)
        VALUES (100, 1, 10, 'غزل شمارهٔ ۱', ?, 'فاعلاتن', 'ا', 'poets/hafez/ghazal/sh1.json')
        """,
        (normalize_persian("غزل شمارهٔ ۱"),),
    )
    conn.execute(
        "INSERT INTO verses(poem_id, verse_order, position, couplet_index, text, normalized_text) VALUES (100, 1, 'Right', 0, 'الا یا ایها الساقی', ?) ",
        (normalize_persian("الا یا ایها الساقی"),),
    )
    conn.execute(
        "INSERT INTO verses(poem_id, verse_order, position, couplet_index, text, normalized_text) VALUES (100, 2, 'Left', 0, 'ادر کاسا و ناولها', ?) ",
        (normalize_persian("ادر کاسا و ناولها"),),
    )
    conn.commit()

    fortune = get_hafez_fortune(conn, rng=random.Random(1))

    assert fortune["poet"] == "حافظ"
    assert fortune["title"] == "غزل شمارهٔ ۱"
    assert [v["text"] for v in fortune["verses"]] == [
        "الا یا ایها الساقی",
        "ادر کاسا و ناولها",
    ]
    assert fortune["metre"] == "فاعلاتن"

    formatted = format_fortune_text(fortune)
    assert "حافظ — غزل شمارهٔ ۱" in formatted
    assert "الا یا ایها الساقی" in formatted
    assert "وزن: فاعلاتن" in formatted
