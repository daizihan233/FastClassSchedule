import json
import pathlib
from typing import Annotated

import orjson
from fastapi import APIRouter, Depends, Body
from fastapi.responses import ORJSONResponse
from loguru import logger

from utils.globalvar import websocket_clients
from utils.path import discovery_path
from utils.schedule.dataclasses import Schedule
from utils.verify import get_current_identity

router = APIRouter()

@router.get("/web/config/{school}/{grade}/subjects", response_class=ORJSONResponse)
def get_subjects(school: str, grade: str):
    subjects: dict = orjson.loads(pathlib.Path(f"./data/{school}/{grade}/subjects.json").read_text())['subject_name']
    return ORJSONResponse(
        {
            'abbr':[{'text': x} for x in subjects.keys()],
            'fullName': [{'text': x} for x in subjects.values()]
        }
    )

@router.get("/web/config/{school}/{grade}/{cls}/schedule", response_class=ORJSONResponse)
def get_schedule(school: str, grade: str, cls: str):
    schedule: dict = orjson.loads(pathlib.Path(f"./data/{school}/{grade}/{cls}/schedule.json").read_text())
    for index_d, day in enumerate(schedule['daily_class']):
        for index_i, item in enumerate(day['classList']):
            if isinstance(item, str):
                schedule['daily_class'][index_d]['classList'][index_i] = [
                    schedule['daily_class'][index_d]['classList'][index_i]
                ]
    return ORJSONResponse(
        schedule
    )

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
    logger.debug(schedule)
    text = json.dumps(schedule, indent=2, ensure_ascii=False)
    pathlib.Path(f"./data/{school}/{grade}/{cls}/schedule.json").write_text(text)
    logger.info(f"更新课表：\n{text}")
    try:
        await websocket_clients[(school, grade)].broadcast("SyncConfig")
    except KeyError:
        logger.warning(f"没有找到对应的websocket连接：{school} {grade}")
    return ORJSONResponse(
        {'status': 200}
    )

@router.get("/web/config/{school}/{grade}/timetable/options", response_class=ORJSONResponse)
def get_timetable_options(school: str, grade: str):
    timetable: dict[dict] = orjson.loads(
        pathlib.Path(f"./data/{school}/{grade}/timetable.json").read_text()
    )['timetable']

    return ORJSONResponse(
        {
            'options': [
                {'label': x, 'value': x, 'need': max([v for v in timetable[x].values() if isinstance(v, int)])}
                for x in timetable.keys()
            ]
        }
    )


@router.get("/web/menu")
async def get_menu():
    menu = {
        'data': [
            {
                "to": "/",
                "text": "总览",
                "key": "go-back-home",
                "children": None
            }
        ]
    }
    menu['data'].extend(
        [
            {  # 学校
                "to": None,
                "text": f"{s} 学校",
                "key": f"school-{s}",
                "children": [
                    {  # 年级
                        "to": None,
                        "text": f"{g} 级",
                        "key": f"school-{s}-grade-{g}",
                        "children": [
                            {
                                "to": f"/config/{s}/{g}/subjects",
                                "text": "课程设置",
                                "key": f"school-{s}-grade-{g}-subjects",
                                "children": None
                            },
                            {
                                "to": f"/config/{s}/{g}/timetable",
                                "text": "作息设置",
                                "key": f"school-{s}-grade-{g}-timetable",
                                "children": None
                            }
                        ] + [
                            {
                                "to": None,
                                "text": f"{c} 班",
                                "key": f"school-{s}-grade-{g}-class-{c}",
                                "children": [
                                    {
                                        "to": f"/config/{s}/{g}/{c}/schedule",
                                        "text": "课表设置",
                                        "key": f"school-{s}-grade-{g}-class-{c}-schedule",
                                        "children": None
                                    },
                                    {
                                        "to": f"/config/{s}/{g}/{c}/settings",
                                        "text": "通用设置",
                                        "key": f"school-{s}-grade-{g}-class-{c}-settings",
                                        "children": None
                                    }
                                ]
                            } for c in await discovery_path(f"./data/{s}/{g}/")
                        ]
                    } for g in await discovery_path(f"./data/{s}/")
                ]
            }
            for s in await discovery_path('./data/')
        ]
    )
    return menu