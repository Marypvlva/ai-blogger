from __future__ import annotations
from fastapi import FastAPI, HTTPException
from dotenv import load_dotenv
load_dotenv()

from app.workflows.daily_routine import DailyRoutine
from app.services.telegram import debug_fetch_updates_raw

app = FastAPI(title="Blogger Automaton")


@app.post("/run-day", summary="Запустить ежедневный workflow")
async def run_day():
    try:
        return await DailyRoutine().run()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/debug/telegram/raw", summary="Debug Tg Raw")
async def debug_tg_raw():
    try:
        return await debug_fetch_updates_raw()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
