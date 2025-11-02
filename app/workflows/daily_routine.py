"""
Генерирует пост по брифу из ContentDAO, публикует его в Telegram и Farcaster,
обновляет метрики Farcaster и ОДИН раз опрашивает Telegram-реакции.
(Обучение RL оставлено как было у тебя.)
"""
from __future__ import annotations

import inspect
import os
from typing import Any, Dict, List, Optional, Callable

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
)

from app.agents.BloggerReinforcment import BloggerReinforcment

# === ContentDAO интеграция ===
# Ожидается, что в app/services/content_dao.py есть:
#   - класс ContentDAO (использующий COOKIE из .env)
#   - функция fetch_next_topic_and_reserve(dao, social="Telegram") -> dict|None
# Если у тебя другая сигнатура — поправь импорты/вызов ниже.
try:
    from app.services.content_dao import ContentDAO, fetch_next_topic_and_reserve
except Exception:
    ContentDAO = None  # type: ignore
    fetch_next_topic_and_reserve = None  # type: ignore


async def _await_if_needed(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


def _build_tg_link(chat_id: int | str, message_id: int, public_username: Optional[str] = None) -> str:
    """
    Для публичного канала лучше передать public_username (username канала).
    Для приватного/без username: используем формат t.me/c/<id>/<mid>, где id = chat_id без префикса -100.
    """
    if public_username:
        return f"https://t.me/{public_username}/{message_id}"
    chat_str = str(chat_id)
    ch_id = chat_str.replace("-100", "") if chat_str.startswith("-100") else chat_str
    return f"https://t.me/c/{ch_id}/{message_id}"


class DailyRoutine:
    ACTION_POST = 0
    ACTION_SLEEP = 4

    def __init__(self) -> None:
        self.blog_agent = BloggerAgent()
        self.finance = FinanceClient()
        self.rl = BloggerReinforcment()

        self._rl_act: Callable[[List[float]], int] = getattr(self.rl, "act", lambda s: 0)
        self._rl_update: Optional[Callable[..., Any]] = getattr(self.rl, "update", None)
        self._rl_compute_reward: Optional[Callable[[List[float], List[float]], float]] = getattr(
            self.rl, "compute_reward", None
        )

    async def _state_now(self) -> List[float]:
        balance = await _await_if_needed(self.finance.get_balance())
        agg = get_farcaster_totals()
        username = os.getenv("FARCASTER_USERNAME", "")
        subs = 0.0
        if username:
            try:
                subs = float(await get_follower_count(username))
            except Exception:
                subs = 0.0
        return [float(balance), float(agg["views"]), float(agg["likes"]), float(agg["replies"]), float(subs)]

    async def run(self) -> Dict[str, Any]:
        prev_state = await self._state_now()

        try:
            action = int(self._rl_act(prev_state))
        except Exception:
            action = self.ACTION_POST

        # ---------- 0) Бриф из ContentDAO (и резерв задачи) ----------
        brief: Optional[Dict[str, Any]] = None
        dao = None
        if ContentDAO and fetch_next_topic_and_reserve:
            try:
                dao = ContentDAO()  # использует CONTENT_DAO_URL и CONTENT_DAO_COOKIE из .env
                brief = await fetch_next_topic_and_reserve(dao, social="Telegram")
            except Exception as e:
                print("[ContentDAO] fetch brief failed:", e)
                brief = None

        # ---------- 1) Генерация текста поста ----------
        if brief:
            # передаём только сам бриф — BloggerAgent сам оформит промпт
            topic_or_brief = (
                f"Бренд: {brief.get('brand', '')}\n"
                f"Заголовок: {brief.get('title', '')}\n"
                f"Описание: {brief.get('description', '')}"
            )
        else:
            # ничего не передаём → BloggerAgent использует тревел-фолбэк
            topic_or_brief = None

        post_text: str = await _await_if_needed(self.blog_agent.write_post(topic_or_brief))

        tg_resp: Dict[str, Any] = {}
        fc_hash: Optional[str] = None

        # ---------- 2) Публикация ----------
        if action != self.ACTION_SLEEP:
            # Telegram
            tg_resp = await publish_to_telegram(post_text) or {}

            # Farcaster
            fc_resp = await publish_to_farcaster(post_text) or {}
            fc_hash = (fc_resp.get("cast") or {}).get("hash")
            if fc_hash:
                save_post("farcaster", fc_hash, post_text)

        # ---------- 3) Отчёт в ContentDAO (send-link) ----------
        if brief and tg_resp:
            try:
                result = tg_resp.get("result") or {}
                message_id = result.get("message_id")
                chat_id = (result.get("chat") or {}).get("id")
                if message_id is not None and chat_id is not None and dao:
                    tg_username = os.getenv("TELEGRAM_PUBLIC_USERNAME")  # если канал публичный
                    link = _build_tg_link(chat_id, message_id, tg_username)
                    await dao.send_link(task_id=brief["taskId"], profile_id=brief["profileId"], link_to_post=link)
            except Exception as e:
                print("[ContentDAO] send-link failed:", e)
        if dao:
            try:
                await dao.aclose()
            except Exception:
                pass

        # ---------- 4) Farcaster: обновим метрики у всех кастов ----------
        for h in list_all_farcaster_casts():
            try:
                m = await get_cast_metrics(h)
                update_farcaster_metrics(h, likes=m["likes"], recasts=m["recasts"], replies=m["replies"])
            except Exception as e:
                print("[farcaster metrics] failed:", e)

        # ---------- 5) Telegram: один опрос getUpdates → агрегат за этот опрос ----------
        try:
            tg_added = await poll_telegram_updates_once()
        except Exception as e:
            print("[telegram poll] failed:", e)
            tg_added = {"likes": 0, "forwards": 0, "replies": 0, "views": 0}

        # ---------- 6) RL: расчёт награды и обновление ----------
        next_state = await self._state_now()

        reward = self._default_reward(prev_state, next_state)
        if self._rl_compute_reward:
            try:
                reward = float(self._rl_compute_reward(prev_state, next_state))
            except Exception:
                pass
        if self._rl_update:
            try:
                self._rl_update(prev_state, action, next_state, baseline=0.0)
            except TypeError:
                self._rl_update(prev_state, action, reward, next_state)
            except Exception:
                pass

        # ---------- 7) Финансы и сон ----------
        balance = await _await_if_needed(self.finance.get_balance())
        if balance > 20:
            await _await_if_needed(self.finance.pay_expenses(10))
        sleep_hours = decide_sleep_hours(balance)

        # ---------- 8) Ответ ----------
        return {
            "action": action,
            "reward": reward,
            "telegram": {
                "message_id": (tg_resp.get("result") or {}).get("message_id"),
                "chat_id": (tg_resp.get("result") or {}).get("chat", {}).get("id"),
                "run_added": tg_added,  # сколько добавилось за этот опрос
            },
            "farcaster": {
                "cast_hash": fc_hash,
                "totals": get_farcaster_totals(),
            },
            "brief_used": bool(brief),
            "prev_state": prev_state,
            "next_state": next_state,
            "balance": balance,
            "sleep_hours": sleep_hours,
        }

    @staticmethod
    def _default_reward(prev_state: List[float], next_state: List[float]) -> float:
        d_views = max(0.0, float(next_state[1] - prev_state[1]))
        d_likes = max(0.0, float(next_state[2] - prev_state[2]))
        d_repl  = max(0.0, float(next_state[3] - prev_state[3]))
        d_subs  = max(0.0, float(next_state[4] - prev_state[4]))
        return d_likes + 2.0 * d_views + 3.0 * d_repl + 4.0 * d_subs
