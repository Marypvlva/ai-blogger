"""
Ежедневный workflow: генерирует текст, публикует его в Telegram и Farcaster,
обновляет метрики по всем постам и обучает RL-агента (BloggerReinforcment).
"""

from __future__ import annotations

import inspect
import os
from typing import Any, Dict, Optional, Callable, List

from app.services.telegram import publish_to_telegram
from app.services.farcaster import (
    publish_to_farcaster,
    get_cast_metrics,
    get_follower_count,
)
from app.services.finance import FinanceClient
from app.utils.sleep_utils import decide_sleep_hours
from app.agents.blogger_agent import BloggerAgent

# DB (посты и метрики)
from app.services.posts_dao import (
    save_post,
    update_farcaster_metrics,
    list_all_farcaster_casts,
    get_farcaster_totals,
)

# RL (твой файл)
from app.agents.BloggerReinforcment import BloggerReinforcment


async def _await_if_needed(value: Any) -> Any:
    """Await *value* если он awaitable, иначе вернуть как есть."""
    if inspect.isawaitable(value):
        return await value
    return value


class DailyRoutine:
    # 0=post, 1=sponsored_post, 2=like_comments, 3=make_comments, 4=sleep
    ACTION_POST = 0
    ACTION_SLEEP = 4

    def __init__(self) -> None:
        self.blog_agent = BloggerAgent()
        self.finance = FinanceClient()

        # Инициализируем RL-агента
        self.rl = BloggerReinforcment()

        # Если внутри класса есть load()/save() — поднимем состояние
        if hasattr(self.rl, "load"):
            try:
                loaded = bool(self.rl.load())  # может вернуть bool
                print("[reinforce] state loaded:", loaded)
            except Exception as e:  # noqa: BLE001
                print("[reinforce] load failed:", e)

        # Адаптеры имён методов (если другое API внутри класса)
        self._rl_act: Callable[[List[float]], int] = self._bind_act()
        self._rl_update: Optional[Callable[..., Any]] = self._bind_update()
        self._rl_compute_reward: Optional[
            Callable[[List[float], List[float]], float]
        ] = self._bind_compute_reward()

    # ---------- RL adapters ----------
    def _bind_act(self) -> Callable[[List[float]], int]:
        if hasattr(self.rl, "act"):
            return getattr(self.rl, "act")
        if hasattr(self.rl, "select_action"):
            return getattr(self.rl, "select_action")
        if hasattr(self.rl, "choose"):
            return getattr(self.rl, "choose")
        # дефолт: всегда постим
        return lambda state: self.ACTION_POST

    def _bind_update(self) -> Optional[Callable[..., Any]]:
        for name in ("update", "learn", "step"):
            if hasattr(self.rl, name):
                return getattr(self.rl, name)
        return None

    def _bind_compute_reward(
        self,
    ) -> Optional[Callable[[List[float], List[float]], float]]:
        if hasattr(self.rl, "compute_reward"):
            return getattr(self.rl, "compute_reward")
        return None

    # ---------- построение состояния ----------
    async def _state_now(self) -> List[float]:
        """
        Состояние: [money, views, likes, comments, subs]
        - money: баланс из FinanceClient
        - views/likes/replies: агрегаты из БД
        - subs: follower_count из Neynar (по username в .env)
        """
        balance = await _await_if_needed(self.finance.get_balance())
        agg = get_farcaster_totals()  # {"likes","recasts","replies","views"}

        username = os.getenv("FARCASTER_USERNAME", "")
        subs = 0.0
        if username:
            try:
                subs = float(await get_follower_count(username))
            except Exception as e:  # noqa: BLE001
                print(f"[followers] failed: {e}")
                subs = 0.0

        return [
            float(balance),
            float(agg.get("views", 0)),
            float(agg.get("likes", 0)),
            float(agg.get("replies", 0)),
            float(subs),
        ]

    async def run(self) -> Dict[str, Any]:
        # 0) предыдущее состояние
        prev_state = await self._state_now()

        # 1) выбрать действие через RL
        try:
            action = int(self._rl_act(prev_state))
        except Exception as e:  # noqa: BLE001
            print(f"[rl] act failed: {e}")
            action = self.ACTION_POST

        # 2) исполняем действие
        post_text: str = await _await_if_needed(self.blog_agent.write_post(None))
        tg_resp: Dict[str, Any] = {}
        cast_hash: Optional[str] = None

        if action != self.ACTION_SLEEP:
            tg_resp = await publish_to_telegram(post_text) or {}
            fc_resp = await publish_to_farcaster(post_text) or {}
            cast_hash = (fc_resp.get("cast") or {}).get("hash")
            if cast_hash:
                save_post("farcaster", cast_hash, post_text)
        # else: sleep — ничего не публикуем

        message_id = (tg_resp.get("result") or {}).get("message_id")
        chat_id = (tg_resp.get("result") or {}).get("chat", {}).get("id")

        # 3) обновляем метрики у всех постов (likes/recasts/replies)
        for h in list_all_farcaster_casts():
            try:
                m = await get_cast_metrics(h)
                update_farcaster_metrics(
                    h, likes=m["likes"], recasts=m["recasts"], replies=m["replies"]
                )
            except Exception as e:  # noqa: BLE001
                print(f"[metrics] failed for {h}: {e}")

        # 4) следующее состояние
        next_state = await self._state_now()

        # 5) обучение RL-агента
        reward = self._default_reward(prev_state, next_state)
        if self._rl_compute_reward:
            try:
                reward = float(self._rl_compute_reward(prev_state, next_state))
            except Exception as e:  # noqa: BLE001
                print(f"[rl] compute_reward failed: {e}")

        if self._rl_update:
            try:
                # частые сигнатуры:
                #   update(prev, action, next, baseline=0.0)
                #   или update(prev, action, reward, next)
                try:
                    self._rl_update(prev_state, action, next_state, baseline=0.0)
                except TypeError:
                    # если требуется reward в позиции 3
                    self._rl_update(prev_state, action, reward, next_state)
            except Exception as e:  # noqa: BLE001
                print(f"[rl] update failed: {e}")

        # если есть save() — сохраним состояние модели на диск
        if hasattr(self.rl, "save"):
            try:
                self.rl.save()
            except Exception as e:  # noqa: BLE001
                print("[reinforce] save failed:", e)

        # 6) финансы и сон
        balance = await _await_if_needed(self.finance.get_balance())
        if balance > 20:
            await _await_if_needed(self.finance.pay_expenses(10))
        sleep_hours = decide_sleep_hours(balance)

        return {
            "post_text": post_text,
            "action": action,
            "reward": reward,
            "telegram_message_id": message_id,
            "telegram_chat_id": chat_id,
            "farcaster_cast_hash": cast_hash,
            "prev_state": prev_state,
            "next_state": next_state,
            "balance": balance,
            "sleep_hours": sleep_hours,
        }

    @staticmethod
    def _default_reward(prev_state: List[float], next_state: List[float]) -> float:
        """
        Простая награда: прирост вовлечения.
        prev/next = [money, views, likes, comments, subs]
        """
        d_views = max(0.0, float(next_state[1] - prev_state[1]))
        d_likes = max(0.0, float(next_state[2] - prev_state[2]))
        d_repl  = max(0.0, float(next_state[3] - prev_state[3]))
        d_subs  = max(0.0, float(next_state[4] - prev_state[4]))
        return d_likes + 2.0 * d_views + 3.0 * d_repl + 4.0 * d_subs
