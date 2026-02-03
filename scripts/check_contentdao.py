# scripts/check_contentdao.py
# scripts/check_contentdao.py
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")  

import asyncio
from app.services.content_dao import ContentDAO  

async def main():
    dao = ContentDAO()
    me = await dao.me()
    print("OK: profile loaded")
    print(me)
    await dao.aclose()

if __name__ == "__main__":
    asyncio.run(main())


import asyncio
import os
from dotenv import load_dotenv


load_dotenv()

from app.services.content_dao import ContentDAO  # noqa: E402


async def main():
    dao = ContentDAO()          
    me = await dao.me()         # GET /api/influencer/profile
    print("OK: profile loaded")
    print(me)

    await dao.aclose()


if __name__ == "__main__":
    asyncio.run(main())
