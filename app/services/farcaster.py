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
