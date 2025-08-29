"""
Ежедневный workflow: генерирует текст, публикует его в Telegram и Farcaster,
проверяет баланс и решает, сколько «спать».
"""
from __future__ import annotations
import inspect
from typing import Any, Dict

from app.services.telegram import publish_to_telegram
from app.services.farcaster import publish_to_farcaster, get_cast_metrics
from app.services.finance import FinanceClient
from app.utils.sleep_utils import decide_sleep_hours
from app.agents.blogger_agent import BloggerAgent

# NEW: DAO для постов
from app.services.posts_dao import (
    save_post,
    update_farcaster_metrics,
    list_all_farcaster_casts, list_all_farcaster_casts,
)

async def _await_if_needed(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value

class DailyRoutine:
    def __init__(self) -> None:
        self.blog_agent = BloggerAgent()
        self.finance = FinanceClient()

    async def run(self) -> Dict[str, Any]:
        # 1) генерируем текст
        post_text: str = await _await_if_needed(self.blog_agent.write_post(None))

        # 2) Telegram
        tg_resp = await publish_to_telegram(post_text)
        message_id = (tg_resp or {}).get("result", {}).get("message_id")
        chat_id    = (tg_resp or {}).get("result", {}).get("chat", {}).get("id")

        # 2b) Farcaster → опубликовать
        fc_resp = await publish_to_farcaster(post_text)
        cast_hash = (fc_resp or {}).get("cast", {}).get("hash")

        # 2c) Сохранить каст в БД (если был опубликован)
        if cast_hash:
            save_post("farcaster", cast_hash, post_text)

        # 2d) Обновить метрики у последних N кастов
        for h in list_all_farcaster_casts():
            try:
                m = await get_cast_metrics(h)
                update_farcaster_metrics(h, likes=m["likes"], recasts=m["recasts"], replies=m["replies"])
            except Exception as e:
                print(f"[metrics] failed for {h}: {e}")

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
            "farcaster_cast_hash": cast_hash,
            "balance": balance,
            "sleep_hours": sleep_hours,
        }
