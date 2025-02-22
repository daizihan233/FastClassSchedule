import pathlib
from contextlib import asynccontextmanager

import uvicorn
from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse
from loguru import logger

from routers.client import schedule, update, weather
from routers.web import statistic
from utils.config import config

scheduler = BackgroundScheduler()

@asynccontextmanager
async def lifespan(_: FastAPI):
    logger.add(
        config.log.file,
        level=config.log.level,
        rotation=config.log.rotation,
        retention=config.log.retention
    )
    logger.info("程序加载中：添加定时任务 (1/3)")
    scheduler.add_job(statistic.reset_statistic, "cron", hour=0, minute=0)
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

app = FastAPI(lifespan=lifespan)
# noinspection PyTypeChecker
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.server.domain,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(schedule.router)
app.include_router(update.router)
app.include_router(weather.router)
app.include_router(statistic.router)

@app.get("/", response_class=ORJSONResponse)
async def root():
    return ORJSONResponse({"message": "Hello World"})


if __name__ == '__main__':
    uvicorn.run(app, host=config.server.host, port=config.server.port)

