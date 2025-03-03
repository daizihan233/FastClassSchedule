from pydantic import BaseModel

class DailyClass(BaseModel):
    Chinese: str
    English: str
    classList: list[list]
    timetable: str


class Schedule(BaseModel):
    daily_class: list[DailyClass]