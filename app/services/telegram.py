# app/services/telegram.py
from __future__ import annotations

import os
from typing import Dict, Iterable

import httpx

from app.services.posts_dao import (
    list_all_telegram_messages,
    upsert_telegram_message,
    update_telegram_metrics,
)

# --- Конфиг Telegram Bot API ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")  # обязательно
TELEGRAM_CHAT_ID = str(os.getenv("TELEGRAM_CHAT_ID") or "").strip()  # числовой ID канала
BASE = (
    f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
    if TELEGRAM_BOT_TOKEN
    else None
)

# Локальный volatile-оффсет (в памяти процесса)
_TG_UPDATE_OFFSET = 0


def get_tg_update_offset() -> int:
    return _TG_UPDATE_OFFSET


def set_tg_update_offset(v: int) -> None:
    global _TG_UPDATE_OFFSET
    _TG_UPDATE_OFFSET = int(v)


# ---------- Вспомогательные ----------

def _sum_reactions(items) -> int:
    """Складывает total_count/count по всем реакциям одного апдейта."""
    total = 0
    for it in (items or []):
        total += int(it.get("total_count") or it.get("count") or 0)
    return total


def _get_old_likes(mid: int) -> int:
    """Берёт текущее значение likes для message_id из БД (синхронно)."""
    from app.services.posts_dao import _conn  # локальный импорт
    with _conn() as con:
        row = con.execute(
            "SELECT likes FROM telegram_posts WHERE message_id=?",
            (mid,),
        ).fetchone()
    return int(row[0]) if row and row[0] is not None else 0


# ---------- Паблиш поста ----------

async def publish_to_telegram(text: str) -> Dict:
    """Публикует текст в канал. Возвращает raw-ответ Telegram."""
    if not BASE or not TELEGRAM_CHAT_ID:
        return {}
    payload = {
        "chat_id": int(TELEGRAM_CHAT_ID),
        "text": text,
        "disable_web_page_preview": True,
    }
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(f"{BASE}/sendMessage", json=payload)
        try:
            data = r.json()
        except Exception:
            data = {}

    # на лету апсертим сообщение в таблицу
    msg = (data or {}).get("result") or {}
    mid = msg.get("message_id")
    if mid is not None:
        upsert_telegram_message(int(mid), TELEGRAM_CHAT_ID)
    return data


# ---------- Отладка raw getUpdates ----------

async def debug_fetch_updates_raw() -> Dict:
    """Сырые данные getUpdates (для Swagger /debug/telegram/raw)."""
    if not BASE:
        return {"error": "NO_TELEGRAM_BOT_TOKEN"}

    payload = {
        "allowed_updates": [
            "message_reaction",
            "message_reaction_count",
            "channel_post",
            "edited_channel_post",
        ],
        "timeout": 0,
    }
    off = get_tg_update_offset()
    if off:
        payload["offset"] = off + 1

    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(f"{BASE}/getUpdates", json=payload)
        try:
            resp = r.json()
        except Exception:
            resp = {}

    return {"offset": off, "request": payload, "response": resp}


# ---------- Основной опрос апдейтов ----------

async def poll_telegram_updates_once(
    known_message_ids: Iterable[int | str] | None = None,
) -> Dict[str, int]:
    """
    ОДИН опрос getUpdates. Для каждого message_id агрегируем все реакции
    (message_reaction_count.reactions[*].total_count), обновляем БД telegram_posts
    текущими суммами, а в ответ возвращаем "run_added" — прирост vs того, что было
    в БД до опроса.
    """
    if not BASE or not TELEGRAM_CHAT_ID:
        return {
            "likes": 0,
            "forwards": 0,
            "replies": 0,
            "views": 0,
            "updates_seen": 0,
            "offset": get_tg_update_offset(),
        }

    # 1) если не передали список известных — достанем из БД
    if known_message_ids is None:
        known_message_ids = list_all_telegram_messages()
    known_set = {str(mid) for mid in known_message_ids}

    # 2) забираем апдейты
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
            data = {}

    updates = (data or {}).get("result") or []
    max_update_id = offset

    # 3) собираем по message_id «текущую» сумму реакций в этом пакете
    summed_now: Dict[int, int] = {}  # mid -> total reactions now
    for upd in updates:
        uid = int(upd.get("update_id", 0))
        if uid > max_update_id:
            max_update_id = uid

        mrc = upd.get("message_reaction_count")
        if not mrc:
            continue

        msg = mrc.get("message") or {}
        chat = msg.get("chat") or {}
        if str(chat.get("id")) != TELEGRAM_CHAT_ID:
            continue

        mid = msg.get("message_id")
        if mid is None:
            continue
        mid = int(mid)

        # если ещё не знаем это сообщение — создадим «скелет» в БД
        if str(mid) not in known_set:
            upsert_telegram_message(mid, TELEGRAM_CHAT_ID)
            known_set.add(str(mid))

        # сумма по реакциям в данном апдейте
        this_update_sum = _sum_reactions(mrc.get("reactions"))
        # берём максимум среди апдейтов одного и того же mid
        summed_now[mid] = max(summed_now.get(mid, 0), this_update_sum)

    # 4) считаем дельту и обновляем БД текущими суммами
    added_likes_total = 0
    for mid, now_sum in summed_now.items():
        old_sum = 0
        try:
            old_sum = _get_old_likes(mid)
        except Exception:
            old_sum = 0

        delta = max(0, now_sum - old_sum)
        added_likes_total += delta

        update_telegram_metrics(mid, likes=now_sum)

    # 5) фиксируем новый offset
    if max_update_id and max_update_id != offset:
        set_tg_update_offset(max_update_id)

    return {
        "likes": added_likes_total,
        "forwards": 0,
        "replies": 0,
        "views": 0,
        "updates_seen": len(updates),
        "offset": get_tg_update_offset(),
    }
