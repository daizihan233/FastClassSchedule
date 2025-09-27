from fastapi import APIRouter
from utils.calc import compensation_from_holiday, compensation_from_workday, compensation_pairs
import datetime

router = APIRouter()

@router.get('/web/autorun/compensation/holiday/{year}/{month}/{day}')
def get_compensation_from_holiday(year: int, month: int, day: int):
    date = datetime.date(year, month, day)
    compensation = compensation_from_holiday(date)
    return {
        "date": date.isoformat(),
        "compensation": compensation.isoformat() if compensation else None
    }

@router.get('/web/autorun/compensation/workday/{year}/{month}/{day}')
def get_compensation_from_workday(year: int, month: int, day: int):
    date = datetime.date(year, month, day)
    compensation = compensation_from_workday(date)
    return {
        "date": date.isoformat(),
        "compensation": compensation.isoformat() if compensation else None
    }

@router.get('/web/autorun/compensation/year/{year}')
def get_compensation_pairs(year: int):
    pairs = compensation_pairs(year)
    return {
        "year": year,
        "pairs": [
            {"holiday": h.isoformat(), "workday": w.isoformat()} for h, w in pairs
        ]
    }