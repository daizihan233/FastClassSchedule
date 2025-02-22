import pathlib
import typing
from dataclasses import dataclass

import toml
from loguru import logger


@dataclass
class ApiKey:
    weather: str

@dataclass
class Secret:
    token: str

@dataclass
class Server:
    host: str
    port: int
    domain: list[str]

@dataclass
class Log:
    level: typing.Literal["TRACE", "DEBUG", "SUCCESS", "WARNING", "ERROR", "CRITICAL"]
    file: str
    rotation: str
    retention: str

@dataclass
class CI:
    kind: typing.Literal["jenkins"]
    url: str
    filename: str

@dataclass
class Config:
    apikey: ApiKey
    secret: Secret
    server: Server
    log: Log
    ci: CI

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

[ci]
kind = "jenkins"
url = "https://example.com/job/ElectronClassSchedule"
filename = "release.zip"
"""

CONFIG_PATH = "config.toml"
if not pathlib.Path(CONFIG_PATH).exists():
    pathlib.Path(CONFIG_PATH).touch()
    pathlib.Path(CONFIG_PATH).write_text(DEFAULT_CONFIG)
    logger.error("配置文件已生成，请填写相关配置再运行")
    exit(1)
CONFIG_JSON = toml.load(CONFIG_PATH)
try:
    config = Config(
        apikey=ApiKey(**CONFIG_JSON["apikey"]),
        secret=Secret(**CONFIG_JSON["secret"]),
        server=Server(**CONFIG_JSON["server"]),
        log=Log(**CONFIG_JSON["log"]),
        ci=CI(**CONFIG_JSON["ci"])
    )
except TypeError as e:
    logger.exception(
        f"配置文件可能缺少或存在过多字段，这可能是由于升级所致，您也可以删除并重新生成配置文件：{e}",
        exc_info=True
    )
    exit(1)
del DEFAULT_CONFIG, CONFIG_PATH, CONFIG_JSON