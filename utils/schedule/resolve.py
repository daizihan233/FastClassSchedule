import asyncio
import copy
# 新增导入
import datetime
import json
from typing import Dict, Any, List, Tuple

from loguru import logger

from utils.calc import weeks, from_str_to_date
from utils.db import fetch_records
from utils.schedule.dataclasses import AutorunType


def _resolve_week_cycle_sync(schedule: dict) -> dict:
    """
    同步实现：处理单双周逻辑
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


async def resolve_week_cycle(schedule: dict) -> dict:
    """
    处理单双周的逻辑（异步包装：在线程池中执行以避免阻塞事件循环）
    :param schedule: 课表原始数据
    :return: 处理后的课表数据
    """
    return await asyncio.to_thread(_resolve_week_cycle_sync, schedule)


def _prepare_compensation_context(schedule, school, grade, class_number):
    today = datetime.date.today()
    rows = fetch_records()
    if not rows:
        return schedule

    # 收集所有“今天”生效，且与当前 (school/grade/class) 匹配的规则
    candidates: List[Tuple[int, int, Dict[str, Any], Dict[str, Any]]] = []  # (level, specificity, row, rule)
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
            spec = _row_applicable_specificity(r, school, grade, class_number)
            if spec < 0:
                continue
            level = int(r.get('level', 0) or 0)
            candidates.append((level, spec, r, rule))
        except Exception:
            continue

    if not candidates:
        return schedule

    candidates.sort(key=lambda x: (x[0], x[1]))

    new_schedule = copy.deepcopy(schedule)
    today_idx = today.isoweekday() % 7
    return today, today_idx, candidates, new_schedule


def _resolve_compensation_sync(schedule: dict, school: str, grade: int | str, class_number: int | str) -> dict:
    """
    同步实现：应用“调休自动任务”。
    """
    today, today_idx, candidates, new_schedule = _prepare_compensation_context(schedule, school, grade, class_number)
    for level, spec, _row, rule in candidates:
        try:
            use_date = datetime.date.fromisoformat(str(rule.get('useDate')))
        except Exception as e:
            logger.warning(f"调休规则 useDate 无效，忽略该条：{e}")
            continue
        src_idx = use_date.isoweekday() % 7
        try:
            new_schedule['daily_class'][today_idx]['classList'] = copy.deepcopy(
                new_schedule['daily_class'][src_idx]['classList']
            )
            if 'timetable' in new_schedule['daily_class'][src_idx]:
                new_schedule['daily_class'][today_idx]['timetable'] = new_schedule['daily_class'][src_idx]['timetable']
            logger.info(
                f"应用调休：{today.isoformat()} 使用 {use_date.isoformat()} 的课表 (src_idx={src_idx} -> today_idx={today_idx}) | "
                f"level={level}, specificity={spec}"
            )
        except Exception as e:
            logger.error(f"应用调休失败(跳过该条)：{e}")
            continue

    return new_schedule


# 作用域匹配与“更小作用域”判定：返回匹配到的最大特异度（段数），不匹配返回 -1
# ALL -> 0；"39" -> 1；"39/2023" -> 2；"39/2023/1" -> 3
def _scope_specificity(scope_entry: str, school: str, grade: int | str, class_number: int | str) -> int:
    try:
        s = str(scope_entry).strip()
    except Exception:
        return -1
    if not s:
        return -1
    if s.upper() == 'ALL':
        return 0
    parts = s.split('/')
    ctx = [str(school), str(grade), str(class_number)]
    if len(parts) > len(ctx):
        return -1
    for idx, p in enumerate(parts):
        if p != ctx[idx]:
            return -1
    return len(parts)


def _row_applicable_specificity(row: Dict[str, Any], school: str, grade: int | str, class_number: int | str) -> int:
    scopes_raw = row.get('scope')
    if isinstance(scopes_raw, list):
        scopes = [str(x) for x in scopes_raw]
    elif isinstance(scopes_raw, str):
        try:
            parsed = json.loads(scopes_raw)
            if isinstance(parsed, list):
                scopes = [str(x) for x in parsed]
            else:
                scopes = [str(scopes_raw)]
        except Exception as err:
            logger.error(err)
            scopes = [str(scopes_raw)]
    else:
        return -1

    best = -1
    for s in scopes:
        spec = _scope_specificity(s, school, grade, class_number)
        if spec > best:
            best = spec
    return best


async def resolve_compensation(schedule: dict, *, school: str, grade: int | str, class_number: int | str) -> dict:
    """
    应用“调休自动任务”——异步包装：在线程池中执行以避免阻塞事件循环
    :param schedule: 合并后的课表数据
    :param school: 学校标识（字符串）
    :param grade: 年级
    :param class_number: 班级
    :return: 应用调休规则后的课表
    """
    return await asyncio.to_thread(
        _resolve_compensation_sync, schedule, school=school, grade=grade, class_number=class_number
    )

# 新增：作息表调整解析

def _resolve_timetable_sync(schedule: dict, *, school: str, grade: int | str, class_number: int | str) -> dict:
    """
    同步实现：应用“作息表调整自动任务”。在规则 date 当天，将当日的 daily_class.timetable 设置为 timetableId。
    多条规则按 (level, specificity) 排序，后应用者覆盖先应用者。
    """
    today, today_idx, candidates, new_schedule = _prepare_compensation_context(schedule, school, grade, class_number)

    for level, spec, _row, rule in candidates:
        timetable_id = rule.get('timetableId')
        if not isinstance(timetable_id, str) or not timetable_id:
            logger.warning("作息表调整规则 timetableId 无效或为空，忽略该条")
            continue
        try:
            new_schedule['daily_class'][today_idx]['timetable'] = timetable_id
            logger.info(
                f"应用作息表调整：{today.isoformat()} 使用 timetable='{timetable_id}' | "
                f"level={level}, specificity={spec}"
            )
        except Exception as e:
            logger.error(f"应用作息表调整失败(跳过该条)：{e}")
            continue

    return new_schedule


async def resolve_timetable(schedule: dict, *, school: str, grade: int | str, class_number: int | str) -> dict:
    """
    应用“作息表调整自动任务”——异步包装：在线程池中执行以避免阻塞事件循环
    """
    return await asyncio.to_thread(
        _resolve_timetable_sync, schedule, school=school, grade=grade, class_number=class_number
    )
