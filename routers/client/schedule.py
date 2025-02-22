import datetime
import json
import pathlib
from typing import Annotated

from fastapi import APIRouter
from fastapi import Depends, WebSocket, WebSocketDisconnect
from fastapi.responses import ORJSONResponse
from loguru import logger

from routers.web.statistic import statistic
from utils.verify import get_current_identity
from utils.ws import ConnectionManager

router = APIRouter()

websocket_clients: dict[tuple[str, int], ConnectionManager] = {}

@router.get("/{school}/{grade}/{class_number}", response_class=ORJSONResponse)
def get_schedule(
        school: str,
        grade: int,
        class_number: int
):
    """
    获取指定学校、年级、班级的课表
    :param school: 学校编号 / 名称
    :param grade: 年级
    :param class_number: 班级
    :return: 相应的课表配置文件
    """
    logger.info(f"获取 {school} 学校 {grade} 级 {class_number} 班的配置文件")
    return ORJSONResponse(
        {
            **json.loads(
                pathlib.Path(f"./data/{school}/{grade}/subjects.json").read_text()
            ),
            **json.loads(
                pathlib.Path(f"./data/{school}/{grade}/timetable.json").read_text()
            ),
            **json.loads(
                pathlib.Path(f"./data/{school}/{grade}/{class_number}/config.json").read_text()
            ),
            **json.loads(
                pathlib.Path(f"./data/{school}/{grade}/{class_number}/schedule.json").read_text()
            )
        }
    )

@router.websocket("/ws/{school}/{grade}/{class_number}")
async def websocket_endpoint(websocket: WebSocket, school: str, grade: int, class_number: int):
    """
    WebSocket 连接
    :param websocket: WebSocket 对象
    :param school: 学校编号 / 名称
    :param grade: 年级
    :param class_number: 班级
    :return:
    """
    try:
        await websocket_clients[(school, grade)].connect(
            websocket, school, grade, class_number
        )
    except KeyError:
        websocket_clients[(school, grade)] = ConnectionManager()
        await websocket_clients[(school, grade)].connect(
            websocket, school, grade, class_number
        )
    logger.info(f"来自 {school} 学校 {grade} 级 {class_number} 班的 WebSocket 连接建立")
    try:
        while True:
            data = await websocket.receive_text()
            logger.info(f"Received data: {data}")
    except WebSocketDisconnect:
        schedule = {
            **json.loads(
                pathlib.Path(f"./data/{school}/{grade}/timetable.json").read_text()
            ),
            **json.loads(
                pathlib.Path(f"./data/{school}/{grade}/{class_number}/schedule.json").read_text()
            )
        }
        now = datetime.datetime.now()
        class_finish_time = datetime.time().fromisoformat(
            list(
                schedule["timetable"][
                    schedule["daily_class"][
                        now.isoweekday() % 7  # 星期日为 0，星期六为 6
                    ]["timetable"]
                ].keys()
            )[-1].split("-")[0]
        )
        if now.time() < class_finish_time and not websocket_clients[(school, grade)].get_class_object(websocket).debug:
            try:
                statistic["websocket_disconnect"] [f"{school} 学校 {grade} 级 {class_number} 班"] += 1
            except KeyError:
                statistic["websocket_disconnect"] [f"{school} 学校 {grade} 级 {class_number} 班"] = 1
            logger.warning(
                f"现在 {school} 学校 {grade} 级 {class_number} 班还未放学，但连接异常断开，"
                f"本班级今日已异常断开 {statistic['websocket_disconnect'] [f'{school} 学校 {grade} 级 {class_number} 班']} 次"
            )
        websocket_clients[(school, grade)].disconnect(websocket)
        logger.info(f"来自 {school} 学校 {grade} 级 {class_number} 班的 WebSocket 连接断开")
        if not websocket_clients[(school, grade)].active_connections:
            del websocket_clients[(school, grade)]
            logger.info(f"现在 {school} 学校 {grade} 级没有存活的 WebSocket 连接，已清除该连接管理器")


@router.post("/api/broadcast/{school}/{grade}/{class_number}")
async def broadcast_message(
        identity: Annotated[str, Depends(get_current_identity)],
        school: str,
        grade: int,
        class_number: int
):
    """
    广播消息
    :param identity: 身份验证
    :param school: 学校编号 / 名称
    :param grade: 年级
    :param class_number: 班级
    :return: Json，表示成功
    """
    logger.info(f"收到来自 {school} 学校 {grade} 级 {class_number} 班的广播请求，即将向级部广播 SyncConfig 事件，{identity}")
    await websocket_clients[(school, grade)].broadcast("SyncConfig")
    return {"status": 200, "message": "SyncConfig"}