import pathlib

import orjson
from fastapi import APIRouter
from fastapi.responses import ORJSONResponse

from utils.path import discovery_path

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