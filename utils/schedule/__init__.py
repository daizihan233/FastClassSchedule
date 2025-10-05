import asyncio

from utils.db import refresh_statuses
from . import resolve, fix


async def run_fix(schedule: dict) -> dict:
    """
    自动修复课表数据
    :param schedule: 课表原始数据
    :return: 修复完成后的数据
    """
    # 先按默认格式校验/填充，再修正作息与课时数不匹配
    s = await fix.ensure_default_shape(schedule)
    s = await fix.fix_wrong_timetable(s)
    return s

async def run_resolve(schedule: dict, *, school: str, grade: int | str, class_number: int | str) -> dict:
    """
    解析课表数据
    :param schedule: 课表原始数据
    :param school: 学校标识
    :param grade: 年级
    :param class_number: 班级
    :return: 解析完成后的数据
    """
    # 每次解析前刷新数据库状态，保证客户端拉取配置时状态最新
    await asyncio.to_thread(refresh_statuses)
    s = await resolve.resolve_week_cycle(schedule)
    s = await resolve.resolve_compensation(s, school=school, grade=grade, class_number=class_number)
    s = await resolve.resolve_timetable(s, school=school, grade=grade, class_number=class_number)
    # 新增：课程表调整与全部调整（按需覆盖）
    s = await resolve.resolve_schedule(s, school=school, grade=grade, class_number=class_number)
    s = await resolve.resolve_all(s, school=school, grade=grade, class_number=class_number)
    return s

async def run_all(schedule: dict, *, school: str, grade: int | str, class_number: int | str) -> dict:
    """
    执行所有的检查、自动修复、解析操作
    :param schedule: 课表原始数据
    :param school: 学校标识
    :param grade: 年级
    :param class_number: 班级
    :return: 处理完成后的数据
    """
    return await run_fix(
        await run_resolve(schedule, school=school, grade=grade, class_number=class_number)
    )
