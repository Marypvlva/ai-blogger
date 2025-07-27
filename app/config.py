import os
from dotenv import load_dotenv

load_dotenv()  # ищет .env в корне

class Settings:
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    FARCASTER_API_KEY: str = os.getenv("FARCASTER_API_KEY", "")
    CONTENT_DAO_URL: str = os.getenv("CONTENT_DAO_URL", "https://example.com")
    FINANCE_URL: str = os.getenv("FINANCE_URL", "https://bank.example.com")

settings = Settings()
