from openai import OpenAI
from agents import Agent, Runner  # твои классы из прежнего файла
from app.config import settings
from app.db.session import get_session
from typing import Optional

client = OpenAI(api_key=settings.OPENAI_API_KEY)

class BloggerAgent:
    """Обёртка вокруг твоего Agent + Runner."""

    def __init__(self) -> None:
        self.agent = Agent(
            name="Blogger",
            instructions="You are a travel blogger. You are writing posts"
        )
        # одна и та же сессия для всех вызовов → память сохранится
        self.session = get_session("blogger")

    async def write_post(self, topic: Optional[str] = None) -> str:
        if topic:
            prompt = f"Create a travel blog post about: {topic}"
        else:
            prompt = (
                "You're a travel blogger. "
                "Write an engaging, random travel blog post about any destination."
            )

        # передаём session → Runner сам запишет обе реплики в agents.sqlite
        result = await Runner.run(self.agent, prompt, session=self.session)
        return result.final_output
