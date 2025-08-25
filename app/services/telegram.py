import os
import httpx
from typing import Optional
from dotenv import load_dotenv

load_dotenv()  # на случай запуска из другого entrypoint

async def publish_to_telegram(
    text: str,
    chat_id: Optional[str] = None,
    parse_mode: str = "HTML",
):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN не задан")

    cid = chat_id or os.getenv("TELEGRAM_CHAT_ID", "@ai_bloggger")
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": cid, "text": text, "parse_mode": parse_mode}

    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(url, json=payload)
        r.raise_for_status()
        return r.json()
