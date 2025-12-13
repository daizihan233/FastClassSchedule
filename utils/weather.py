import aiohttp
from loguru import logger

cache = {}


async def city_lookup(name, key, host, adm=None) -> dict:
    """
    查找某个城市的城市 ID
    :param host: API Host
    :param name: 城市名称
    :param key: APIKEY
    :param adm: 省份名称
    :return: 城市 ID
    """
    if (name, adm) in cache:
        logger.info(
            f"Cache hit: {name = }, {adm = } -> {cache[(name, adm)]} | lat: {cache[(name, adm)]['lat']}, "
            f"lon: {cache[(name, adm)]['lon']}"
        )
        return cache[(name, adm)]
    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"https://{host}/geo/v2/city/lookup?"
            f"location={name}&" + (f"&adm={adm}" if adm else ""),
            headers={"X-QW-Api-Key": key},
        ) as response:
            cache[(name, adm)] = {
                "id": (await response.json())["location"][0]["id"],
                "lat": (await response.json())["location"][0]["lat"],
                "lon": (await response.json())["location"][0]["lon"],
                "name": (await response.json())["location"][0]["name"],
            }
            return cache[(name, adm)]


async def weather_lookup(location, key, host):
    """
    查找某个城市的天气预报
    :param host: API Host
    :param location: 城市 ID
    :param key: APIKEY
    :return: API 所返回的 JSON 数据
    """
    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"https://{host}/v7/weather/now?location={location}",
            headers={"X-QW-Api-Key": key},
        ) as response:
            return await response.json()


async def weather_warning_lookup(lat, lon, key, host):
    """
    查找某个城市的天气预警
    :param lat: 所需位置的纬度
    :param lon: 所需位置的经度
    :param host: API Host
    :param key: APIKEY
    :return: API 所返回的 JSON 数据
    """
    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"https://{host}/weatheralert/v1/current/{lat}/{lon}",
            headers={"X-QW-Api-Key": key},
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
        location=(await city_lookup(name, key, host, adm))["id"], host=host, key=key
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
    _, lat, lon, _ = (await city_lookup(name, key, host, adm)).values()
    return await weather_warning_lookup(lat=lat, lon=lon, host=host, key=key)
