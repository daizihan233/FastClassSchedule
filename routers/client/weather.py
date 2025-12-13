from typing import Annotated

from fastapi import APIRouter, HTTPException, status, Header
from fastapi.responses import ORJSONResponse
from loguru import logger

from routers.web.statistic import statistic
from utils import weather
from utils.config import config

router = APIRouter()


@router.get("/api/weather/{province}/{name}", response_class=ORJSONResponse)
@router.get("/api/weather/{name}", response_class=ORJSONResponse)
async def weather_province_name(name: str, province: str = None):
    """
    获取指定城市的对应信息（当存在不同省份同名城市时使用）
    :param name: 城市名称
    :param province: 省份名称
    :return: 温度与天气
    """
    for _ in range(5):
        try:
            location = (
                await weather.city_lookup(
                    name=name,
                    adm=province,
                    host=config.apikey.apihost,
                    key=config.apikey.weather,
                )
            )["name"]
            resp = await weather.weather_lookup_by_name(
                name=name,
                adm=province,
                host=config.apikey.apihost,
                key=config.apikey.weather,
            )
            warn_resp = await weather.weather_warning_lookup_by_name(
                name=name,
                adm=province,
                host=config.apikey.apihost,
                key=config.apikey.weather,
            )
            warn = "；".join([x["description"] for x in warn_resp["alerts"]]).replace(
                "\n", ""
            )
            brief_warn = "；".join(
                [x["headline"] for x in warn_resp["alerts"]]
            ).replace("\n", "")
            temp = resp["now"]["temp"]
            weat = resp["now"]["text"]
            wind = resp["now"]["windDir"]
            wind_power = resp["now"]["windScale"]
            logger.info(
                f"获取 {province}/{name}（{location}） 的天气信息，T: {temp}, W: {weat}, Warning: {warn}, "
                f"Brief: {brief_warn}, Wind: {wind} ({wind_power}级)"
            )
            return ORJSONResponse(
                {
                    "where": location,
                    "temp": temp,
                    "weat": weat,
                    "wind": wind,
                    "wind_power": wind_power,
                    "warn": warn,
                    "brief_warn": brief_warn,
                }
            )
        except KeyError:
            logger.error(f"不存在 {province}/{name} ")
            return ORJSONResponse(
                {"temp": 404, "weat": "不存在", "warning": "", "brief_warn": ""},
                status_code=status.HTTP_404_NOT_FOUND,
            )
        except Exception as err:
            logger.exception(f"获取天气信息失败: {err}", exc_info=True)
    statistic["weather_error"] += 1
    logger.error(f"获取 {province}/{name} 的天气信息失败，超过最大重试次数")
    raise HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail="获取天气信息失败，超过最大重试次数，可能是上游服务器异常，或是本服务器存在网络波动",
    )


@router.get("/api/weather/", response_class=ORJSONResponse)
async def weather_by_cf(
    cf_ipcity: Annotated[str | None, Header()] = None,
    cf_region: Annotated[str | None, Header()] = None,
):
    """
    通过请求来源获取对应城市的天气信息（通过 Cloudflare 请求头获取位置信息）
    :return: 温度与天气
    """
    # 从 Cloudflare 请求头获取位置信息
    if not cf_ipcity:
        logger.error("无法通过请求头获取城市信息")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="无法通过请求头获取城市信息，请确保请求经过 Cloudflare",
        )
    return await weather_province_name(name=cf_ipcity, province=cf_region or None)
