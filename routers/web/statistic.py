from fastapi import APIRouter
from fastapi.responses import ORJSONResponse

from utils.ws import ConnectionManager

router = APIRouter()

statistic = {
    "weather_error": 0,  # 天气 API 响应错误次数（不含重试次数）
    "websocket_disconnect": {},   # 各班 WebSocket 连接异常断开次数
}
websocket_clients: dict[tuple[str, int], ConnectionManager] = {}

def reset_statistic():
    global statistic
    statistic = {
        "weather_error": 0,  # 天气 API 响应错误次数（不含重试次数）
        "websocket_disconnect": {}  # WebSocket 连接异常断开次数
    }

@router.get("/web/statistic", response_class=ORJSONResponse)
def get_statistic():
    """
    获取统计信息
    :return: Json，表示统计信息
    """
    websocket_clients_list = {"clients": []}
    for (school, grade), manager in websocket_clients.items():
        for client in manager.active_connections:
            if manager.get_class_object(client).debug:
                continue
            websocket_clients_list["clients"].append(
                f"{school} 学校 {grade} 级 {manager.get_class_object(client).class_number} 班"
            )
    return ORJSONResponse(
        {
            **statistic,
            **websocket_clients_list,
            **{
                "websocket_disconnect_count": sum(statistic["websocket_disconnect"].values()),
                "clients_count": len(websocket_clients_list["clients"])
            }
        }
    )