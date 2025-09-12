# app/services/telegram.py
from __future__ import annotations

import os
from typing import Dict, Iterable, Optional

import httpx

from app.services.posts_dao import (
    save_post,
    list_all_telegram_messages,
    update_telegram_metrics,
)
from dotenv import load_dotenv
load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")  # числовой -100..., допускается @username для отправки
BASE = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}" if TELEGRAM_BOT_TOKEN else None

# простой in-memory offset для getUpdates
_TG_UPDATE_OFFSET: int = 0


def _resolved_chat_id() -> str:
    # публикация допускает и @username; для реакций лучше числовой id
    return TELEGRAM_CHAT_ID or ""


def get_tg_update_offset() -> int:
    return _TG_UPDATE_OFFSET


def set_tg_update_offset(v: int) -> None:
    global _TG_UPDATE_OFFSET
    _TG_UPDATE_OFFSET = int(v)


async def publish_to_telegram(text: str) -> Dict:
    """
    Публикуем пост в канал.
    Возвращает сырой ответ Telegram API (dict).
    """
    if not BASE or not _resolved_chat_id():
        return {"ok": False, "result": {}}

    payload = {"chat_id": _resolved_chat_id(), "text": text, "disable_web_page_preview": True}
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(f"{BASE}/sendMessage", json=payload)
        data = r.json()
        # если получилось — сохраним пост в БД
        msg = (data or {}).get("result") or {}
        mid = msg.get("message_id")
        if mid is not None:
            save_post("telegram", str(mid), text)
        return data


async def init_telegram_updates() -> None:
    """
    Разовая инициализация: снимем вебхук и «разбудим» getUpdates,
    чтобы Telegram начал присылать новые типы апдейтов.
    """
    if not BASE:
        return
    async with httpx.AsyncClient(timeout=15) as client:
        try:
            await client.get(f"{BASE}/deleteWebhook")
        except Exception:
            pass
        # холостой вызов с нужными типами
        await client.post(
            f"{BASE}/getUpdates",
            json={
                "allowed_updates": [
                    "message_reaction",
                    "message_reaction_count",
                    "channel_post",
                    "edited_channel_post",
                ],
                "timeout": 0,
            },
        )


async def debug_fetch_updates_raw() -> Dict:
    """
    Для /debug/telegram/raw — возвращаем сырой ответ телеги + какой offset используем.
    """
    if not BASE:
        return {"error": "NO_TELEGRAM_BOT_TOKEN"}

    offset = get_tg_update_offset()
    payload = {
        **({"offset": offset + 1} if offset else {}),
        "allowed_updates": [
            "message_reaction",
            "message_reaction_count",
            "channel_post",
            "edited_channel_post",
        ],
        "timeout": 0,
    }
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(f"{BASE}/getUpdates", json=payload)
        try:
            data = r.json()
        except Exception:
            data = {"ok": False, "result": []}

    # НЕ двигаем offset (это «peek» без фиксации)
    return {"offset": offset, "request": payload, "response": data}


async def poll_telegram_updates_once(
    known_message_ids: Optional[Iterable[int | str]] = None,
) -> Dict[str, int]:
    """
    Один проход getUpdates.
    Суммируем изменения по реакциям для постов, которые находятся у нас в БД.
    """
    if not BASE:
        return {"likes": 0, "forwards": 0, "replies": 0, "views": 0}

    if known_message_ids is None:
        known_message_ids = list_all_telegram_messages()
    known_set = {str(mid) for mid in known_message_ids}

    offset = get_tg_update_offset()
    payload = {
        **({"offset": offset + 1} if offset else {}),
        "allowed_updates": [
            "message_reaction",
            "message_reaction_count",
            "channel_post",
            "edited_channel_post",
        ],
        "timeout": 0,
    }

    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(f"{BASE}/getUpdates", json=payload)
        try:
            data = r.json()
        except Exception:
            return {"likes": 0, "forwards": 0, "replies": 0, "views": 0}

    updates = (data or {}).get("result") or []
    totals = {"likes": 0, "forwards": 0, "replies": 0, "views": 0}
    max_update_id = offset

    for upd in updates:
        uid = int(upd.get("update_id", 0))
        if uid > max_update_id:
            max_update_id = uid

        # интересует агрегированный блок по реакциям
        mrc = upd.get("message_reaction_count")
        if not mrc:
            continue

        msg = mrc.get("message") or {}
        chat = msg.get("chat") or {}
        # фильтр по каналу
        wanted = str(_resolved_chat_id())
        if wanted.startswith("-100"):
            if str(chat.get("id")) != wanted:
                continue
        else:
            # если в .env указан @username, просто не фильтруем по id
            pass

        mid = msg.get("message_id")
        if mid is None or str(mid) not in known_set:
            continue

        # суммируем все эмодзи-реакции
        total_reactions = 0
        for item in (mrc.get("reactions") or []):
            total_reactions += int(item.get("total_count") or 0)

        update_telegram_metrics(mid, likes=total_reactions)
        totals["likes"] += total_reactions

    if max_update_id and max_update_id != offset:
        set_tg_update_offset(max_update_id)

    return totals
