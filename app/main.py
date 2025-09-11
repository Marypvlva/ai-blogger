from fastapi import FastAPI, HTTPException
from dotenv import load_dotenv

load_dotenv()

from app.workflows.daily_routine import DailyRoutine

app = FastAPI(title="Blogger Automaton")




@app.post("/run-day", summary="Запустить ежедневный workflow")
async def run_day():
    """
    Генерирует пост, публикует в TG и Farcaster, обновляет метрики и обучает RL.
    Возвращает JSON-резюме.
    """
    try:
        result = await DailyRoutine().run()
        # ВАЖНО: реально вернуть JSON, а не None
        return result
    except Exception as exc:  # pylint: disable=broad-except
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ---------- DEBUG RL ----------
# Не скрываем импорт ошибками — если путь неверный, увидите понятную ошибку в логах.
from app.agents.BloggerReinforcment import BloggerReinforcment  # noqa: E402

import dataclasses
from collections import defaultdict
import json


def _to_jsonable(obj):
    """Рекурсивно приводим к JSON-friendly структурам."""
    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj
    if dataclasses.is_dataclass(obj):
        return _to_jsonable(dataclasses.asdict(obj))
    if isinstance(obj, (dict, defaultdict)):
        return {str(k): _to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [_to_jsonable(v) for v in obj]
    if hasattr(obj, "tolist"):
        try:
            return _to_jsonable(obj.tolist())
        except Exception:
            pass
    if hasattr(obj, "__dict__"):
        try:
            return _to_jsonable(vars(obj))
        except Exception:
            pass
    try:
        json.dumps(obj)
        return obj
    except Exception:
        return repr(obj)


@app.get("/debug/reinforce", summary="Показать текущие параметры RL-агента")
def debug_reinforce():
    r = BloggerReinforcment()
    # если у вас есть состояние на диске
    if hasattr(r, "load"):
        try:
            r.load()
        except Exception:
            pass

    payload = None
    if hasattr(r, "debug_params"):
        try:
            payload = r.debug_params()
        except Exception as e:
            payload = {"error": f"debug_params() failed: {e}"}
    elif hasattr(r, "state_dict"):
        payload = r.state_dict()
    elif hasattr(r, "q_table"):
        payload = r.q_table
    else:
        payload = {"detail": "No debug_params/state_dict/q_table on BloggerReinforcment"}

    return _to_jsonable(payload)


@app.get("/debug/reinforce/raw", summary="Сырой вывод debug_params() как текст")
def debug_reinforce_raw():
    r = BloggerReinforcment()
    if hasattr(r, "load"):
        try:
            r.load()
        except Exception:
            pass
    if hasattr(r, "debug_params"):
        try:
            return {"text": repr(r.debug_params())}
        except Exception as e:
            return {"text": f"debug_params() failed: {e}"}
    return {"text": "No debug_params() on BloggerReinforcment"}
