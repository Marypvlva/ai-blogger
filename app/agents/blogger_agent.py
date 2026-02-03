# app/agents/blogger_agent.py
from __future__ import annotations

from typing import Optional, Union, Dict, Any


from agents import Agent, Runner  # noqa: F401


try:
    from app.config import settings  # noqa: F401
except Exception:
    settings = None  # type: ignore

try:
    from app.db.session import get_session  
except Exception:
    
    from app.agents.session import get_session  # type: ignore


class BloggerAgent:
    """
    Обёртка над твоими Agent/Runner с единой сессией.
    Метод write_post умеет принимать:
      - строку (готовый промпт или тема),
      - бриф-словарь {"brand","title","description"} — как из ContentDAO.
    """

    def __init__(self) -> None:
        
        self.agent = Agent(
            name="Blogger",
            instructions=(
                "You are a travel micro-blogger for a Telegram channel.\n"
                "Write a catchy, friendly post in Russian.\n"
                "Prefer short sentences. Add 1–2 relevant emojis if appropriate.\n"
                "Avoid clickbait and toxicity. No hashtags.\n"
            ),
        )
        
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

        
        result = await Runner.run(self.agent, prompt, session=self.session)

        
        text = (
            getattr(result, "final_output", None)
            or getattr(result, "text", None)
            or (result if isinstance(result, str) else None)
        )
        if text is None:
            
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
            
            return (
                "Сгенерируй короткий пост для Telegram по брифу.\n"
                f"Бренд: {brand}\n"
                f"Заголовок: {title}\n"
                f"Описание/Требования: {desc}\n"
                "Тон: дружелюбный, информативный, без кликбейта и токсичности. "
                "В конце добавь 1–2 уместных эмодзи. Хештеги не используй."
            )

        if isinstance(topic_or_brief, str) and topic_or_brief.strip():
            
            return (
                "Напиши короткий пост для Telegram на заданную тему, дружелюбно и без кликбейта. "
                "Короткие фразы, 1–2 релевантных эмодзи, без хештегов.\n\n"
                f"Тема/брИф: {topic_or_brief.strip()}"
            )

        
        return (
            "Ты тревел-блогер. Напиши короткий, увлекательный пост для Telegram "
            "про одно интересное место (достопримечательность, маршрут или лайфхак).\n"
            "Короткие фразы, 1–2 уместных эмодзи, без хештегов, без токсичности."
        )
