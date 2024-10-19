from dataclasses import dataclass

from fastapi import WebSocket
from loguru import logger


@dataclass
class ClassObject:
    school: str
    grade: int
    class_number: int
    debug: bool = False

class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []
        self.ws_map: dict[WebSocket, ClassObject] = {}
        self.class_map: list[tuple[str, int, int]] = []

    async def connect(self, websocket: WebSocket, school: str, grade: int, class_number: int):
        await websocket.accept()
        self.active_connections.append(websocket)
        if (school, grade, class_number) not in self.class_map:
            self.ws_map[websocket] = ClassObject(school, grade, class_number)
        else:
            self.ws_map[websocket] = ClassObject(school, grade, class_number, debug=True)
            logger.warning(
                f"出现了一个 {school} 学校 {grade} 级 {class_number} 班的重复连接，可能是某地正在调试，"
                f"该连接发生的所有操作均不会计入统计。"
            )
        self.class_map.append((school, grade, class_number))

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
        self.ws_map.pop(websocket)

    @staticmethod
    async def send_personal_message(message: str, websocket: WebSocket):
        await websocket.send_text(message)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            await connection.send_text(message)

    def get_class_object(self, websocket: WebSocket) -> ClassObject:
        return self.ws_map[websocket]