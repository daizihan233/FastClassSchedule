import asyncio
import copy
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


# -------------------------- Scope helpers --------------------------

def _scope_specificity(scope_entry: str, school: str, grade: int | str, class_number: int | str) -> int:
    """作用域匹配与“更小作用域”判定：返回匹配到的最大特异度（段数），不匹配返回 -1
    ALL -> 0；"39" -> 1；"39/2023" -> 2；"39/2023/1" -> 3
    """
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
            scopes = [str(x) for x in parsed] if isinstance(parsed, list) else [str(scopes_raw)]
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


def _decode_rule(params_text: Any) -> Dict[str, Any]:
    if isinstance(params_text, str) and params_text:
        try:
            parsed = json.loads(params_text)
        except Exception:
            parsed = None
    elif isinstance(params_text, dict):
        parsed = params_text
    else:
        parsed = None
    if isinstance(parsed, dict):
        rule = parsed.get('rule') if isinstance(parsed.get('rule'), dict) else parsed
        return rule if isinstance(rule, dict) else {}
    return {}


def _collect_applicable_candidates(
    rows: List[Dict[str, Any]], *, etype: int, school: str, grade: int | str, class_number: int | str,
    today: datetime.date
) -> List[Tuple[int, int, Dict[str, Any]]]:
    """
    从记录中收集“今天”生效且作用域匹配的候选规则，返回 (level, specificity, rule) 列表。
    """
    candidates: List[Tuple[int, int, Dict[str, Any]]] = []
    for r in rows:
        try:
            if int(r.get('etype')) != etype:
                continue
            rule = _decode_rule(r.get('parameters'))
            d = datetime.date.fromisoformat(str(rule.get('date')))
            if d != today:
                continue
            spec = _row_applicable_specificity(r, school, grade, class_number)
            if spec < 0:
                continue
            level = int(r.get('level', 0) or 0)
            candidates.append((level, spec, rule))
        except Exception:
            continue
    candidates.sort(key=lambda x: (x[0], x[1]))
    return candidates


def _resolve_compensation_sync(schedule: dict, *, school: str, grade: int | str, class_number: int | str) -> dict:
    """
    同步实现：应用“调休自动任务”。
    """
    today = datetime.date.today()
    rows = fetch_records()
    if not rows:
        return schedule

    candidates = _collect_applicable_candidates(
        rows, etype=int(AutorunType.COMPENSATION), school=school, grade=grade, class_number=class_number, today=today
    )
    if not candidates:
        return schedule

    new_schedule = copy.deepcopy(schedule)
    today_idx = today.isoweekday() % 7
    for level, spec, rule in candidates:
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


def _resolve_timetable_sync(schedule: dict, *, school: str, grade: int | str, class_number: int | str) -> dict:
    """
    同步实现：应用“作息表调整自动任务”。在规则 date 当天，将当日的 daily_class.timetable 设置为 timetableId。
    多条规则按 (level, specificity) 排序，后应用者覆盖先应用者。
    """
    today = datetime.date.today()
    rows = fetch_records()
    if not rows:
        return schedule

    candidates = _collect_applicable_candidates(
        rows, etype=int(AutorunType.TIMETABLE), school=school, grade=grade, class_number=class_number, today=today
    )
    if not candidates:
        return schedule

    new_schedule = copy.deepcopy(schedule)
    today_idx = today.isoweekday() % 7
    for level, spec, rule in candidates:
        timetable_id = rule.get('timetableId')
        if not isinstance(timetable_id, str) or not timetable_id:
            logger.warning("作息表调整规则 timetableId 无效或为空，忽略该条")
            continue
        try:
            new_schedule['daily_class'][today_idx]['timetable'] = timetable_id
            logger.info(
                f"应用作息表调整：{today.isoformat()} 使用 timetable='{timetable_id}' | level={level}, specificity={spec}"
            )
        except Exception as e:
            logger.error(f"应用作息表调整失败(跳过该条)：{e}")
            continue

    return new_schedule


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


async def resolve_timetable(schedule: dict, *, school: str, grade: int | str, class_number: int | str) -> dict:
    """
    应用“作息表调整自动任务”——异步包装：在线程池中执行以避免阻塞事件循环
    """
    return await asyncio.to_thread(
        _resolve_timetable_sync, schedule, school=school, grade=grade, class_number=class_number
    )
