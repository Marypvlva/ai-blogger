from openai import OpenAI
from agents import Agent, Runner  # твои классы из прежнего файла
from app.config import settings

client = OpenAI(api_key=settings.OPENAI_API_KEY)

class BloggerAgent:
    """Обёртка вокруг твоего Agent + Runner."""

    def __init__(self) -> None:
        self.agent = Agent(
            name="Blogger",
            instructions="You are a travel blogger. You are writing posts"
        )

    async def write_post(self, topic: str) -> str:
        """Генерирует пост на заданную тему."""
        """
       +        topic == None  → пишет случайный тревел‑пост.
       +        topic != None →пишет про конкретную тему.
       +        """
        if topic:  # есть тема — пишем о ней
            prompt = f"Create a travel blog post about: {topic}"
        else:
            prompt = (
                "You're a travel blogger. "
                "Write an engaging, random travel blog post about any destination of your choice."
            )
            result = await Runner.run(self.agent, prompt)
            return result.final_output
