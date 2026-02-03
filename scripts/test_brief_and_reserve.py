import sys, asyncio
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from app.services.content_dao import ContentDAO, fetch_next_topic_and_reserve  # type: ignore

async def main():
    dao = ContentDAO()
    brief = await fetch_next_topic_and_reserve(dao, social="Telegram")
    print("BRIEF:", brief)
    await dao.aclose()

if __name__ == "__main__":
    asyncio.run(main())
