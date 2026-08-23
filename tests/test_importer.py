import json
from pathlib import Path

from ganjoor_bot.db import connect, initialize
from ganjoor_bot.importer import import_corpus


def _write(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")


def test_import_current_ganjoor_shape(tmp_path: Path):
    root = tmp_path / "upstream"
    _write(root / "manifest.json", {"SchemaVersion": 1, "GeneratedAtUtc": "2026-08-16T00:00:00Z"})
    _write(root / "poets/hafez/poet.json", {"Id": 2, "Name": "حافظ شیرازی", "Nickname": "حافظ"})
    _write(root / "poets/hafez/_cat.json", {"Id": 9, "PoetId": 2, "Title": "حافظ"})
    _write(root / "poets/hafez/ghazal/_cat.json", {"Id": 24, "PoetId": 2, "ParentId": 9, "Title": "غزلیات"})
    _write(
        root / "poets/hafez/ghazal/sh1.json",
        {
            "Id": 2130,
            "CatId": 24,
            "Title": "غزل شمارهٔ ۱",
            "RhymeLetters": "لها",
            "Metre": {"Id": 2, "Rhythm": "مفاعیلن مفاعیلن"},
            "Verses": [
                {"VOrder": 1, "Position": "Right", "Text": "الا یا ایها الساقی", "CoupletIndex": 0, "SectionIndex1": 0},
                {"VOrder": 2, "Position": "Left", "Text": "که عشق آسان نمود اول", "CoupletIndex": 0, "SectionIndex1": 0},
            ],
        },
    )

    conn = connect(tmp_path / "poetry.sqlite")
    initialize(conn)
    stats = import_corpus(root, conn)

    assert stats == {"poets": 1, "categories": 2, "poems": 1, "verses": 2}
    poem = conn.execute("SELECT * FROM poems WHERE id = 2130").fetchone()
    assert poem["poet_id"] == 2
    assert poem["category_id"] == 24
    assert poem["metre_id"] == 2
    assert poem["rhyme"] == "لها"
    verse = conn.execute("SELECT * FROM verses WHERE poem_id = 2130 AND verse_order = 1").fetchone()
    assert verse["position"] == "Right"
    assert verse["couplet_index"] == 0
