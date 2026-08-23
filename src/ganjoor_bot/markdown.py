from __future__ import annotations

import sqlite3
from pathlib import Path


def _safe_name(value: str) -> str:
    return value.replace("/", "／").replace("\\", "＼").strip() or "untitled"


def export_markdown(conn: sqlite3.Connection, out_dir: Path) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    poems = conn.execute(
        """
        SELECT p.id, p.title, p.metre, p.rhyme, p.source_path, po.nickname AS poet
        FROM poems p JOIN poets po ON po.id = p.poet_id
        ORDER BY po.nickname, p.id
        """
    ).fetchall()

    count = 0
    for poem in poems:
        poet_dir = out_dir / _safe_name(poem["poet"])
        poet_dir.mkdir(parents=True, exist_ok=True)
        path = poet_dir / f'{poem["id"]}.md'
        verses = conn.execute(
            "SELECT verse_order, text FROM verses WHERE poem_id = ? ORDER BY verse_order",
            (poem["id"],),
        ).fetchall()

        header = [
            "---",
            f'id: {poem["id"]}',
            f'poet: "{poem["poet"]}"',
            f'title: "{(poem["title"] or "").replace(chr(34), chr(39))}"',
            f'source_path: "{poem["source_path"]}"',
        ]
        if poem["metre"]:
            header.append(f'metre: "{str(poem["metre"]).replace(chr(34), chr(39))}"')
        if poem["rhyme"]:
            header.append(f'rhyme: "{str(poem["rhyme"]).replace(chr(34), chr(39))}"')
        header += ["---", "", f'# {poem["title"] or "شعر"}', ""]

        body = [row["text"] for row in verses]
        path.write_text("\n".join(header + body) + "\n", encoding="utf-8")
        count += 1
    return count
