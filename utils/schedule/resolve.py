from loguru import logger

from utils.calc import weeks, from_str_to_date

# 新增导入
import datetime
import json
from typing import Optional, Dict, Any, List, Tuple
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
    # fetch_records 返回的 scope 是 JSON 字符串（或已解码），需要容错
    scopes: List[str] = []
    if isinstance(scopes_raw, list):
        scopes = [str(x) for x in scopes_raw]
    elif isinstance(scopes_raw, str):
        try:
            parsed = json.loads(scopes_raw)
            if isinstance(parsed, list):
                scopes = [str(x) for x in parsed]
            else:
                # 兼容非列表的历史数据，按单个作用域处理
                scopes = [str(scopes_raw)]
        except Exception:
            scopes = [str(scopes_raw)]
    else:
        # 兜底：无 scope 时视为不匹配
        return -1

    best = -1
    for s in scopes:
        spec = _scope_specificity(s, school, grade, class_number)
        if spec > best:
            best = spec
    return best


async def resolve_compensation(schedule: dict, *, school: str, grade: int | str, class_number: int | str) -> dict:
    """
    应用“调休自动任务”：当今日等于某条调休规则的 date 时，将今日的日课表替换为 useDate 所在星期的配置。
    多条规则同时生效时，全部处理；若发生冲突，使用优先级(level)更大的规则；若优先级相同，选择作用域更小（特异度更大）的规则。
    :param schedule: 合并后的课表数据
    :param school: 学校标识（字符串）
    :param grade: 年级
    :param class_number: 班级
    :return: 应用调休规则后的课表
    """
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
                # 该记录的作用域与当前上下文不匹配
                continue
            level = int(r.get('level', 0) or 0)
            candidates.append((level, spec, r, rule))
        except Exception:
            # 忽略损坏记录
            continue

    if not candidates:
        return schedule

    # 为满足“全部处理+冲突按优先级/特异度解决”，我们按 (level ASC, specificity ASC) 顺序依次应用；
    # 因此越高优先级、越具体的规则会在最后覆盖之前的结果。
    candidates.sort(key=lambda x: (x[0], x[1]))

    new_schedule = copy.deepcopy(schedule)
    today_idx = today.isoweekday() % 7
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
