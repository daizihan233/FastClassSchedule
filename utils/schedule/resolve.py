from loguru import logger

from utils.calc import weeks, from_str_to_date

# 新增导入
import datetime
import json
from typing import Optional, Dict, Any
from utils.db import fetch_records
from utils.schedule.dataclasses import AutorunType
import copy


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


async def resolve_compensation(schedule: dict) -> dict:
    """
    应用“调休自动任务”：当今日等于某条调休规则的 date 时，将今日的日课表替换为 useDate 所在星期的配置。
    规则来源：utils.db.records 表中 etype=0 的记录；优先级按 level 降序（fetch_records 已排序）。
    """
    today = datetime.date.today()
    rows = fetch_records()
    if not rows:
        return schedule

    # 选择第一条今日生效或直接命中的调休规则
    chosen_rule: Optional[Dict[str, Any]] = None
    for r in rows:
        try:
            if int(r.get('etype')) != int(AutorunType.COMPENSATION):
                continue
            params_text = r.get('parameters')
            params = json.loads(params_text) if isinstance(params_text, str) else (params_text or {})
            rule = params.get('rule') if isinstance(params.get('rule'), dict) else params
            d = datetime.date.fromisoformat(str(rule.get('date')))
            if d != today:
                continue
            chosen_rule = rule
            break
        except Exception:
            continue

    if not chosen_rule:
        return schedule

    try:
        use_date = datetime.date.fromisoformat(str(chosen_rule.get('useDate')))
    except Exception as e:
        logger.warning(f"调休规则 useDate 无效，忽略：{e}")
        return schedule

    # daily_class 索引：项目中周日索引为 0，周一为 1，... 周六为 6
    today_idx = today.isoweekday() % 7
    src_idx = use_date.isoweekday() % 7

    try:
        new_schedule = copy.deepcopy(schedule)
        # 替换今日的课表和作息引用
        new_schedule['daily_class'][today_idx]['classList'] = copy.deepcopy(
            schedule['daily_class'][src_idx]['classList']
        )
        if 'timetable' in schedule['daily_class'][src_idx]:
            new_schedule['daily_class'][today_idx]['timetable'] = schedule['daily_class'][src_idx]['timetable']
        logger.info(
            f"应用调休：{today.isoformat()} 使用 {use_date.isoformat()} 的课表 (src_idx={src_idx} -> today_idx={today_idx})"
        )
        return new_schedule
    except Exception as e:
        logger.error(f"应用调休失败：{e}")
        return schedule
