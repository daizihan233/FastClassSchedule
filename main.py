import json
import pathlib
import secrets
from typing import Annotated

import toml
import uvicorn
from fastapi import FastAPI, HTTPException, status, Depends
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from loguru import logger

from utils import config as utils_config
from utils import weather

app = FastAPI()
security = HTTPBasic()

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
logger.add(
    config.log.file,
    level=config.log.level,
    rotation=config.log.rotation,
    retention=config.log.retention
)

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

def get_current_username(
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
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"status": 401, "message": "Incorrect password"},
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username

@app.get("/")
async def root():
    return {"message": "Hello World"}


@app.get("/api/weather/{province}/{name}")
@app.get("/api/weather/{name}")
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
            return {"temp": resp['now']['temp'], "weat": resp['now']['text']}
        except KeyError:
            logger.error(f"不存在 {province}/{name} ")
            return {"temp": 404, "weat": "不存在"}
        except Exception as err:
            logger.exception(f"获取天气信息失败: {err}", exc_info=True)
    logger.error(f"获取 {province}/{name} 的天气信息失败，超过最大重试次数")
    raise HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail={"temp": 502, "weat": "异常"}
    )


@app.get("/{school}/{grade}/{class_number}")
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
    return {
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



if __name__ == '__main__':
    uvicorn.run(app, host=config.server.host, port=config.server.port)


