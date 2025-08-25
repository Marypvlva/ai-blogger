"""
Ежедневный workflow: генерирует текст, публикует его в Telegram,
проверяет баланс и решает, сколько «спать».
"""

from __future__ import annotations

import inspect
from typing import Any

from app.services.telegram import publish_to_telegram
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
        self.blog_agent = BloggerAgent()
        self.finance = FinanceClient()

    async def run(self) -> dict[str, Any]:
        # 1) генерируем текст
        post_text: str = await _await_if_needed(self.blog_agent.write_post(None))

        # 2) публикуем в Telegram
        tg_resp = await publish_to_telegram(post_text)
        # ожидаемый ответ Telegram API:
        # {"ok": true, "result": {"message_id": ..., "chat": {"id": ...}, ...}}
        message_id = tg_resp.get("result", {}).get("message_id")
        chat_id = tg_resp.get("result", {}).get("chat", {}).get("id")

        # 3) финансы
        balance = await _await_if_needed(self.finance.get_balance())
        if balance > 20:
            await _await_if_needed(self.finance.pay_expenses(10))

        # 4) сон
        sleep_hours = decide_sleep_hours(balance)

        return {
            "post_text": post_text,
            "telegram_message_id": message_id,
            "telegram_chat_id": chat_id,
            "balance": balance,
            "sleep_hours": sleep_hours,
        }
