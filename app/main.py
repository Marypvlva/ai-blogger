from fastapi import FastAPI, HTTPException
from app.workflows.daily_routine import DailyRoutine

app = FastAPI(title="Blogger Automaton")


@app.post("/run-day", summary="Запустить ежедневный workflow")
async def run_day():
    """
    Генерирует пост, публикует его в Bluesky, обслуживает финансы
    и возвращает JSON-резюме.
    """
    try:
        return await DailyRoutine().run()
    except Exception as exc:          # pylint: disable=broad-except
        raise HTTPException(status_code=500, detail=str(exc)) from exc
