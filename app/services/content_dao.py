import httpx
from app.config import settings

class ContentDAOClient:
    BASE_URL = settings.CONTENT_DAO_URL

    async def fetch_topic(self) -> str:
        """Берём свежую тему на сайте контент‑ДАУ."""
        # TODO: заменить на реальный эндпоинт/парсер
        async with httpx.AsyncClient() as client:
            # resp = await client.get(f"{self.BASE_URL}/today-topic")
            # topic = resp.json()["topic"]
            topic = "Placeholder topic from Content DAO"
        return topic
