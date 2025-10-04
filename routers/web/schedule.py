import datetime
import json
import pathlib
from typing import List, Dict, Any, Optional, Tuple

from fastapi import APIRouter, HTTPException, Query
from loguru import logger

from utils.calc import weeks, from_str_to_date
from utils.db import fetch_records
from utils.schedule.dataclasses import AutorunType
from utils.schedule.helpers import (
    decode_rule,
    row_applicable_specificity,
    row_etype,
    row_level,
)

router = APIRouter()


def _parse_scope(scope: str) -> Tuple[str, Optional[int], Optional[int]]:
    s = (scope or '').strip()
    parts = s.split('/') if s else []
    if len(parts) < 2:
        raise ValueError('scope 需为 school/grade 或 school/grade/class')
    school = parts[0]
    try:
        grade = int(parts[1])
    except Exception:
        raise ValueError('grade 必须为数字')
    class_number: Optional[int] = None
    if len(parts) >= 3 and parts[2] != '':
        try:
            class_number = int(parts[2])
        except Exception:
            raise ValueError('class 必须为数字')
    return school, grade, class_number


def _build_candidate(row: Dict[str, Any], *, date_obj: datetime.date, school: str, grade: int,
                     class_number: Optional[int]) -> Optional[Tuple[int, int, int, Dict[str, Any]]]:
    """
    将一条记录转换为 (etype, level, specificity, rule) 候选，若不适用则返回 None。
    """
    etype = row_etype(row)
    if etype not in (int(AutorunType.COMPENSATION), int(AutorunType.TIMETABLE)):
        return None
    rule = decode_rule(row.get('parameters'))
    try:
        d = datetime.date.fromisoformat(str(rule.get('date')))
    except Exception:
        return None
    if d != date_obj:
        return None
    spec = row_applicable_specificity(row, school, grade, class_number)
    if spec < 0:
        return None
    level = row_level(row)
    return etype, level, spec, rule


def _collect_rules_for_date(date_obj: datetime.date, school: str, grade: int, class_number: Optional[int]) -> Dict[
    int, List[Tuple[int, int, Dict[str, Any]]]]:
    """按 etype -> [(level, specificity, rule)] 收集在指定 date 生效的规则"""
    rows = fetch_records()
    bucket: Dict[int, List[Tuple[int, int, Dict[str, Any]]]] = {0: [], 1: []}
    for r in rows:
        cand = _build_candidate(r, date_obj=date_obj, school=school, grade=grade, class_number=class_number)
        if cand is None:
            continue
        etype, level, spec, rule = cand
        bucket.setdefault(etype, []).append((level, spec, rule))
    # 排序
    for k in bucket.keys():
        bucket[k].sort(key=lambda x: (x[0], x[1]))
    return bucket


def _load_schedule_files(school: str, grade: int, class_number: int) -> Dict[str, Any]:
    base = pathlib.Path(f"./data/{school}/{grade}")
    cls = base / str(class_number)
    return {
        **json.loads((base / 'subjects.json').read_text(encoding='utf-8')),
        **json.loads((base / 'timetable.json').read_text(encoding='utf-8')),
        **json.loads((cls / 'config.json').read_text(encoding='utf-8')),
        **json.loads((cls / 'schedule.json').read_text(encoding='utf-8')),
    }


def _pick_week_item(item: Any, week_idx: int) -> Any:
    if isinstance(item, list) and item:
        return item[week_idx % len(item)]
    return item


def _compute_week_index(schedule: Dict[str, Any], date_obj: datetime.date) -> int:
    try:
        start = from_str_to_date(schedule.get('start'))
    except Exception:
        # 默认用当前周数 1
        return 0
    w = weeks(start, date_obj)
    return (w - 1) if w > 0 else 0


def _period_indices_for_timetable(schedule: Dict[str, Any], timetable_id: str) -> List[int]:
    try:
        entries = schedule['timetable'][timetable_id]
    except Exception:
        return []
    indices = sorted({int(v) for v in entries.values() if isinstance(v, int)})
    return indices


def _build_periods(schedule: Dict[str, Any], date_obj: datetime.date, school: str, grade: int, class_number: int) -> \
List[Dict[str, Any]]:
    # 1) week/day
    week_idx = _compute_week_index(schedule, date_obj)
    dow_idx = date_obj.isoweekday() % 7

    # 2) collect applicable autorun rules for this date/scope
    rules = _collect_rules_for_date(date_obj, school, grade, class_number)

    # 3) resolve source day for classes (compensation)
    src_dow_idx = dow_idx
    comp_rules = rules.get(int(AutorunType.COMPENSATION), [])
    for _level, _spec, rule in comp_rules:
        try:
            ud = datetime.date.fromisoformat(str(rule.get('useDate')))
            src_dow_idx = ud.isoweekday() % 7
        except Exception:
            continue

    # 4) resolve timetable id override
    # take initial timetable id from the (possibly compensated) source day, but it is applied to target day
    try:
        timetable_id = schedule['daily_class'][src_dow_idx]['timetable']
    except Exception:
        timetable_id = ''
    tt_rules = rules.get(int(AutorunType.TIMETABLE), [])
    for _level, _spec, rule in tt_rules:
        tid = rule.get('timetableId')
        if isinstance(tid, str) and tid:
            timetable_id = tid

    # 5) resolve subjects (use classList from compensated source day)
    try:
        class_list = schedule['daily_class'][src_dow_idx]['classList']
    except Exception:
        class_list = []
    # pick week-specific items
    w = week_idx
    resolved_subjects = [str(_pick_week_item(x, w)) for x in class_list]

    # 6) gather period indices from timetable and map to subjects
    indices = _period_indices_for_timetable(schedule, str(timetable_id))
    periods: List[Dict[str, Any]] = []
    for idx in indices:
        subject = resolved_subjects[idx] if idx < len(resolved_subjects) else ''
        periods.append({"no": idx + 1, "subject": subject})
    return periods


@router.get('/web/schedule/by-date')
def get_schedule_by_date(date: str = Query(..., description='YYYY-MM-DD'), scope: str = Query(...)):
    """
    根据日期与 scope 返回当日的课节列表。
    返回格式：{"data": {"periods": Array<{no:number, subject:string}>}}
    """
    try:
        date_obj = datetime.date.fromisoformat(date)
    except Exception:
        raise HTTPException(status_code=400, detail='无效的日期格式，应为 YYYY-MM-DD')
    try:
        school, grade, class_number = _parse_scope(scope)
        if class_number is None:
            raise ValueError('scope 需要包含班级，如 39/2023/1')
        schedule = _load_schedule_files(school, grade, class_number)
    except Exception as e:
        logger.warning(f"/web/schedule/by-date 解析失败: {e}")
        raise HTTPException(status_code=400, detail=f'无效的 scope 或配置缺失: {e}')

    periods = _build_periods(schedule, date_obj, school, grade, class_number)
    return {"data": {"periods": periods}}
