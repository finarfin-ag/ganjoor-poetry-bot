import sqlite3

import pytest

import ganjoor_bot.db as db


def test_connect_uses_query_only_when_database_is_not_writable(tmp_path, monkeypatch):
    path = tmp_path / "corpus.sqlite"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE sample(value TEXT)")
    conn.execute("INSERT INTO sample(value) VALUES ('ok')")
    conn.commit()
    conn.close()

    monkeypatch.setattr(db.os, "access", lambda *_args, **_kwargs: False)

    conn = db.connect(path)
    try:
        assert conn.execute("PRAGMA query_only").fetchone()[0] == 1
        assert conn.execute("SELECT value FROM sample").fetchone()[0] == "ok"
        with pytest.raises(sqlite3.OperationalError):
            conn.execute("INSERT INTO sample(value) VALUES ('nope')")
    finally:
        conn.close()


def test_connect_keeps_writable_database_in_wal_mode(tmp_path):
    path = tmp_path / "build.sqlite"
    conn = db.connect(path)
    try:
        assert conn.execute("PRAGMA query_only").fetchone()[0] == 0
        assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
    finally:
        conn.close()
