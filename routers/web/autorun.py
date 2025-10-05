import datetime
from typing import Optional, Annotated, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, status, Body
from loguru import logger

from utils.autorun import (
    parse_payload_basic,
    get_subject_set,
    get_need_count,
    check_duplicate_rule,
    notify_ws_by_scope,
    map_row,
    parse_scope_value,
)
from utils.calc import compensation_from_holiday, compensation_from_workday, compensation_pairs
from utils.db import fetch_records, delete_record, upsert_record, refresh_statuses
from utils.schedule.dataclasses import AutorunType
from utils.verify import get_current_identity

router = APIRouter()

ERR_CONTENT_OBJ = 'content 必须为对象'


@router.get('/web/autorun')
def get_autorun_status():
    """获取当前自动任务日志状态（返回所有记录）"""
    # 查询前刷新一次状态
    refresh_statuses()
    rows = fetch_records()
    if not rows:
        return {"data": []}
    data = [map_row(r) for r in rows]
    return {"data": data}


@router.get('/web/autorun/{hashid}')
def get_autorun_status(hashid: str):
    """获取当前自动任务日志状态（返回目标记录）"""
    # 查询前刷新一次状态
    refresh_statuses()
    rows = fetch_records(hashid)
    if not rows:
        return {"data": []}
    data = [map_row(r) for r in rows][0]
    return {"data": data}


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


@router.put('/web/autorun/compensation')
async def put_compensation(
    identity: Annotated[str, Depends(get_current_identity)],
    payload: Dict[str, Any] = Body(...)
):
    """
    新增/更新一条调休自动任务。
    请求体示例：{"type":0,"scope":["ALL"],"priority":0,"content":{"date":"2025-10-11","useDate":"2025-10-08"}}
    """
    try:
        etype, scope, level, content = parse_payload_basic(payload, int(AutorunType.COMPENSATION))
        date_str = str(content.get('date'))
        use_date_str = str(content.get('useDate'))
        datetime.date.fromisoformat(date_str)
        datetime.date.fromisoformat(use_date_str)
        parameters = {"rule": {"date": date_str, "useDate": use_date_str}}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f'无效参数: {e}')

    rows = fetch_records()
    check_duplicate_rule(rows, etype, date_str)

    logger.info(f"收到新增调休任务请求：{identity} {parameters}")
    hid, _ = upsert_record(etype=etype, scope=scope, level=level, parameters=parameters)
    refresh_statuses()
    await notify_ws_by_scope(scope)
    return {"status": 200, "id": hid}


@router.put('/web/autorun/timetable')
async def put_timetable(
    identity: Annotated[str, Depends(get_current_identity)],
    payload: Dict[str, Any] = Body(...)
):
    """
    新增/更新一条作息表调整自动任务。
    Body: { "type": 1, "scope": string[], "priority": number, "content": { "date": "YYYY-MM-DD", "timetableId": string, "id?": string } }
    示例：{ "type": 1, "scope": ["39/2023", "39/2023/1"], "priority": 5, "content": { "date": "2025-10-12", "timetableId": "运动会" } }
    支持编辑：可在 content.id 或顶层 id 传入记录 hashid 进行替换。
    """
    try:
        etype, scope, level, content = parse_payload_basic(payload, int(AutorunType.TIMETABLE))
        date_str = str(content.get('date'))
        timetable_id = content.get('timetableId')
        if not isinstance(timetable_id, str) or not timetable_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='timetableId 必须为非空字符串')
        datetime.date.fromisoformat(date_str)
        parameters = {"rule": {"date": date_str, "timetableId": timetable_id}}
        # 编辑 id（支持顶层或 content 内）
        hashid: Optional[str] = None
        for key in ('id',):
            v = payload.get(key)
            if isinstance(v, str) and v:
                hashid = v
                break
        if not hashid:
            cid = content.get('id')
            if isinstance(cid, str) and cid:
                hashid = cid
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f'无效参数: {e}')

    rows = fetch_records()
    check_duplicate_rule(rows, etype, date_str, timetable_id=timetable_id, skip_hashid=hashid)

    logger.info(f"收到新增/更新作息表任务请求：{identity} {parameters} edit_id={hashid}")
    hid, _ = upsert_record(etype=etype, scope=scope, level=level, parameters=parameters, hashid=hashid)
    refresh_statuses()
    await notify_ws_by_scope(scope)
    return {"status": 200, "id": hid}


