import os
import asyncio
import httpx
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())

API_KEY = os.getenv("NEYNAR_API_KEY")

async def test_key():
    if not API_KEY:
        print("❗ NEYNAR_API_KEY is empty. Check your .env file and working directory.")
        return

    url = "https://api.neynar.com/v2/farcaster/user/search"
    headers = {
        "accept": "application/json",
        "x-api-key": API_KEY,   # <- correct header name
    }
    params = {"q": "dwr"}

    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(url, headers=headers, params=params)
        print("Status:", r.status_code)
        print(r.text)

if __name__ == "__main__":
    asyncio.run(test_key())
