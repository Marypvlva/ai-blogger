# app/workflows/daily_routine.py

from app.services.content_dao import ContentDAOClient
from app.services.nostr import NostrClient
from app.services.finance import FinanceClient
from app.utils.sleep_utils import decide_sleep_hours
from app.agents.blogger_agent import BloggerAgent

class DailyRoutine:
    """
    Единый сценарий:
      1) (опционально) берём тему из ContentDAO,
      2) генерируем тревел-пост,
      3) публикуем его в Nostr,
      4) проверяем баланс и (опционально) платим,
      5) решаем, сколько спать.
    """

    def __init__(self) -> None:
        # (1) тема
        self.content_dao   = ContentDAOClient()
        # (2) генерация
        self.blog_agent    = BloggerAgent()
        # (3) Nostr
        self.nostr_client  = NostrClient()
        # (4) финансы
        self.finance       = FinanceClient()

    async def run(self) -> dict:
        # 1) (пока без темы)
        topic = None

        # 2) пишем пост
        post_text = await self.blog_agent.write_post(topic)
        print(f"[DailyRoutine] Generated post: {post_text[:60]!r}...")

        # 3) публикуем сразу же в Nostr — метод возвращает event_id
        print("[DailyRoutine] Publishing to Nostr…")
        event_id = await self.nostr_client.publish_note(post_text)
        print(f"[DailyRoutine] Nostr event_id: {event_id}")

        # 4) проверяем баланс
        balance = await self.finance.get_balance()
        print(f"[DailyRoutine] Balance is {balance}")
        if balance > 20:
            await self.finance.pay_expenses(amount=10)
            print("[DailyRoutine] Paid expenses 10 units")

        # 5) решаем, сколько спать
        sleep_hours = decide_sleep_hours(balance)
        print(f"[DailyRoutine] Decided to sleep {sleep_hours} hours")

        return {
            "topic":       topic,
            "post_text":   post_text,
            "event_id":    event_id,
            "balance":     balance,
            "sleep_hours": sleep_hours,
        }
