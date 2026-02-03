import os
from dotenv import load_dotenv

load_dotenv()  

class Settings:
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    NSEC: str = os.getenv("NSEC", "")
    RELAYS: str = os.getenv("RELAYS", "wss://relay.damus.io")

    CONTENT_DAO_URL: str = os.getenv("CONTENT_DAO_URL", "https://example.com")
    FINANCE_URL: str = os.getenv("FINANCE_URL", "https://bank.example.com")

settings = Settings()
