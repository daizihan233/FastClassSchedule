from . import resolve

async def run_resolve(schedule: dict) -> dict:
    """
    解析课表数据
    :param schedule: 课表原始数据
    :return: 解析完成后的数据
    """
    return await resolve.resolve_week_cycle(schedule)

async def run_all(schedule: dict) -> dict:
    """
    执行所有的检查、自动修复、解析操作
    :param schedule: 课表原始数据
    :return: 处理完成后的数据
    """
    return await run_resolve(schedule)
