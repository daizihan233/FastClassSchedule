from functools import lru_cache

import aiohttp
from loguru import logger

cache = {}

async def city_lookup(name, key, host, adm=None):
    """
    查找某个城市的城市 ID
    :param host: API Host
    :param name: 城市名称
    :param key: APIKEY
    :param adm: 省份名称
    :return: 城市 ID
    """
    if (name, adm) in cache:
        logger.info(f"Cache hit: {name = }, {adm = } -> {cache[(name, adm)]}")
        return cache[(name, adm)]
    async with aiohttp.ClientSession() as session:
        async with session.get(
                f"https://{host}/geo/v2/city/lookup?"
                f"location={name}&" + (f"&adm={adm}" if adm else ""),
                headers={
                    'X-QW-Api-Key': key
                }
        ) as response:
            cache[(name, adm)] = (await response.json())["location"][0]["id"]
            return cache[(name, adm)]


async def weather_lookup(location, key, host):
    """
    查找某个城市的天气预报
    :param host: API Host
    :param location: 城市 ID
    :param key: APIKEY
    :return: API 所返回的 JSON 数据
    """
    async with (aiohttp.ClientSession() as session):
        async with session.get(
            f"https://{host}/v7/weather/now?"
            f"location={location}",
            headers={
                'X-QW-Api-Key': key
            }
        ) as response:
            return await response.json()


async def weather_warning_lookup(location, key, host):
    """
    查找某个城市的天气预警
    :param host: API Host
    :param location: 城市 ID
    :param key: APIKEY
    :return: API 所返回的 JSON 数据
    """
    async with (aiohttp.ClientSession() as session):
        async with session.get(
            f"https://{host}/v7/warning/now?"
            f"location={location}",
            headers={
                'X-QW-Api-Key': key
            }
        ) as response:
            return await response.json()

async def weather_lookup_by_name(name, key, host, adm=None):
    """
    根据城市名称查找天气预报
    :param host: API Host
    :param name: 城市名称
    :param key: APIKEY
    :param adm: 省份名称
    :return: API 所返回的 JSON 数据
    """
    return await weather_lookup(
        location=await city_lookup(name, key, host, adm),
        host=host,
        key=key
    )


async def weather_warning_lookup_by_name(name, key, host, adm=None):
    """
    根据城市名称查找天气预警
    :param host: API Host
    :param name: 城市名称
    :param key: APIKEY
    :param adm: 省份名称
    :return: API 所返回的 JSON 数据
    """
    return await weather_warning_lookup(
        location=await city_lookup(name, key, host, adm),
        host=host,
        key=key
    )