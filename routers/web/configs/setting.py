from fastapi import APIRouter, Depends
from fastapi.responses import ORJSONResponse
import pathlib
import orjson
import json
from loguru import logger
from typing import Annotated
from utils.globalvar import websocket_clients
from utils.schedule.dataclasses import Setting
from utils.verify import get_current_identity

router = APIRouter()

@router.get("/web/config/{school}/{grade}/{cls}/settings", response_class=ORJSONResponse)
def get_setting(school: str, grade: str, cls: str):
    data = orjson.loads(pathlib.Path(f"./data/{school}/{grade}/{cls}/config.json").read_text())
    return ORJSONResponse(data)

@router.put("/web/config/{school}/{grade}/{cls}/settings", response_class=ORJSONResponse)
async def update_setting(
    school: str, grade: int, cls: int,
    identity: Annotated[str, Depends(get_current_identity)],
    setting: Setting,
):
    logger.info(f"收到更新设置请求：{identity}")
    text = json.dumps(setting.model_dump(), indent=4, ensure_ascii=False)
    pathlib.Path(f"./data/{school}/{grade}/{cls}/config.json").write_text(text, encoding="utf-8")
    logger.info(f"更新设置：\n{text}")
    try:
        await websocket_clients[(school, grade)].broadcast("SyncConfig")
    except KeyError:
        logger.warning(f"没有找到对应的websocket连接：{school} {grade}")
    return ORJSONResponse({'status': 200})

