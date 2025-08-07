"""
Ежедневный workflow: генерирует текст, публикует его в Bluesky,
проверяет баланс и решает, сколько «спать».
"""

from __future__ import annotations

import inspect
from typing import Any

from app.services.bluesky import BlueskyClient
from app.services.finance import FinanceClient
from app.utils.sleep_utils import decide_sleep_hours
from app.agents.blogger_agent import BloggerAgent


async def _await_if_needed(value: Any) -> Any:
    """Await *value* если он awaitable, иначе вернуть как есть."""
    if inspect.isawaitable(value):
        return await value
    return value


class DailyRoutine:
    def __init__(self) -> None:
        self.blog_agent  = BloggerAgent()
        self.bsky_client = BlueskyClient()
        self.finance     = FinanceClient()

    async def run(self) -> dict[str, Any]:
        # 1) генерируем текст
        post_text: str = await _await_if_needed(self.blog_agent.write_post(None))

        # 2) публикуем в Bluesky
        res = await _await_if_needed(self.bsky_client.post_text(post_text))
        uri, cid = res["uri"], res["cid"]

        # 3) финансы
        balance = await _await_if_needed(self.finance.get_balance())
        if balance > 20:
            await _await_if_needed(self.finance.pay_expenses(10))

        # 4) сон
        sleep_hours = decide_sleep_hours(balance)

        return {
            "post_text":   post_text,
            "bsky_uri":    uri,
            "bsky_cid":    cid,
            "balance":     balance,
            "sleep_hours": sleep_hours,
        }
