import random

def decide_sleep_hours(balance: float) -> int:
    """Наивная стратегия: меньше денег — меньше сон 😊"""
    if balance < 10:
        return 4
    if balance < 50:
        return 6
    return random.randint(7, 9)
