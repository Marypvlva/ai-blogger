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

# --- ENV ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = str(os.getenv("TELEGRAM_CHAT_ID") or "").strip()
BASE = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}" if TELEGRAM_BOT_TOKEN else None

# in-memory offset
_TG_UPDATE_OFFSET = 0
def get_tg_update_offset() -> int: return _TG_UPDATE_OFFSET
def set_tg_update_offset(v: int) -> None:
    global _TG_UPDATE_OFFSET
    _TG_UPDATE_OFFSET = int(v)


# ---------- helpers ----------
def _sum_reactions(items) -> int:
    total = 0
    for it in (items or []):
        
        total += int(it.get("total_count") or it.get("count") or 0)
    return total

def _get_old_likes(mid: int) -> int:
    from app.services.posts_dao import _conn
    with _conn() as con:
        row = con.execute("SELECT likes FROM telegram_posts WHERE message_id=?", (mid,)).fetchone()
    return int(row[0]) if row and row[0] is not None else 0


# ---------- publish ----------
async def publish_to_telegram(text: str) -> Dict:
    if not BASE or not TELEGRAM_CHAT_ID:
        return {}
    payload = {"chat_id": int(TELEGRAM_CHAT_ID), "text": text, "disable_web_page_preview": True}
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(f"{BASE}/sendMessage", json=payload)
        try:
            data = r.json()
        except Exception:
            data = {}
    msg = (data or {}).get("result") or {}
    mid = msg.get("message_id")
    if mid is not None:
        upsert_telegram_message(int(mid), TELEGRAM_CHAT_ID)
    return data


# ---------- debug raw ----------
async def debug_fetch_updates_raw() -> Dict:
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


# ---------- poll once (fixed) ----------
async def poll_telegram_updates_once(
    known_message_ids: Iterable[int | str] | None = None,
) -> Dict[str, int]:
    """
    Один опрос getUpdates. Поддерживает обе формы payload:
    1) mrc = { chat, message_id, reactions, ... }    <-- как у тебя
    2) mrc = { message: {chat, message_id, ...}, reactions, ... }
    Обновляет БД текущими суммами реакций (total_count), а в ответ отдаёт прирост.
    """
    if not BASE or not TELEGRAM_CHAT_ID:
        return {
            "likes": 0, "forwards": 0, "replies": 0, "views": 0,
            "updates_seen": 0, "offset": get_tg_update_offset()
        }

    if known_message_ids is None:
        known_message_ids = list_all_telegram_messages()
    known_set = {str(m) for m in known_message_ids}

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

    
    summed_now: Dict[int, int] = {}

    for upd in updates:
        uid = int(upd.get("update_id", 0))
        if uid > max_update_id:
            max_update_id = uid

        mrc = upd.get("message_reaction_count")
        if not mrc:
            continue

        
        if "message" in mrc and isinstance(mrc["message"], dict):
            msg = mrc["message"]
            chat = msg.get("chat") or {}
            mid = msg.get("message_id")
        else:
            chat = mrc.get("chat") or {}
            mid = mrc.get("message_id")

        
        if str(chat.get("id")) != str(TELEGRAM_CHAT_ID):
            continue
        if mid is None:
            continue
        mid = int(mid)

        if str(mid) not in known_set:
            upsert_telegram_message(mid, TELEGRAM_CHAT_ID)
            known_set.add(str(mid))

        this_sum = _sum_reactions(mrc.get("reactions"))
        
        prev = summed_now.get(mid, 0)
        if this_sum > prev:
            summed_now[mid] = this_sum

    
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
