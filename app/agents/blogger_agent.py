# app/agents/blogger_agent.py
from __future__ import annotations

from typing import Optional, Union, Dict, Any

# Твои классы агента/раннера
from agents import Agent, Runner  # noqa: F401

# Настройки и сессия: поддержим обе раскладки проекта
try:
    from app.config import settings  # noqa: F401
except Exception:
    settings = None  # type: ignore

try:
    from app.db.session import get_session  # вариант 1: db/session.py
except Exception:
    # вариант 2: agents/session.py
    from app.agents.session import get_session  # type: ignore


class BloggerAgent:
    """
    Обёртка над твоими Agent/Runner с единой сессией.
    Метод write_post умеет принимать:
      - строку (готовый промпт или тема),
      - бриф-словарь {"brand","title","description"} — как из ContentDAO.
    """

    def __init__(self) -> None:
        # Базовые инструкции для роли (микро-блогер про путешествия)
        self.agent = Agent(
            name="Blogger",
            instructions=(
                "You are a travel micro-blogger for a Telegram channel.\n"
                "Write a catchy, friendly post in Russian.\n"
                "Prefer short sentences. Add 1–2 relevant emojis if appropriate.\n"
                "Avoid clickbait and toxicity. No hashtags.\n"
            ),
        )
        # одна и та же сессия — чтобы сохранялась память в agents.sqlite
        self.session = get_session("blogger")

    async def write_post(self, topic_or_brief: Optional[Union[str, Dict[str, Any]]] = None) -> str:
        """
        :param topic_or_brief:
            - str: будет воспринято как готовый промпт/тема.
            - dict: ожидаются ключи brand/title/description (передаются как бриф).
            - None: сгенерируем рандомный тревел-пост.
        :return: сгенерированный текст поста (очищенный).
        """
        prompt = self._build_prompt(topic_or_brief)

        # Runner сам пишет историю в БД через session
        result = await Runner.run(self.agent, prompt, session=self.session)

        # безопасные фолбэки под разные версии Runner’а
        text = (
            getattr(result, "final_output", None)
            or getattr(result, "text", None)
            or (result if isinstance(result, str) else None)
        )
        if text is None:
            # иногда результат лежит в .message / .content / .output
            text = (
                getattr(result, "message", None)
                or getattr(result, "content", None)
                or getattr(result, "output", None)
                or ""
            )
        return str(text).strip()

    # ------------------------ helpers ------------------------

    def _build_prompt(self, topic_or_brief: Optional[Union[str, Dict[str, Any]]]) -> str:
        """
        Собираем финальный промпт для LLM из строки или брифа.
        """
        if isinstance(topic_or_brief, dict):
            brand = str(topic_or_brief.get("brand", "") or "")
            title = str(topic_or_brief.get("title", "") or "")
            desc = str(topic_or_brief.get("description", "") or topic_or_brief.get("brief", "") or "")
            # Бриф из ContentDAO
            return (
                "Сгенерируй короткий пост для Telegram по брифу.\n"
                f"Бренд: {brand}\n"
                f"Заголовок: {title}\n"
                f"Описание/Требования: {desc}\n"
                "Тон: дружелюбный, информативный, без кликбейта и токсичности. "
                "В конце добавь 1–2 уместных эмодзи. Хештеги не используй."
            )

        if isinstance(topic_or_brief, str) and topic_or_brief.strip():
            # Пользователь передал готовый промпт/тему — просто уточним формат
            return (
                "Напиши короткий пост для Telegram на заданную тему, дружелюбно и без кликбейта. "
                "Короткие фразы, 1–2 релевантных эмодзи, без хештегов.\n\n"
                f"Тема/брИф: {topic_or_brief.strip()}"
            )

        # Запасной вариант: случайная тревел-тема
        return (
            "Ты тревел-блогер. Напиши короткий, увлекательный пост для Telegram "
            "про одно интересное место (достопримечательность, маршрут или лайфхак).\n"
            "Короткие фразы, 1–2 уместных эмодзи, без хештегов, без токсичности."
        )
