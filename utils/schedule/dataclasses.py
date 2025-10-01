from enum import IntEnum

from pydantic import BaseModel
from typing import List, Dict, Union


class DailyClass(BaseModel):
    Chinese: str
    English: str
    classList: list[list]
    timetable: str


class Schedule(BaseModel):
    daily_class: list[DailyClass]


class SubjectItem(BaseModel):
    text: str


class Subjects(BaseModel):
    abbr: List[SubjectItem]
    fullName: List[SubjectItem]

class Timetable(BaseModel):
    timetable: Dict[str, Dict[str, Union[str, int]]]
    divider: Dict[str, List[int]]
    start: str

class Setting(BaseModel):
    countdown_target: str
    weather_alert_override: bool
    weather_alert_brief: bool
    week_display: bool
    banner_text: str
    css_style: Dict[str, str]

class AutorunType(IntEnum):
    COMPENSATION = 0  # 调休
    TIMETABLE = 1  # 作息表调整
    SCHEDULE = 2  # 课程表调整
    ALL = 3  # 作息表、课程表均调整
