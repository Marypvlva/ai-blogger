# app/services/bluesky.py

"""Мини‑клиент для публикации постов в Bluesky (AT‑Protocol)."""

import os
import sys
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# client
# ---------------------------------------------------------------------------

class BlueskyClient:
    """Логин + createRecord в одном методе."""

    def __init__(self) -> None:
        load_dotenv()
        self.service  = os.getenv("BLSKY_HOST", "https://bsky.social").rstrip("/")
        self.email    = os.getenv("BLSKY_EMAIL")
        self.password = os.getenv("BLSKY_PASS")
        if not (self.email and self.password):
            raise RuntimeError("В .env укажите BLSKY_EMAIL и BLSKY_PASS (и, опц., BLSKY_HOST)")

    # ────────────────────────────────────────────────────────────────────
    # public API
    # ────────────────────────────────────────────────────────────────────

    def post_text(self, text: str) -> dict:
        """Публикует текст ≤300 симв. Возвращает dict с ``uri`` и ``cid``."""
        jwt, did = self._login()

        now_iso = (
            datetime.now(timezone.utc)
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z")
        )
        record = {
            "$type":     "app.bsky.feed.post",
            "text":      text[:300],  # Bluesky ограничивает 300 символами
            "createdAt": now_iso,
        }

        body = {
            "repo":       did,
            "collection": "app.bsky.feed.post",
            "record":     record,
        }
        headers = {
            "Authorization": f"Bearer {jwt}",
            "Content-Type":  "application/json",
        }

        res = requests.post(
            f"{self.service}/xrpc/com.atproto.repo.createRecord",
            json=body,
            headers=headers,
            timeout=15,
        )
        if res.status_code >= 400:
            # Пытаемся извлечь JSON‑ошибку от Bluesky, чтобы увидеть причину
            try:
                err_detail = res.json()
            except ValueError:
                err_detail = res.text
            raise RuntimeError(f"Bluesky 400: {err_detail}")
        return res.json()

    # ────────────────────────────────────────────────────────────────────
    # internals
    # ────────────────────────────────────────────────────────────────────

    def _login(self) -> tuple[str, str]:
        """Возвращает (JWT, DID)."""
        res = requests.post(
            f"{self.service}/xrpc/com.atproto.server.createSession",
            json={"identifier": self.email, "password": self.password},
            timeout=15,
        )
        res.raise_for_status()
        data = res.json()
        return data["accessJwt"], data["did"]
