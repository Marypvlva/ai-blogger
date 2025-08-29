# app/services/farcaster.py
import os
import httpx
from fastapi import HTTPException




NEYNAR_API_KEY = os.getenv("NEYNAR_API_KEY")
FARCASTER_SIGNER = os.getenv("FARCASTER_SIGNER")

async def publish_to_farcaster(text: str) -> dict:
    if not NEYNAR_API_KEY or not FARCASTER_SIGNER:
        raise HTTPException(status_code=500, detail="Missing Farcaster credentials")

    url = "https://api.neynar.com/v2/farcaster/cast"
    headers = {"api_key": NEYNAR_API_KEY, "Content-Type": "application/json"}
    payload = {"signer_uuid": FARCASTER_SIGNER, "text": text}

    async with httpx.AsyncClient() as client:
        r = await client.post(url, headers=headers, json=payload)
        if r.status_code != 200:
            raise HTTPException(status_code=r.status_code, detail=r.text)
        return r.json()

# + сверху уже есть publish_to_farcaster(...)


BASE = "https://api.neynar.com/v2/farcaster"

async def get_cast_metrics(cast_hash: str) -> dict:
    """
    Возвращает {"likes": int, "recasts": int, "replies": int} для данного cast_hash.
    """
    headers = {"x-api-key": NEYNAR_API_KEY, "accept": "application/json"}
    async with httpx.AsyncClient(timeout=30) as client:
        # основной маршрут
        r = await client.get(
            f"{BASE}/cast",
            params={"identifier": cast_hash, "type": "hash"},
            headers=headers
        )
        r.raise_for_status()
        data = r.json() or {}

    cast = (data.get("cast") or {})
    reactions = (cast.get("reactions") or {})
    likes   = reactions.get("likes_count")   or cast.get("likes_count")   or 0
    recasts = reactions.get("recasts_count") or cast.get("recasts_count") or 0
    replies = cast.get("replies_count") or 0
    return {"likes": int(likes), "recasts": int(recasts), "replies": int(replies)}

