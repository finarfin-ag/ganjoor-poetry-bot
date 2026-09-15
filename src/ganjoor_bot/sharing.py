from __future__ import annotations

import sqlite3
from urllib.parse import quote


GANJOOR_BASE_URL = "https://ganjoor.net"


def ganjoor_url_from_source_path(source_path: str | None) -> str | None:
    if not source_path:
        return None
    path = str(source_path).strip().replace("\\", "/")
    if path.startswith("poets/"):
        path = path[len("poets/") :]
    if path.endswith(".json"):
        path = path[:-5]
    if not path:
        return None
    return f"{GANJOOR_BASE_URL}/{path.lstrip('/')}"


def poem_share_info(conn: sqlite3.Connection, poem_id: int) -> dict[str, str] | None:
    row = conn.execute(
        """
        SELECT p.id, p.title, p.source_path, po.nickname AS poet
        FROM poems p
        JOIN poets po ON po.id = p.poet_id
        WHERE p.id = ?
        """,
        (int(poem_id),),
    ).fetchone()
    if row is None:
        return None

    url = ganjoor_url_from_source_path(row["source_path"])
    if not url:
        return None
    poet = str(row["poet"] or "").strip()
    title = str(row["title"] or "").strip()
    label = " — ".join(part for part in (poet, title) if part)
    return {"url": url, "label": label or "شعر فارسی"}


def telegram_share_url(url: str, text: str) -> str:
    return f"https://t.me/share/url?url={quote(url, safe='')}&text={quote(text, safe='')}"
