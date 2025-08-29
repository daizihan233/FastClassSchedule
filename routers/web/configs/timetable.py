from fastapi import APIRouter, Depends, Body
from fastapi.responses import ORJSONResponse
import pathlib
import orjson
import json
from loguru import logger
from typing import Annotated
from utils.globalvar import websocket_clients
from utils.schedule.dataclasses import Timetable
from utils.verify import get_current_identity

router = APIRouter()

@router.get("/web/config/{school}/{grade}/timetable/options", response_class=ORJSONResponse)
def get_timetable_options(school: str, grade: str):
    timetable: dict[str, dict] = orjson.loads(
        pathlib.Path(f"./data/{school}/{grade}/timetable.json").read_text()
    )["timetable"]
    return ORJSONResponse(
        {
            "options": [
                {"label": x, "value": x, "need": max([v for v in timetable[x].values() if isinstance(v, int)])}
                for x in timetable.keys()
            ]
        }
    )

@router.get("/web/config/{school}/{grade}/timetable", response_class=ORJSONResponse)
def get_timetable(school: str, grade: str):
    data = orjson.loads(pathlib.Path(f"./data/{school}/{grade}/timetable.json").read_text())
    return ORJSONResponse(data)

@router.put("/web/config/{school}/{grade}/timetable", response_class=ORJSONResponse)
async def update_timetable(
    school: str, grade: int,
    identity: Annotated[str, Depends(get_current_identity)],
    timetable: Timetable,
):
    logger.info(f"收到更新作息时间请求：{identity}")
    text = json.dumps(timetable.model_dump(), indent=4, ensure_ascii=False)
    pathlib.Path(f"./data/{school}/{grade}/timetable.json").write_text(text, encoding="utf-8")
    logger.info(f"更新作息时间：\n{text}")
    try:
        await websocket_clients[(school, grade)].broadcast("SyncConfig")
    except KeyError:
        logger.warning(f"没有找到对应的websocket连接：{school} {grade}")
    return ORJSONResponse({'status': 200})
