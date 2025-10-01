from . import resolve, fix
from utils.db import refresh_statuses

async def run_fix(schedule: dict) -> dict:
    """
    自动修复课表数据
    :param schedule: 课表原始数据
    :return: 修复完成后的数据
    """
    return await fix.fix_wrong_timetable(schedule)

async def run_resolve(schedule: dict) -> dict:
    """
    解析课表数据
    :param schedule: 课表原始数据
    :return: 解析完成后的数据
    """
    # 每次解析前刷新数据库状态，保证客户端拉取配置时状态最新
    refresh_statuses()
    s = await resolve.resolve_week_cycle(schedule)
    s = await resolve.resolve_compensation(s)
    return s

async def run_all(schedule: dict) -> dict:
    """
    执行所有的检查、自动修复、解析操作
    :param schedule: 课表原始数据
    :return: 处理完成后的数据
    """
    return await run_fix(
        await run_resolve(schedule)
    )
