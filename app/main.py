from fastapi import FastAPI, HTTPException
from app.workflows.daily_routine import DailyRoutine

app = FastAPI(title="Blogger Automaton")

@app.post("/run-day")
async def run_day():
    try:
        summary = await DailyRoutine().run()
        return summary
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
