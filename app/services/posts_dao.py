# app/services/posts_dao.py
from __future__ import annotations
from typing import List
import sqlite3
from contextlib import contextmanager
from pathlib import Path
import os

# Путь к тому же файлу, что использует твой SQLiteSession:
# session.py делает: BASE = Path(__file__).parent / "data"; db_path = BASE / "agents.sqlite"
DB_PATH = (Path(__file__).resolve().parents[1]  # -> .../app
           / "db" / "data" / "agents.sqlite")

# гарантируем папку
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

@contextmanager
def _conn():
    con = sqlite3.connect(DB_PATH)
    try:
        yield con
        con.commit()
    finally:
        con.close()

TABLE = "posts"

def _init() -> None:
    """Создать таблицу один раз."""
    with _conn() as con:
        con.execute(f"""
            CREATE TABLE IF NOT EXISTS {TABLE} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                platform    TEXT NOT NULL,          -- 'farcaster' | 'telegram'
                external_id TEXT UNIQUE,            -- cast_hash | message_id
                text        TEXT,
                likes       INTEGER DEFAULT 0,
                recasts     INTEGER DEFAULT 0,
                replies     INTEGER DEFAULT 0,
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        con.execute(f"CREATE INDEX IF NOT EXISTS idx_{TABLE}_platform ON {TABLE}(platform);")
        con.execute(f"CREATE INDEX IF NOT EXISTS idx_{TABLE}_ext ON {TABLE}(external_id);")

def save_post(platform: str, external_id: str, text: str) -> None:
    _init()
    with _conn() as con:
        con.execute(
            f"INSERT OR IGNORE INTO {TABLE} (platform, external_id, text) VALUES (?, ?, ?)",
            (platform, external_id, text),
        )

def update_farcaster_metrics(cast_hash: str, *, likes: int, recasts: int, replies: int) -> None:
    _init()
    with _conn() as con:
        con.execute(
            f"""UPDATE {TABLE}
                   SET likes=?, recasts=?, replies=?, updated_at=CURRENT_TIMESTAMP
                 WHERE platform='farcaster' AND external_id=?""",
            (int(likes), int(recasts), int(replies), cast_hash),
        )



# app/services/posts_dao.py
def list_all_farcaster_casts() -> list[str]:
    _init()
    with _conn() as con:
        cur = con.execute(
            "SELECT external_id FROM posts WHERE platform='farcaster' ORDER BY created_at DESC;"
        )
        return [row[0] for row in cur.fetchall()]
