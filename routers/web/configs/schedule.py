from fastapi import APIRouter, Depends, Body
from fastapi.responses import ORJSONResponse
import pathlib
import orjson
import json
from loguru import logger
from typing import Annotated
from utils.globalvar import websocket_clients
from utils.schedule import run_fix
from utils.schedule.dataclasses import Schedule
from utils.verify import get_current_identity

router = APIRouter()

@router.get("/web/config/{school}/{grade}/{cls}/schedule", response_class=ORJSONResponse)
def get_schedule(school: str, grade: str, cls: str):
    schedule: dict = orjson.loads(pathlib.Path(f"./data/{school}/{grade}/{cls}/schedule.json").read_text())
    timetable: dict[str, dict] = orjson.loads(
        pathlib.Path(f"./data/{school}/{grade}/timetable.json").read_text()
    )["timetable"]
    max_subjects = max([max([v for v in timetable[x].values() if isinstance(v, int)]) for x in timetable.keys()]) + 1
    for index_d, day in enumerate(schedule["daily_class"]):
        # 校验 daily_class.timetable 是否在 timetable 中，不存在则指定为“常日”
        if "timetable" in day and day["timetable"] not in timetable:
            schedule["daily_class"][index_d]["timetable"] = "常日"
        for index_i, item in enumerate(day["classList"]):
            if isinstance(item, str):
                schedule["daily_class"][index_d]["classList"][index_i] = [
                    schedule["daily_class"][index_d]["classList"][index_i]
                ]
        if len(schedule["daily_class"][index_d]["classList"]) < max_subjects:
            schedule["daily_class"][index_d]["classList"].extend(
                [["课"]] * (max_subjects - len(schedule["daily_class"][index_d]["classList"]))
            )
    return ORJSONResponse(schedule)

@router.put("/web/config/{school}/{grade}/{cls}/schedule", response_class=ORJSONResponse)
async def update_schedule(
        school: str, grade: int, cls: int,
        identity: Annotated[str, Depends(get_current_identity)],
        model: Schedule = Body(embed=True),
):
    logger.info(f"收到更新课表请求：{identity}")
    mjson = model.model_dump()
    schedule: dict = mjson.copy()
    logger.debug(mjson)
    for index_d, day in enumerate(schedule['daily_class']):
        for index_i, item in enumerate(day['classList']):
            if len(item) == 1:
                schedule['daily_class'][index_d]['classList'][index_i] = schedule['daily_class'][index_d][
                    'classList'
                ][index_i][0]
    schedule = {
        'daily_class': (
            await run_fix(
                {
                    **schedule,
                    **json.loads(
                        pathlib.Path(f"./data/{school}/{grade}/timetable.json").read_text()
                    )
                }
            )
        )['daily_class']
    }
    logger.debug(schedule)
    text = json.dumps(schedule, indent=4, ensure_ascii=False)
    pathlib.Path(f"./data/{school}/{grade}/{cls}/schedule.json").write_text(text)
    logger.info(f"更新课表：\n{text}")
    try:
        await websocket_clients[(school, grade)].broadcast("SyncConfig")
    except KeyError:
        logger.warning(f"没有找到对应的websocket连接：{school} {grade}")
    return ORJSONResponse({'status': 200})
