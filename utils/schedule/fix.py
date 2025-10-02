from loguru import logger
import asyncio


def _fix_wrong_timetable_sync(schedule: dict) -> dict:
    """
    同步实现：处理错误的作息表
    """
    result = schedule.copy()
    dic = {
        x: max([v for v in result['timetable'][x].values() if isinstance(v, int)]) + 1
        for x in result['timetable'].keys()
    }
    for index, item in enumerate(result['daily_class']):
        if len(item['classList']) != dic[item['timetable']]:
            logger.warning(f"{item['Chinese']} 与当天的作息（{item['timetable']}）安排不符，尝试自动修复")
            # 如果多了则去除，如果少了则补充
            if len(item['classList']) > dic[item['timetable']]:
                result['daily_class'][index]['classList'] = item['classList'][:dic[item['timetable']]]
            else:
                result['daily_class'][index]['classList'].extend(['课'] * (dic[item['timetable']] - len(item['classList'])))
    return result


async def fix_wrong_timetable(schedule: dict) -> dict:
    """
    处理错误的作息表（异步包装：在线程池中执行以避免阻塞事件循环）
    :param schedule: 课表原始数据
    :return: 处理后的课表数据
    """
    return await asyncio.to_thread(_fix_wrong_timetable_sync, schedule)
