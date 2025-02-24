from loguru import logger

from utils.calc import weeks, from_str_to_date


async def resolve_week_cycle(schedule: dict) -> dict:
    """
    处理单双周的逻辑
    :param schedule: 课表原始数据
    :return: 处理后的课表数据
    """
    resp = schedule.copy()
    week = weeks(from_str_to_date(schedule['start']))
    for i, lst in enumerate(schedule['daily_class']):
        for j, item in enumerate(lst['classList']):
            if isinstance(item, list):
                resp['daily_class'][i]['classList'][j] = resp['daily_class'][i]['classList'][j][
                    (week - 1) % len(resp['daily_class'][i]['classList'][j])
                ]
                logger.debug(f"第 {week} 周 | {item} -> {resp['daily_class'][i]['classList'][j]}")
    return resp

