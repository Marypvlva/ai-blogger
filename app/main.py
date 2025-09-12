# app/main.py
from __future__ import annotations

from fastapi import FastAPI, HTTPException
from dotenv import load_dotenv

from app.workflows.daily_routine import DailyRoutine
from app.services.telegram import (
    debug_fetch_updates_raw,
    poll_telegram_updates_once,
    init_telegram_updates,
)

load_dotenv()  # подтянет .env из корня

app = FastAPI(title="Blogger Automaton", version="0.1.0")


@app.on_event("startup")
async def _startup() -> None:
    # не обязательно, но полезно один раз «разбудить» getUpdates
    try:
        await init_telegram_updates()
    except Exception:
        pass


@app.post("/run-day", summary="Запустить ежедневный workflow")
async def run_day():
    try:
        return await DailyRoutine().run()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# --------- DEBUG: Telegram ---------

@app.get("/debug/telegram/raw", summary="Debug Tg Raw")
async def debug_tg_raw():
    try:
        return await debug_fetch_updates_raw()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/debug/telegram/reactions", summary="Debug Tg Reactions")
async def debug_tg_reactions():
    try:
        return await poll_telegram_updates_once()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
