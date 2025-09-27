import datetime
from functools import lru_cache
from typing import Optional, List, Tuple, Dict

import chinese_calendar


def from_str_to_date(date_str: str, format_str: str = '%Y-%m-%d') -> datetime.date:
    """
    将一个字符串转换为日期对象
    :param date_str: 日期，如 2025-03-14
    :param format_str: 字符串格式，默认为 '%Y-%m-%d'，如 '2025-03-14'
    :return: 一个日期对象
    """
    return datetime.datetime.strptime(date_str, format_str).date()

def weeks(start_date: datetime.date, end_date: datetime.date = datetime.date.today()) -> int:
    """
    计算从 start_date 到当前日期的周数
    :param start_date: 起始日期
    :param end_date: 结束日期，默认为今天
    :return: 周数（按自然周计算，也就是即使开始日期是周日，结束日期是下周一，也会计算为第 2 周）
    """
    return (
        (
            (end_date + datetime.timedelta(days=7 - end_date.isoweekday())) -
            (start_date - datetime.timedelta(days=start_date.isoweekday()))
        ).days
    ) // 7


def compensation_from_holiday(date: datetime.date) -> Optional[datetime.date]:
    """
    输入：某个节假日日期 date
    行为：若该日是调休休息日（in-lieu holiday），返回对应的补班日；否则返回 None。
    """
    if not chinese_calendar.is_in_lieu(date):
        return None
    return _holiday_to_workday_map(date.year).get(date)


def compensation_from_workday(workday: datetime.date) -> Optional[datetime.date]:
    """
    输入：某个被调休成为补班日的日期 workday
    行为：若该日是补班日（法定工作日中的“被调休工作日”），返回其对应的调休节假日；否则返回 None。
    """
    # chinese_calendar.workdays 中仅包含被调整为工作日的周末/节假日
    if workday not in chinese_calendar.workdays:
        return None
    return _workday_to_holiday_map(workday.year).get(workday)


def compensation_pairs(year: int) -> List[Tuple[datetime.date, datetime.date]]:
    """
    输入：年份 year
    输出：该年所有 (调休休息日 -> 补班日) 的配对列表，按日期升序。
    """
    mapping = _holiday_to_workday_map(year)
    return sorted(mapping.items(), key=lambda p: (p[0], p[1]))


@lru_cache(maxsize=16)
def _holiday_to_workday_map(year: int) -> Dict[datetime.date, datetime.date]:
    """
    构建指定年份的映射：调休休息日(holiday 且 in_lieu) -> 对应补班日(workday)。
    规则：按 chinese_calendar 中的 detail 归组；组内分别对“调休休息日”和“补班日”排序后按序配对；zip 最短长度保证稳健。
    """
    # detail -> list[workday]
    detail_to_workdays: Dict[object, List[datetime.date]] = {}
    for d, detail in chinese_calendar.workdays.items():
        if d.year == year:
            detail_to_workdays.setdefault(detail, []).append(d)

    # detail -> list[in-lieu holiday]
    detail_to_holidays: Dict[object, List[datetime.date]] = {}
    for d, detail in chinese_calendar.holidays.items():
        if d.year == year and chinese_calendar.is_in_lieu(d):
            detail_to_holidays.setdefault(detail, []).append(d)

    mapping: Dict[datetime.date, datetime.date] = {}
    for detail, holidays in detail_to_holidays.items():
        workdays = detail_to_workdays.get(detail, [])
        if not workdays:
            continue
        for h, w in zip(sorted(holidays), sorted(workdays)):
            mapping[h] = w
    return mapping


@lru_cache(maxsize=16)
def _workday_to_holiday_map(year: int) -> Dict[datetime.date, datetime.date]:
    """
    逆映射：补班日(workday) -> 调休休息日(holiday)
    """
    fwd = _holiday_to_workday_map(year)
    return {w: h for h, w in fwd.items()}


