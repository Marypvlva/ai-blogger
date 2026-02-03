from pathlib import Path
from agents import SQLiteSession

BASE = Path(__file__).parent / "data"
BASE.mkdir(parents=True, exist_ok=True)

def get_session(name: str = "blogger") -> SQLiteSession:
    """
    Возвращает persistent‑сессию.
    Один файл agents.sqlite хранит истории разных session_id.
    """
    return SQLiteSession(
        session_id=name,                              
        db_path=str(BASE / "agents.sqlite")           
    )
