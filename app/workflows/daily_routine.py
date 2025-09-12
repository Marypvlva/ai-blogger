"""
Ежедневный workflow: публикует в Telegram и Farcaster,
обновляет метрики, собирает раздельную статистику
и обучает RL-агента (BloggerReinforcment).
"""
from __future__ import annotations

import inspect
import os
from typing import Any, Dict, Optional, Callable, List

from app.services.telegram import (
    publish_to_telegram,
    poll_telegram_updates_once,
)
from app.services.farcaster import (
    publish_to_farcaster,
    get_cast_metrics,
    get_follower_count,
)
from app.services.finance import FinanceClient
from app.utils.sleep_utils import decide_sleep_hours
from app.agents.blogger_agent import BloggerAgent

from app.services.posts_dao import (
    save_post,
    update_farcaster_metrics,
    list_all_farcaster_casts,
    get_farcaster_totals,
    get_telegram_totals,
)

from app.agents.BloggerReinforcment import BloggerReinforcment


async def _await_if_needed(value: Any) -> Any:
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
        self.rl = BloggerReinforcment()

        # подхватим состояние, если класс это поддерживает
        if hasattr(self.rl, "load"):
            try:
                self.rl.load()
            except Exception as e:  # noqa: BLE001
                print("[reinforce] load failed:", e)

        self._rl_act: Callable[[List[float]], int] = self._bind_act()
        self._rl_update: Optional[Callable[..., Any]] = self._bind_update()
        self._rl_compute_reward: Optional[
            Callable[[List[float], List[float]], float]
        ] = self._bind_compute_reward()

    # ------ RL adapters ------
    def _bind_act(self) -> Callable[[List[float]], int]:
        if hasattr(self.rl, "act"):
            return getattr(self.rl, "act")
        if hasattr(self.rl, "select_action"):
            return getattr(self.rl, "select_action")
        if hasattr(self.rl, "choose"):
            return getattr(self.rl, "choose")
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

    # ------ состояние ------
    async def _state_now(self) -> List[float]:
        """
        Состояние для RL: [money, views, likes, comments, subs]
        Здесь views/likes/comments — СУММА по Farcaster+Telegram (для обучения),
        а отдельные платформенные срезы возвращаем в JSON-ответе.
        """
        balance = await _await_if_needed(self.finance.get_balance())
        fc = get_farcaster_totals()
        tg = get_telegram_totals()

        username = os.getenv("FARCASTER_USERNAME", "")
        subs = 0.0
        if username:
            try:
                subs = float(await get_follower_count(username))
            except Exception as e:  # noqa: BLE001
                print(f"[followers] failed: {e}")

        views = float(fc.get("views", 0) + tg.get("views", 0))
        likes = float(fc.get("likes", 0) + tg.get("likes", 0))
        comments = float(fc.get("replies", 0) + tg.get("replies", 0))

        return [float(balance), views, likes, comments, float(subs)]

    async def run(self) -> Dict[str, Any]:
        prev_state = await self._state_now()

        # решить действие
        try:
            action = int(self._rl_act(prev_state))
        except Exception as e:  # noqa: BLE001
            print(f"[rl] act failed: {e}")
            action = self.ACTION_POST

        tg_resp: Dict[str, Any] = {}
        fc_resp: Dict[str, Any] = {}
        text: str = await _await_if_needed(self.blog_agent.write_post(None))

        if action != self.ACTION_SLEEP:
            # постинг
            tg_resp = await publish_to_telegram(text) or {}
            fc_resp = await publish_to_farcaster(text) or {}

            # сохраняем новые посты
            mid = (tg_resp.get("result") or {}).get("message_id")
            if mid is not None:
                save_post("telegram", str(mid), text)
            cast_hash = (fc_resp.get("cast") or {}).get("hash")
            if cast_hash:
                save_post("farcaster", cast_hash, text)

        # обновим метрики Farcaster по всем нашим кастам
        for h in list_all_farcaster_casts():
            try:
                m = await get_cast_metrics(h)
                update_farcaster_metrics(
                    h, likes=m["likes"], recasts=m["recasts"], replies=m["replies"]
                )
            except Exception as e:  # noqa: BLE001
                print(f"[metrics/fc] failed for {h}: {e}")

        # снимем новый срез реакций в TG
        try:
            tg_added = await poll_telegram_updates_once()
        except Exception as e:  # noqa: BLE001
            print("[metrics/tg] poll failed:", e)
            tg_added = {"likes": 0, "forwards": 0, "replies": 0, "views": 0}

        # следующее состояние
        next_state = await self._state_now()

        # награда
        reward = self._default_reward(prev_state, next_state)
        if self._rl_compute_reward:
            try:
                reward = float(self._rl_compute_reward(prev_state, next_state))
            except Exception as e:  # noqa: BLE001
                print(f"[rl] compute_reward failed: {e}")

        # шаг обучения
        if self._rl_update:
            try:
                try:
                    self._rl_update(prev_state, action, next_state, baseline=0.0)
                except TypeError:
                    self._rl_update(prev_state, action, reward, next_state)
            except Exception as e:  # noqa: BLE001
                print(f"[rl] update failed: {e}")

        if hasattr(self.rl, "save"):
            try:
                self.rl.save()
            except Exception as e:  # noqa: BLE001
                print("[reinforce] save failed:", e)

        # финансы/сон
        balance = await _await_if_needed(self.finance.get_balance())
        if balance > 20:
            await _await_if_needed(self.finance.pay_expenses(10))
        sleep_hours = decide_sleep_hours(balance)

        # раздельная статистика для ответа
        fc_tot = get_farcaster_totals()
        tg_tot = get_telegram_totals()

        return {
            "action": action,
            "reward": reward,
            "telegram": {
                "message_id": (tg_resp.get("result") or {}).get("message_id"),
                "chat_id": (tg_resp.get("result") or {}).get("chat", {}).get("id"),
                "totals": tg_tot,
                "run_added": tg_added,
                "subscribers": int(os.getenv("TG_SUBSCRIBERS", "0") or 0),  # если захочешь хранить
            },
            "farcaster": {
                "cast_hash": (fc_resp.get("cast") or {}).get("hash"),
                "followers": int(
                    next_state[4] if len(next_state) > 4 else 0
                ),
                "totals": {
                    "likes": fc_tot["likes"],
                    "recasts": fc_tot["recasts"],
                    "replies": fc_tot["replies"],
                    "views": fc_tot["views"],
                },
            },
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
