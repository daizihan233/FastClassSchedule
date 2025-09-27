from fastapi import APIRouter, HTTPException, status
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
            resp = await weather.weather_lookup_by_name(
                name=name,
                adm=province,
                host=config.apikey.apihost,
                key=config.apikey.weather
            )
            warn_resp = await weather.weather_warning_lookup_by_name(
                name=name,
                adm=province,
                host=config.apikey.apihost,
                key=config.apikey.weather
            )
            warn = '；'.join([x['text'] for x in warn_resp['warning']]).replace('\n', '')
            brief_warn = '；'.join([x['title'] for x in warn_resp['warning']]).replace('\n', '')
            temp = resp['now']['temp']
            weat = resp['now']['text']
            logger.info(f"获取 {province}/{name} 的天气信息，T: {temp}, W: {weat}, Warning: {warn}, Brief: {brief_warn}")
            return ORJSONResponse({"temp": temp, "weat": weat, 'warn': warn, 'brief_warn': brief_warn})
        except KeyError:
            logger.error(f"不存在 {province}/{name} ")
            return ORJSONResponse({"temp": 404, "weat": "不存在", "warning": '', 'brief_warn': ''}, status_code=status.HTTP_404_NOT_FOUND)
        except Exception as err:
            logger.exception(f"获取天气信息失败: {err}", exc_info=True)
    statistic['weather_error'] += 1
    logger.error(f"获取 {province}/{name} 的天气信息失败，超过最大重试次数")
    raise HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail="获取天气信息失败，超过最大重试次数，可能是上游服务器异常，或是本服务器存在网络波动"
    )