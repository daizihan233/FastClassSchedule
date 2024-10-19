import datetime
import json
import pathlib
import secrets
from contextlib import asynccontextmanager
from typing import Annotated

import toml
import uvicorn
from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI, HTTPException, status, Depends, WebSocket, WebSocketDisconnect
from fastapi.responses import ORJSONResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from loguru import logger
from fastapi.middleware.cors import CORSMiddleware

from utils import config as utils_config
from utils import weather
from utils.ws import ConnectionManager

security = HTTPBasic()
statistic = {
    "weather_error": 0,  # 天气 API 响应错误次数（不含重试次数）
    "websocket_disconnect": {}   # WebSocket 连接异常断开次数
}
CONFIG_PATH = "config.toml"
DEFAULT_CONFIG = """\
[apikey]
weather = "YOUR_API_KEY"

[secret]
token = "YOUR_SECRET_TOKEN"

[server]
host = "0.0.0.0"
port = 8114
    
    

[log]
level = "INFO"
file = "logs/app.log"
rotation = "00:00"
retention = "14 days"
"""
websocket_clients: dict[tuple[str, int], ConnectionManager] = {}
scheduler = BackgroundScheduler()

if not pathlib.Path(CONFIG_PATH).exists():
    pathlib.Path(CONFIG_PATH).touch()
    pathlib.Path(CONFIG_PATH).write_text(DEFAULT_CONFIG)
    logger.error("配置文件已生成，请填写相关配置再运行")
    exit(1)
CONFIG_JSON = toml.load(CONFIG_PATH)
try:
    config = utils_config.Config(
        apikey=utils_config.ApiKey(**CONFIG_JSON["apikey"]),
        secret=utils_config.Secret(**CONFIG_JSON["secret"]),
        server=utils_config.Server(**CONFIG_JSON["server"]),
        log=utils_config.Log(**CONFIG_JSON["log"]),
    )
except TypeError as e:
    logger.exception(
        f"配置文件可能缺少或存在过多字段，这可能是由于升级所致，您也可以删除并重新生成配置文件：{e}",
        exc_info=True
    )
    exit(1)
del DEFAULT_CONFIG, CONFIG_PATH, CONFIG_JSON


def get_current_identity(
    credentials: Annotated[HTTPBasicCredentials, Depends(security)],
):
    current_username_bytes = credentials.username.encode("utf8")
    correct_username_bytes = b"ElectronClassSchedule"
    is_correct_username = secrets.compare_digest(
        current_username_bytes, correct_username_bytes
    )
    current_password_bytes = credentials.password.encode("utf8")
    correct_password_bytes = config.secret.token.encode("utf8")
    is_correct_password = secrets.compare_digest(
        current_password_bytes, correct_password_bytes
    )
    if not (is_correct_username and is_correct_password):
        logger.warning(f"收到广播请求，但密码或用户名错误：{credentials.username}:{credentials.password}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="密码错误",
            headers={"WWW-Authenticate": "Basic"},
        )
    return f"{credentials.username}:{credentials.password}"


def reset_statistic():
    global statistic
    statistic = {
        "weather_error": 0,  # 天气 API 响应错误次数（不含重试次数）
        "websocket_disconnect": {}  # WebSocket 连接异常断开次数
    }


@asynccontextmanager
async def lifespan(_: FastAPI):
    logger.add(
        config.log.file,
        level=config.log.level,
        rotation=config.log.rotation,
        retention=config.log.retention
    )
    logger.info("程序加载中：添加定时任务 (1/3)")
    scheduler.add_job(reset_statistic, "cron", hour=0, minute=0)
    logger.info("程序加载中：启动定时任务 (2/3)")
    scheduler.start()
    logger.info("程序加载中：寻找工作目录 (3/3)")
    if not pathlib.Path("./data/").exists():
        pathlib.Path("./data/").mkdir()
    logger.success(
        """\
        FastClassSchedule 启动成功
        ______        _    _____ _                _____      _              _       _      
        |  ____|      | |  / ____| |              / ____|    | |            | |     | |     
        | |__ __ _ ___| |_| |    | | __ _ ___ ___| (___   ___| |__   ___  __| |_   _| | ___ 
        |  __/ _` / __| __| |    | |/ _` / __/ __|\___ \ / __| '_ \ / _ \/ _` | | | | |/ _ \\
        | | | (_| \__ \ |_| |____| | (_| \__ \__ \____) | (__| | | |  __/ (_| | |_| | |  __/
        |_|  \__,_|___/\__|\_____|_|\__,_|___/___/_____/ \___|_| |_|\___|\__,_|\__,_|_|\___|
        """
    )
    yield
    scheduler.shutdown()


origins = config.server.domain
app = FastAPI(lifespan=lifespan)
# noinspection PyTypeChecker
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/", response_class=ORJSONResponse)
async def root():
    return ORJSONResponse({"message": "Hello World"})


@app.get("/api/weather/{province}/{name}", response_class=ORJSONResponse)
@app.get("/api/weather/{name}", response_class=ORJSONResponse)
async def weather_province_name(name: str, province: str = None):
    """
    获取指定城市的对应信息（当存在不同省份同名城市时使用）
    :param name: 城市名称
    :param province: 省份名称
    :return: 温度与天气
    """
    for _ in range(5):
        try:
            resp = await weather.weather_lookup_by_name(
                name=name,
                adm=province,
                key=config.apikey.weather
            )
            logger.info(f"获取 {province}/{name} 的天气信息，T: {resp['now']['temp']}, W: {resp['now']['text']}")
            return ORJSONResponse({"temp": resp['now']['temp'], "weat": resp['now']['text']})
        except KeyError:
            logger.error(f"不存在 {province}/{name} ")
            return ORJSONResponse({"temp": 404, "weat": "不存在"})
        except Exception as err:
            logger.exception(f"获取天气信息失败: {err}", exc_info=True)
    statistic['weather_error'] += 1
    logger.error(f"获取 {province}/{name} 的天气信息失败，超过最大重试次数")
    raise HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail="获取天气信息失败，超过最大重试次数，可能是上游服务器异常，或是本服务器存在网络波动"
    )


@app.get("/{school}/{grade}/{class_number}", response_class=ORJSONResponse)
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

@app.websocket("/ws/{school}/{grade}/{class_number}")
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
                statistic["websocket_disconnect"][f'{school}_{grade}_{class_number}'] += 1
            except KeyError:
                statistic["websocket_disconnect"][f'{school}_{grade}_{class_number}'] = 1
            logger.warning(
                f"现在 {school} 学校 {grade} 级 {class_number} 班还未放学，但连接异常断开，"
                f"本班级今日已异常断开 {statistic['websocket_disconnect'][f'{school}_{grade}_{class_number}']} 次"
            )
        websocket_clients[(school, grade)].disconnect(websocket)
        logger.info(f"来自 {school} 学校 {grade} 级 {class_number} 班的 WebSocket 连接断开")
        if not websocket_clients[(school, grade)].active_connections:
            del websocket_clients[(school, grade)]
            logger.info(f"现在 {school} 学校 {grade} 级没有存活的 WebSocket 连接，已清除该连接管理器")


@app.post("/api/broadcast/{school}/{grade}/{class_number}")
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


@app.get("/api/statistic", response_class=ORJSONResponse)
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
            **websocket_clients_list
        }
    )


if __name__ == '__main__':
    uvicorn.run(app, host=config.server.host, port=config.server.port)

