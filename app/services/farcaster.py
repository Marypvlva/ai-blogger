# app/services/farcaster.py
from __future__ import annotations

import os
from typing import Dict
import httpx

# ENV:
# FARCASTER_API_KEY=...         # Neynar API key
# FARCASTER_SIGNER_UUID=...     # signer uuid (approved)


API_KEY = os.getenv("NEYNAR_API_KEY")
SIGNER_UUID = os.getenv("FARCASTER_SIGNER")

BASE_URL = "https://api.neynar.com/v2/farcaster"


async def publish_to_farcaster(text: str) -> Dict:
    """
    Публикация каста через Neynar (нужны FARCASTER_API_KEY и FARCASTER_SIGNER_UUID).
    Возвращает JSON Neynar, ожидаем {"cast": {"hash": "...", ...}, ...}
    """
    if not API_KEY or not SIGNER_UUID:
        raise RuntimeError("FARCASTER_API_KEY or FARCASTER_SIGNER_UUID is missing")

    headers = {
        "x-api-key": API_KEY,
        "accept": "application/json",
        "content-type": "application/json",
    }
    payload = {"signer_uuid": SIGNER_UUID, "text": text}

    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(f"{BASE_URL}/cast", headers=headers, json=payload)
        r.raise_for_status()
        return r.json()


async def get_cast_metrics(cast_hash: str) -> Dict[str, int]:
    """
    Возвращает {"likes": int, "recasts": int, "replies": int} по hash каста.
    """
    if not API_KEY:
        return {"likes": 0, "recasts": 0, "replies": 0}

    headers = {"x-api-key": API_KEY, "accept": "application/json"}

    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(
            f"{BASE_URL}/cast",
            headers=headers,
            params={"identifier": cast_hash, "type": "hash"},
        )
        r.raise_for_status()
        data = r.json() or {}

    cast = (data.get("cast") or {})
    reactions = (cast.get("reactions") or {})
    likes = reactions.get("likes_count") or cast.get("likes_count") or 0
    recasts = reactions.get("recasts_count") or cast.get("recasts_count") or 0
    replies = cast.get("replies_count") or 0
    return {"likes": int(likes), "recasts": int(recasts), "replies": int(replies)}


async def get_follower_count(username: str) -> int:
    """
    Реальное количество подписчиков пользователя Farcaster (по username) через Neynar v2.
    Использует поиск: /v2/farcaster/user/search?q=<username> и берёт точное совпадение.
    """
    if not API_KEY:
        return 0

    headers = {"x-api-key": API_KEY, "accept": "application/json"}
    params = {"q": username}

    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(f"{BASE_URL}/user/search", headers=headers, params=params)
        r.raise_for_status()
        data = r.json() or {}

    users = (data.get("result") or {}).get("users") or []
    for u in users:
        if (u.get("username") or "").lower() == (username or "").lower():
            return int(u.get("follower_count") or 0)
    return 0
