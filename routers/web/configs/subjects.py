from fastapi import APIRouter, Depends, Body
from fastapi.responses import ORJSONResponse
import pathlib
import orjson
import json
from loguru import logger
from typing import Annotated
from utils.globalvar import websocket_clients
from utils.schedule.dataclasses import Subjects
from utils.verify import get_current_identity

router = APIRouter()

@router.get("/web/config/{school}/{grade}/subjects/options", response_class=ORJSONResponse)
def get_subjects_options(school: str, grade: str):
    subjects: dict = orjson.loads(pathlib.Path(f"./data/{school}/{grade}/subjects.json").read_text())["subject_name"]
    return ORJSONResponse(
        {
            "options": [
                {"label": f"{abbr}（{full}）", "value": abbr} for abbr, full in subjects.items()
            ]
        }
    )

@router.get("/web/config/{school}/{grade}/subjects", response_class=ORJSONResponse)
def get_subjects(school: str, grade: str):
    subjects: dict = orjson.loads(pathlib.Path(f"./data/{school}/{grade}/subjects.json").read_text())["subject_name"]
    return ORJSONResponse(
        {
            "abbr": [{"text": x} for x in subjects.keys()],
            "fullName": [{"text": x} for x in subjects.values()]
        }
    )

@router.put("/web/config/{school}/{grade}/subjects", response_class=ORJSONResponse)
async def update_subjects(
    school: str, grade: int,
    identity: Annotated[str, Depends(get_current_identity)],
    model: Subjects = Body(embed=True),
):
    logger.info(f"收到更新科目请求：{identity}")
    abbr_list = model.abbr
    full_list = model.fullName
    abbrs = [x.text for x in abbr_list]
    fulls = [x.text for x in full_list]
    subject_name = dict(zip(abbrs, fulls))
    data = {"subject_name": subject_name}
    text = json.dumps(data, indent=4, ensure_ascii=False)
    pathlib.Path(f"./data/{school}/{grade}/subjects.json").write_text(text, encoding="utf-8")
    logger.info(f"更新科目：\n{text}")
    try:
        await websocket_clients[(school, grade)].broadcast("SyncConfig")
    except KeyError:
        logger.warning(f"没有找到对应的websocket连接：{school} {grade}")
    return ORJSONResponse({'status': 200})

