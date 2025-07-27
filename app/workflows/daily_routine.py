"""
Единый сценарий: беру тему → пишу пост → публикую →
смотрю баланс → решаю платить или копить → решаю поспать.
"""
from app.services.content_dao import ContentDAOClient
from app.services.farcaster import FarcasterClient
from app.services.finance import FinanceClient
from app.utils.sleep_utils import decide_sleep_hours
from app.agents.blogger_agent import BloggerAgent

class DailyRoutine:
    def __init__(self) -> None:
        self.content_dao = ContentDAOClient()
        self.blog_agent = BloggerAgent()
        self.farcaster = FarcasterClient()
        self.finance = FinanceClient()

    async def run(self) -> dict:
        # Пока тема не нужна — сразу пишем случайный пост
        topic = None
        post = await self.blog_agent.write_post(topic)

        post_id = await self.farcaster.publish_post(post)

        balance = await self.finance.get_balance()
        if balance > 20:
            await self.finance.pay_expenses(amount=10)

        sleep_hours = decide_sleep_hours(balance)
        return {
            "topic": topic,  # будет None (можно убрать, но оставлю для совместимости)
            "post": post,  # 👈 сам текст поста теперь в ответе
            "post_id": post_id,
            "balance": balance,
            "sleep_hours": sleep_hours
        }
