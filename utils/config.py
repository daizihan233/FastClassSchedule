import typing
from dataclasses import dataclass


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