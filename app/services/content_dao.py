# app/services/content_dao.py
from __future__ import annotations
import os, httpx
from typing import Any, Dict, List, Optional

class ContentDAO:
    def __init__(self, base_url: Optional[str] = None):
        self.base = (base_url or os.getenv("CONTENT_DAO_URL") or "").rstrip("/")
        if not self.base:
            raise RuntimeError("CONTENT_DAO_URL is not set")
        # Вариант A: используем уже полученные cookie из .env
        cookie = os.getenv("CONTENT_DAO_COOKIE") or ""
        self.client = httpx.AsyncClient(
            base_url=self.base,
            headers={"Cookie": cookie, "Accept": "application/json", "Content-Type": "application/json"},
            timeout=20,
            follow_redirects=True,
        )

    async def me(self) -> Dict[str, Any]:
        r = await self.client.get("/api/influencer/profile")   # проверка авторизации
        r.raise_for_status()
        return r.json()

    async def list_pools(self) -> List[Dict[str, Any]]:
        r = await self.client.get("/api/pool")                 # список пулов
        r.raise_for_status()
        return r.json()

    async def pool_tasks(self, pool_id: str) -> List[Dict[str, Any]]:
        r = await self.client.get(f"/api/pool/{pool_id}/tasks")  # задачи пула
        r.raise_for_status()
        return r.json()

    async def reserve(self, task_id: str, profile_id: str) -> Dict[str, Any]:
        r = await self.client.post("/api/task/reserve", json={"taskId": task_id, "profileId": profile_id})
        r.raise_for_status()
        return r.json()

    async def send_link(self, task_id: str, profile_id: str, link_to_post: str) -> Dict[str, Any]:
        r = await self.client.post("/api/task/send-link",
                                   json={"taskId": task_id, "profileId": profile_id, "linkToPost": link_to_post})
        r.raise_for_status()
        return r.json()

    async def aclose(self):
        await self.client.aclose()

def pick_profile_id(profile: Dict[str, Any], social: str) -> Optional[str]:
    """Возвращает profileId/handle для нужной соцсети из /profile."""
    for p in profile.get("profiles", []):
        if (p.get("socialMedia", {}).get("name") or "").lower() == social.lower():
            # на практике task ожидает profileId; если его нет — вернём handle
            return p.get("profileId") or p.get("handle")
    return None

async def fetch_next_topic_and_reserve(dao: ContentDAO, social: str) -> Optional[Dict[str, Any]]:
    """
    Находит первую доступную задачу под нужную соцсеть, резервирует её
    и возвращает краткий бриф: {taskId, profileId, title, description, brand, poolId}
    """
    me = await dao.me()                                                     # авторизован?
    profile_id = pick_profile_id(me, social)
    if not profile_id:
        return None

    pools = await dao.list_pools()
    for pool in pools:
        tasks = await dao.pool_tasks(pool["id"])
        for t in tasks:
            sm = (t.get("socialMedia", {}) or {}).get("name", "")
            status = (t.get("status") or "").lower()
            if sm.lower() == social.lower() and status in ("available", "new", "open"):
                task_id = t.get("taskId") or t.get("id") or t.get("task_id")
                if not task_id:
                    continue
                # резервируем
                try:
                    await dao.reserve(task_id=task_id, profile_id=profile_id)
                except Exception:
                    # если уже кем-то занята — пробуем следующую
                    continue
                # собираем бриф
                brief = {
                    "taskId": task_id,
                    "profileId": profile_id,
                    "poolId": pool.get("id"),
                    "brand": pool.get("brand") or "",
                    "title": t.get("title") or pool.get("title") or "",
                    "description": t.get("description") or t.get("brief") or "",
                }
                return brief
    return None
