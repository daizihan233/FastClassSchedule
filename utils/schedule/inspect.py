import asyncio


def _check_duplicate_subject(schedule: dict) -> tuple[bool, str]:
    dr: list = list(set(schedule['subject_name'].keys()))
    dt: list = list(schedule['subject_name'].keys())
    for i in dr:
        dt.remove(i)
    if len(dt) != 0:
        return True, '存在重复的课程：' + str(dt)
    return False, ""


async def check_duplicate_subject(schedule: dict) -> tuple[bool, str]:
    """
    检查是否存在重复的课程
    :param schedule: 课表（不一定需要完整课表，但一定要有 subject_name 字段）
    :return: 一个 tuple，第一个元素 True 表示存在问题，False 表示不存在问题；第二个元素为问题描述，不存在问题时为空字符串
    """
    return await asyncio.to_thread(
        _check_duplicate_subject, schedule
    )
