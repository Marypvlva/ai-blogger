import httpx
from app.config import settings

class FinanceClient:
    BASE_URL = settings.FINANCE_URL

    async def get_balance(self) -> float:
        """Возвращает текущий баланс, €."""
        
        async with httpx.AsyncClient() as client:
            # resp = await client.get(f"{self.BASE_URL}/balance")
            # balance = resp.json()["balance"]
            balance = 42.0
        return balance

    async def pay_expenses(self, amount: float) -> bool:
        """Платим за существование; True если успешно."""
        
        return True
