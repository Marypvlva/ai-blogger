import httpx
from app.config import settings

class FarcasterClient:
    BASE_URL = "https://api.farcaster.xyz"

    async def publish_post(self, content: str) -> str:
        """Публикует пост и возвращает ссылку/ID."""
        # TODO: заменить на реальное API + авторизацию
        async with httpx.AsyncClient() as client:
            # resp = await client.post(f"{self.BASE_URL}/posts",
            #                          headers={"Authorization": f"Bearer {settings.FARCASTER_API_KEY}"},
            #                          json={"text": content})
            # post_id = resp.json()["id"]
            post_id = "fake‑post‑id"
        return post_id