@router.delete('/web/autorun/{hashid}')
async def delete_autorun_record(hashid: str, identity: Annotated[str, Depends(get_current_identity)]):
    logger.info(f"收到删除自动任务记录请求：{identity} 删除 {hashid}")
    # 先查询该记录的 scope 以便广播
    rows = fetch_records()
    scope_to_notify: list[str] = []
    for r in rows:
        if r.get('hashid') == hashid:
            scope_to_notify = parse_scope_value(r.get('scope'))
            break
    affected = delete_record(hashid)
    if affected == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='记录不存在')
    refresh_statuses()
    if scope_to_notify:
        await notify_ws_by_scope(scope_to_notify)
    return {"status": 200, "deleted": affected, "id": hashid}


@router.put('/web/autorun/schedule')
async def put_schedule(
    identity: Annotated[str, Depends(get_current_identity)],
    payload: Dict[str, Any] = Body(...)
):
    """
    新增/更新一条课程表调整自动任务。
    """
    try:
        etype = int(payload.get('type', 2))
        if etype != 2:
            raise ValueError('仅支持 type=2')
        scope = parse_payload_basic(payload, 2)[1]
        level = int(payload.get('priority', 0))
        content = parse_payload_basic(payload, 2)[3]
        date_str = content['date']
        schedule = content.get('schedule')
        if not isinstance(schedule, dict):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='content.schedule 必须为对象')
        periods = schedule.get('periods')
        subject_set = get_subject_set(scope)
        need_count = get_need_count(scope, date_str=date_str)
        from utils.autorun import validate_periods  # local import to avoid polluting namespace
        validate_periods(periods, need_count, subject_set)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f'无效参数: {e}')
    rows = fetch_records()
    check_duplicate_rule(rows, etype, date_str)
    parameters = {"rule": {"date": date_str, "schedule": {"periods": periods}}}
    logger.info(f"收到新增课程表调整任务请求：{identity} {parameters}")
    hid, _ = upsert_record(etype=etype, scope=scope, level=level, parameters=parameters)
    refresh_statuses()
    await notify_ws_by_scope(scope)
    return {"status": 200, "id": hid}


@router.put('/web/autorun/all')
async def put_all(
    identity: Annotated[str, Depends(get_current_identity)],
    payload: Dict[str, Any] = Body(...)
):
    """
    新增/更新一条全部调整自动任务。
    """
    try:
        etype = int(payload.get('type', 3))
        if etype != 3:
            raise ValueError('仅支持 type=3')
        scope = parse_payload_basic(payload, 3)[1]
        level = int(payload.get('priority', 0))
        content = parse_payload_basic(payload, 3)[3]
        date_str = content['date']
        timetable_id = content.get('timetableId')
        if not isinstance(timetable_id, str) or not timetable_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='content.timetableId 必须为非空字符串')
        schedule = content.get('schedule')
        if not isinstance(schedule, dict):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='content.schedule 必须为对象')
        periods = schedule.get('periods')
        subject_set = get_subject_set(scope)
        need_count = get_need_count(scope, timetable_id=timetable_id)
        from utils.autorun import validate_periods
        validate_periods(periods, need_count, subject_set)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f'无效参数: {e}')
    rows = fetch_records()
    check_duplicate_rule(rows, etype, date_str, timetable_id)
    parameters = {"rule": {"date": date_str, "timetableId": timetable_id, "schedule": {"periods": periods}}}
    logger.info(f"收到新增全部调整任务请求：{identity} {parameters}")
    hid, _ = upsert_record(etype=etype, scope=scope, level=level, parameters=parameters)
    refresh_statuses()
    await notify_ws_by_scope(scope)
    return {"status": 200, "id": hid}
