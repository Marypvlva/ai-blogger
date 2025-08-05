import os, ssl, json, time, asyncio
from typing import List

from app.config import settings

# Install:  pip install pynostr
from pynostr.key import PrivateKey
from pynostr.event import Event
from pynostr.relay_manager import RelayManager

class NostrClient:
    """Send short text-notes (kind 1) to the given relays."""

    def __init__(self) -> None:
        nsec = settings.NSEC
        if not nsec:
            raise RuntimeError("NSEC is not set in .env")
        self.sk = PrivateKey.from_nsec(nsec)
        self.relays: List[str] = settings.RELAYS.split(",")

    async def publish_note(self, content: str) -> str:
        event = Event(
            pubkey=self.sk.public_key.hex(),
            created_at=int(time.time()),
            kind=1,
            tags=[],
            content=content,
        )
        event.sign(self.sk.hex())

        rm = RelayManager(self.relays)
        rm.open_connections({"cert_reqs": ssl.CERT_NONE})
        rm.publish_event(event)
        rm.close_connections()

        return event.id            # return the event-ID (32-byte hex)
