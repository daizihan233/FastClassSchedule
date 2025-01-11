import datetime

import httpx
from loguru import logger


async def get_from_jenkins(url: str, filename: str) -> dict[str, str]:
    logger.debug(f"GET {url}/lastSuccessfulBuild/api/json")
    async with httpx.AsyncClient() as client:
        resp = (await client.get(f"{url}/lastSuccessfulBuild/api/json")).json()
    build_date = datetime.date.fromtimestamp(resp["timestamp"] // 1000).strftime("%Y%m%d")
    logger.info(f"Last successful build date: {build_date}")
    return {
        "build_date": build_date,
        "url": f"{url}/lastSuccessfulBuild/artifact/{filename}"
    }
