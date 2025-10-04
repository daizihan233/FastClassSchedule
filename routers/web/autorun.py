import datetime
from typing import Optional, Annotated, Dict, Any, List, Callable

from fastapi import APIRouter, Depends, HTTPException, status, Body
from loguru import logger

from utils.calc import compensation_from_holiday, compensation_from_workday, compensation_pairs
from utils.db import fetch_records, delete_record, upsert_record, refresh_statuses
from utils.schedule.dataclasses import AutorunType
from utils.schedule.helpers import parse_scope_field, decode_rule
from utils.verify import get_current_identity

router = APIRouter()


def _status_text(v: Any) -> str:
    mapping = {0: '待生效', 1: '生效中', 2: '已过期'}
    try:
        return mapping.get(int(v), '未知')
    except Exception:
        return '未知'


def _type_name(v: Any) -> str:
    try:
        return AutorunType(v).name
    except Exception:
        return str(v)


def _extract_edit_id(payload: Dict[str, Any]) -> Optional[str]:
    """同时支持顶层 id 与 content.id。"""
    pid = payload.get('id')
    if isinstance(pid, str) and pid:
        return pid
    content = payload.get('content') or {}
    if isinstance(content, dict):
        cid = content.get('id')
        if isinstance(cid, str) and cid:
            return cid
    return None


def _require_date(date_str: Any) -> str:
    s = str(date_str)
    try:
        datetime.date.fromisoformat(s)
    except Exception:
        raise ValueError('date 必须为 ISO 格式 YYYY-MM-DD')
    return s


def _require_scope_list(scope_val: Any) -> List[str]:
    if not isinstance(scope_val, list):
        raise ValueError('scope 必须为列表')
    return [str(x) for x in scope_val]


def _check_duplicate(rows: List[Dict[str, Any]], *, etype: int, matcher: Callable[[Dict[str, Any]], bool],
                     skip_id: Optional[str]):
    for r in rows:
        try:
            if int(r.get('etype')) != etype:
                continue
        except Exception:
            continue
        if skip_id and r.get('hashid') == skip_id:
            continue
        rule = decode_rule(r.get('parameters'))
        try:
            if matcher(rule):
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='规则已存在')
        except HTTPException:
            raise
        except Exception:
            continue


def _upsert_and_refresh(*, etype: int, scope: List[str], level: int, parameters: Dict[str, Any],
                        hashid: Optional[str]) -> Dict[str, Any]:
    hid, _ = upsert_record(etype=etype, scope=scope, level=level, parameters=parameters, hashid=hashid)
    refresh_statuses()
    return {"status": 200, "id": hid}


def map_row(row: dict) -> dict:
    return {
        'id': row.get('hashid', ''),
        'type': _type_name(row.get('etype')),
        'scope': parse_scope_field(row.get('scope')),
        'content': decode_rule(row.get('parameters')),
        'priority': int(row.get('level', 0) or 0),
        'status': _status_text(row.get('status'))
    }

@router.get('/web/autorun')
def get_autorun_status():
    """获取当前自动任务日志状态（返回所有记录）"""
    rows = fetch_records()
    if not rows:
        return {"data": []}
    data = [map_row(r) for r in rows]
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
    Body: {"type":0,"scope":string[],"priority":number,"content":{"date":"YYYY-MM-DD","useDate":"YYYY-MM-DD"},"id?":string}
    """
    try:
        etype = int(payload.get('type', int(AutorunType.COMPENSATION)))
        if etype != int(AutorunType.COMPENSATION):
            raise ValueError('仅支持调休类型')
        scope = _require_scope_list(payload.get('scope') or ['ALL'])
        level = int(payload.get('priority', 0))
        content = payload.get('content') or {}
        if not isinstance(content, dict):
            raise ValueError('content 必须为对象')
        date_str = _require_date(content.get('date'))
        use_date_str = _require_date(content.get('useDate'))
        parameters = {"rule": {"date": date_str, "useDate": use_date_str}}
        edit_id = _extract_edit_id(payload)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f'无效参数: {e}')

    # 查重：同一 (date, useDate)
    rows = fetch_records()
    _check_duplicate(
        rows,
        etype=etype,
        skip_id=edit_id,
        matcher=lambda rule: str(rule.get('date')) == date_str and str(rule.get('useDate')) == use_date_str
    )

    logger.info(f"收到新增/更新调休任务请求：{identity} {parameters} edit_id={edit_id}")
    return _upsert_and_refresh(etype=etype, scope=scope, level=level, parameters=parameters, hashid=edit_id)


@router.put('/web/autorun/timetable')
async def put_timetable(
    identity: Annotated[str, Depends(get_current_identity)],
    payload: Dict[str, Any] = Body(...)
):
    """
    新增/更新一条作息表调整自动任务。
    Body: { "type": 1, "scope": string[], "priority": number, "content": { "date": "YYYY-MM-DD", "timetableId": string }, "id?": string }
    """
    try:
        etype = int(payload.get('type', int(AutorunType.TIMETABLE)))
        if etype != int(AutorunType.TIMETABLE):
            raise ValueError('仅支持作息表调整类型')
        scope = _require_scope_list(payload.get('scope') or ['ALL'])
        level = int(payload.get('priority', 0))
        content = payload.get('content') or {}
        if not isinstance(content, dict):
            raise ValueError('content 必须为对象')
        date_str = _require_date(content.get('date'))
        timetable_id = content.get('timetableId')
        if not isinstance(timetable_id, str) or not timetable_id:
            raise ValueError('timetableId 必须为非空字符串')
        parameters = {"rule": {"date": date_str, "timetableId": timetable_id}}
        edit_id = _extract_edit_id(payload)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f'无效参数: {e}')

    # 查重：同一 (date, timetableId)
    rows = fetch_records()
    _check_duplicate(
        rows,
        etype=etype,
        skip_id=edit_id,
        matcher=lambda rule: str(rule.get('date')) == date_str and str(rule.get('timetableId')) == timetable_id
    )

    logger.info(f"收到新增/更新作息表任务请求：{identity} {parameters} edit_id={edit_id}")
    return _upsert_and_refresh(etype=etype, scope=scope, level=level, parameters=parameters, hashid=edit_id)


@router.delete('/web/autorun/{hashid}')
def delete_autorun_record(hashid: str, identity: Annotated[str, Depends(get_current_identity)]):
    logger.info(f"收到删除自动任务记录请求：{identity} 删除 {hashid}")
    affected = delete_record(hashid)
    if affected == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='记录不存在')
    return {"status": 200, "deleted": affected, "id": hashid}
