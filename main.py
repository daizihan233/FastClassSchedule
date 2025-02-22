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
    logger.info("程序加载中：添加定时任务 (7/9)")
    scheduler.add_job(statistic.reset_statistic, "cron", hour=0, minute=0)
    logger.info("程序加载中：启动定时任务 (8/9)")
    scheduler.start()
    logger.info("程序加载中：设置工作目录 (9/9)")
    pathlib.Path("./data/").mkdir(parents=True, exist_ok=True)
    logger.success(
        r"""
        FastClassSchedule 加载成功
        ______        _    _____ _                _____      _              _       _      
        |  ____|      | |  / ____| |              / ____|    | |            | |     | |     
        | |__ __ _ ___| |_| |    | | __ _ ___ ___| (___   ___| |__   ___  __| |_   _| | ___ 
        |  __/ _` / __| __| |    | |/ _` / __/ __|\___ \ / __| '_ \ / _ \/ _` | | | | |/ _ \
        | | | (_| \__ \ |_| |____| | (_| \__ \__ \____) | (__| | | |  __/ (_| | |_| | |  __/
        |_|  \__,_|___/\__|\_____|_|\__,_|___/___/_____/ \___|_| |_|\___|\__,_|\__,_|_|\___|
        """
    )
    yield
    logger.info("程序关闭中：关闭定时任务 (1/1)")
    scheduler.shutdown()
    logger.success(
        r"""
        FastClassSchedule 即将关闭
        ______        _    _____ _                _____      _              _       _      
        |  ____|      | |  / ____| |              / ____|    | |            | |     | |     
        | |__ __ _ ___| |_| |    | | __ _ ___ ___| (___   ___| |__   ___  __| |_   _| | ___ 
        |  __/ _` / __| __| |    | |/ _` / __/ __|\___ \ / __| '_ \ / _ \/ _` | | | | |/ _ \
        | | | (_| \__ \ |_| |____| | (_| \__ \__ \____) | (__| | | |  __/ (_| | |_| | |  __/
        |_|  \__,_|___/\__|\_____|_|\__,_|___/___/_____/ \___|_| |_|\___|\__,_|\__,_|_|\___|
        """
    )

logger.info("程序加载中：初始化 FastAPI (1/9)")
app = FastAPI(lifespan=lifespan)
logger.info("程序加载中：设置跨域 (2/9)")
# noinspection PyTypeChecker
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.server.domain,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
logger.info("程序加载中：导入课程表相关 API (3/9)")
app.include_router(schedule.router)
logger.info("程序加载中：导入更新相关 API (4/9)")
app.include_router(update.router)
logger.info("程序加载中：导入天气相关 API (5/9)")
app.include_router(weather.router)
logger.info("程序加载中：导入统计相关 API (6/9)")
app.include_router(statistic.router)

@app.get("/", response_class=ORJSONResponse)
async def root():
    return ORJSONResponse({"message": "Hello World"})


if __name__ == '__main__':
    uvicorn.run(app, host=config.server.host, port=config.server.port)

