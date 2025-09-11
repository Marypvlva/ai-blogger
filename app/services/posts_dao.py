# app/services/posts_dao.py
from __future__ import annotations

from typing import List, Dict
import sqlite3
from contextlib import contextmanager
from pathlib import Path

# Пишем в тот же файл БД, что и сессии агентов: app/db/data/agents.sqlite
DB_PATH = (
    Path(__file__).resolve().parents[1] / "db" / "data" / "agents.sqlite"
)
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

TABLE = "posts"


@contextmanager
def _conn():
    con = sqlite3.connect(DB_PATH)
    try:
        yield con
        con.commit()
    finally:
        con.close()


def _init() -> None:
    with _conn() as con:
        con.execute(
            f"""
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
            """
        )
        con.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{TABLE}_platform ON {TABLE}(platform);"
        )
        con.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{TABLE}_ext ON {TABLE}(external_id);"
        )


def save_post(platform: str, external_id: str, text: str) -> None:
    _init()
    with _conn() as con:
        con.execute(
            f"INSERT OR IGNORE INTO {TABLE} (platform, external_id, text) VALUES (?, ?, ?)",
            (platform, external_id, text),
        )


def update_farcaster_metrics(
    cast_hash: str, *, likes: int, recasts: int, replies: int
) -> None:
    _init()
    with _conn() as con:
        con.execute(
            f"""
            UPDATE {TABLE}
               SET likes=?, recasts=?, replies=?, updated_at=CURRENT_TIMESTAMP
             WHERE platform='farcaster' AND external_id=?
            """,
            (int(likes), int(recasts), int(replies), cast_hash),
        )


def list_all_farcaster_casts() -> List[str]:
    _init()
    with _conn() as con:
        cur = con.execute(
            f"""
            SELECT external_id
              FROM {TABLE}
             WHERE platform='farcaster'
             ORDER BY created_at DESC
            """
        )
        return [row[0] for row in cur.fetchall()]


def get_farcaster_totals() -> Dict[str, int]:
    """
    Агрегаты по всем кастам: likes/recasts/replies + proxy views.
    subs (подписчики) берём отдельно в workflow через Neynar (get_follower_count).
    """
    _init()
    with _conn() as con:
        cur = con.execute(
            f"""
            SELECT
              COALESCE(SUM(likes),0),
              COALESCE(SUM(recasts),0),
              COALESCE(SUM(replies),0)
            FROM {TABLE}
            WHERE platform='farcaster';
            """
        )
        likes, recasts, replies = cur.fetchone()
    likes = int(likes or 0)
    recasts = int(recasts or 0)
    replies = int(replies or 0)
    views = likes + 2 * recasts + 3 * replies
    return {"likes": likes, "recasts": recasts, "replies": replies, "views": views}
