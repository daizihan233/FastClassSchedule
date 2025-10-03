from loguru import logger
import asyncio
import re
import datetime
import copy
from utils.globalvar import default_config


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


def _ensure_default_shape_sync(schedule: dict) -> dict:
    """
    同步实现：检查配置是否与默认格式一致，并按需使用默认配置进行填充/替换（不改动本地文件）。
    规则：
    - 若每日课程长度不为 7（或类型不正确），则将 subject_name/timetable/divider/daily_class 全部替换为默认配置。
    - countdown_target 必须符合 YYYY-MM-DD 或为 'hidden'，否则替换为 'hidden'。
    - css_style 若缺失或不是字典，则替换为默认；若仅缺少部分键，则补齐缺失键。
    - 其他顶层配置项若缺失，则用默认值填充。
    """
    result = copy.deepcopy(schedule) if isinstance(schedule, dict) else {}

    # 1) 每日课程长度检查 -> 替换四大块
    need_replace_blocks = False
    daily = result.get('daily_class')
    if not isinstance(daily, list) or len(daily) != 7:
        need_replace_blocks = True
    if need_replace_blocks:
        for k in ('subject_name', 'timetable', 'divider', 'daily_class'):
            result[k] = copy.deepcopy(default_config[k])
        logger.warning("每日课程长度不是 7 天，已使用默认配置替换 subject_name/timetable/divider/daily_class")

    # 2) 倒计时目标
    ct = result.get('countdown_target', default_config.get('countdown_target'))
    valid = False
    if isinstance(ct, str):
        if ct.strip().lower() == 'hidden':
            valid = True
            ct = 'hidden'
        else:
            # 格式校验 + 合法日期校验
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", ct.strip() or ''):
                try:
                    datetime.date.fromisoformat(ct.strip())
                    valid = True
                except Exception:
                    valid = False
    if not valid:
        result['countdown_target'] = 'hidden'
        logger.warning("countdown_target 不合法，已替换为 'hidden'")
    else:
        result['countdown_target'] = ct

    # 3) css_style 填充
    css_default = default_config.get('css_style', {})
    css = result.get('css_style')
    if not isinstance(css, dict):
        result['css_style'] = copy.deepcopy(css_default)
        logger.warning("css_style 缺失或格式错误，已使用默认配置替换")
    else:
        missing_keys = [k for k in css_default.keys() if k not in css]
        if missing_keys:
            for k in missing_keys:
                css[k] = css_default[k]
            logger.warning(f"css_style 缺失以下键，已使用默认值填充: {', '.join(missing_keys)}")
        result['css_style'] = css

    # 4) 其他顶层缺失项填充（不覆盖已有值）
    for k, v in default_config.items():
        if k not in result:
            result[k] = copy.deepcopy(v)
            logger.warning(f"配置项 {k} 缺失，已使用默认值填充")

    return result


async def ensure_default_shape(schedule: dict) -> dict:
    """
    异步包装：在线程池中执行以避免阻塞事件循环
    """
    return await asyncio.to_thread(_ensure_default_shape_sync, schedule)


async def fix_wrong_timetable(schedule: dict) -> dict:
    """
    处理错误的作息表（异步包装：在线程池中执行以避免阻塞事件循环）
    :param schedule: 课表原始数据
    :return: 处理后的课表数据
    """
    return await asyncio.to_thread(_fix_wrong_timetable_sync, schedule)
