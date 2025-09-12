from __future__ import annotations
from typing import List, Dict, Any, Iterable, Optional
import sqlite3
from pathlib import Path

# Один файл БД для всего проекта
DB_PATH = Path(__file__).resolve().parents[1] / "db" / "data" / "agents.sqlite"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

# Таблицы:
# - posts         (у тебя уже есть; здесь Farcaster-посты)
# - telegram_posts(новая — для канал-постов и их метрик)


def _conn() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def _init() -> None:
    with _conn() as con:
        # Общая таблица постов (как была)
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS posts (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                platform    TEXT NOT NULL,          -- 'farcaster' | 'telegram'
                external_id TEXT UNIQUE,            -- cast_hash | message_id (str)
                text        TEXT,
                likes       INTEGER DEFAULT 0,
                recasts     INTEGER DEFAULT 0,
                replies     INTEGER DEFAULT 0,
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        con.execute("CREATE INDEX IF NOT EXISTS idx_posts_platform ON posts(platform)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_posts_ext ON posts(external_id)")

        # Telegram-таблица (для подробных метрик и backfill)
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS telegram_posts (
                message_id  INTEGER PRIMARY KEY,
                chat_id     TEXT,
                likes       INTEGER DEFAULT 0,      -- суммарное число реакций
                forwards    INTEGER DEFAULT 0,
                replies     INTEGER DEFAULT 0,
                views       INTEGER DEFAULT 0,
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
        )


# ----------------------- Farcaster (как было) -----------------------
def save_post(platform: str, external_id: str, text: str) -> None:
    _init()
    with _conn() as con:
        con.execute(
            "INSERT OR IGNORE INTO posts (platform, external_id, text) VALUES (?, ?, ?)",
            (platform, external_id, text),
        )


def update_farcaster_metrics(cast_hash: str, *, likes: int, recasts: int, replies: int) -> None:
    _init()
    with _conn() as con:
        con.execute(
            """
            UPDATE posts
               SET likes=?, recasts=?, replies=?, updated_at=CURRENT_TIMESTAMP
             WHERE platform='farcaster' AND external_id=?
            """,
            (int(likes), int(recasts), int(replies), cast_hash),
        )


def list_all_farcaster_casts() -> List[str]:
    _init()
    with _conn() as con:
        cur = con.execute(
            "SELECT external_id FROM posts WHERE platform='farcaster' ORDER BY created_at DESC"
        )
        return [row[0] for row in cur.fetchall()]


def get_farcaster_totals() -> Dict[str, int]:
    _init()
    with _conn() as con:
        cur = con.execute(
            """
            SELECT COALESCE(SUM(likes),0), COALESCE(SUM(recasts),0), COALESCE(SUM(replies),0)
              FROM posts
             WHERE platform='farcaster'
            """
        )
        likes, recasts, replies = cur.fetchone()
    likes = int(likes or 0)
    recasts = int(recasts or 0)
    replies = int(replies or 0)
    views = likes + 2 * recasts + 3 * replies
    return {"likes": likes, "recasts": recasts, "replies": replies, "views": views}


# ----------------------- Telegram -----------------------
def list_all_telegram_messages() -> List[int]:
    """ID всех сообщений канала, которые мы уже знаем/храним."""
    _init()
    mids: List[int] = []
    with _conn() as con:
        for r in con.execute("SELECT message_id FROM telegram_posts ORDER BY message_id DESC"):
            try:
                mids.append(int(r[0]))
            except Exception:
                pass
    return mids


def upsert_telegram_message(
    message_id: int,
    chat_id: str | int,
    *,
    likes: int = 0,
    forwards: int = 0,
    replies: int = 0,
    views: int = 0,
) -> None:
    """Вставить или обновить строку telegram_posts по message_id."""
    _init()
    with _conn() as con:
        con.execute(
            """
            INSERT INTO telegram_posts (message_id, chat_id, likes, forwards, replies, views)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(message_id) DO UPDATE SET
                chat_id=excluded.chat_id,
                likes=excluded.likes,
                forwards=excluded.forwards,
                replies=excluded.replies,
                views=excluded.views,
                updated_at=CURRENT_TIMESTAMP
            """,
            (int(message_id), str(chat_id), int(likes), int(forwards), int(replies), int(views)),
        )


def update_telegram_metrics(
    message_id: int | str,
    *,
    likes: int | None = None,
    forwards: int | None = None,
    replies: int | None = None,
    views: int | None = None,
) -> None:
    """Обновить отдельные поля (если переданы)."""
    _init()
    sets = []
    vals: List[Any] = []
    for col, v in (("likes", likes), ("forwards", forwards), ("replies", replies), ("views", views)):
        if v is not None:
            sets.append(f"{col}=?")
            vals.append(int(v))
    if not sets:
        return
    vals.append(int(message_id))
    sql = f"UPDATE telegram_posts SET {', '.join(sets)}, updated_at=CURRENT_TIMESTAMP WHERE message_id=?"
    with _conn() as con:
        con.execute(sql, vals)
