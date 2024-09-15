import aiohttp


async def city_lookup(name, key, adm=None):
    """
    查找某个城市的城市 ID
    :param name: 城市名称
    :param key: APIKEY
    :param adm: 省份名称
    :return: 城市 ID
    """
    async with aiohttp.ClientSession() as session:
        async with session.get(
                f"https://geoapi.qweather.com/v2/city/lookup?"
                f"location={name}&"
                f"key={key}" + (f"&adm={adm}" if adm else "")
        ) as response:
            return (await response.json())["location"][0]["id"]


async def weather_lookup(location, key):
    """
    查找某个城市的天气预报
    :param location: 城市 ID
    :param key: APIKEY
    :return: API 所返回的 JSON 数据
    """
    async with (aiohttp.ClientSession() as session):
        async with session.get(
                f"https://devapi.qweather.com/v7/weather/now?"
                f"location={location}&"
                f"key={key}"
        ) as response:
            return await response.json()

async def weather_lookup_by_name(name, key, adm=None):
    """
    根据城市名称查找天气预报
    :param name: 城市名称
    :param key: APIKEY
    :param adm: 省份名称
    :return: API 所返回的 JSON 数据
    """
    return await weather_lookup(
        location=await city_lookup(name, key, adm),
        key=key
    )