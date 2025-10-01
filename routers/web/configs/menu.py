from fastapi import APIRouter
from utils.path import discovery_path

router = APIRouter()

@router.get("/web/menu")
async def get_menu():
    menu = {
        'data': [
            {
                "to": "/",
                "text": "总览",
                "key": "go-back-home",
                "children": None
            },
            {
                "to": "/autorun",
                "text": "自动任务",
                "key": "autorun",
                "children": None
            },
        ]
    }
    menu['data'].extend(
        [
            {  # 学校
                "text": f"{s} 学校",
                "key": f"school-{s}",
                "raw": s,
                "children": [
                    {  # 年级
                        "text": f"{g} 级",
                        "key": f"school-{s}-grade-{g}",
                        "raw": g,
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
                                "text": f"{c} 班",
                                "key": f"school-{s}-grade-{g}-class-{c}",
                                "raw": c,
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


@router.get('/web/structure')
async def get_structure():
    return [
        {  # 学校
            "text": s,
            "children": [
                {  # 年级
                    "text": g,
                    "children": [
                        {  # 班级
                            "text": c,
                            "children": None
                        } for c in await discovery_path(f"./data/{s}/{g}/")
                    ]
                } for g in await discovery_path(f"./data/{s}/")
            ]
        }
        for s in await discovery_path('./data/')
    ]