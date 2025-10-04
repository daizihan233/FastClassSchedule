from fastapi import APIRouter, Depends, HTTPException, status, Body
from loguru import logger

from utils.calc import compensation_from_holiday, compensation_from_workday, compensation_pairs
import datetime
# 新增导入
import json
from typing import Optional, Annotated, Dict, Any
from utils.db import fetch_records, delete_record, upsert_record, refresh_statuses
from utils.autorun import rule_to_text
from utils.schedule.dataclasses import AutorunType
from utils.verify import get_current_identity

router = APIRouter()

def map_row(row: dict) -> dict:
    status_map = {0: '待生效', 1: '生效中', 2: '已过期'}
    # type 映射
    try:
        type_str = AutorunType(row.get('etype')).name
    except Exception:
        type_str = str(row.get('etype'))

    # scope
    scope_str = str(row.get('scope')) if row.get('scope') is not None else ''

    # content 由 parameters 解析并转文本
    content_text: str = ''
    params_text: Optional[str] = row.get('parameters')
    if isinstance(params_text, str) and params_text:
        try:
            parsed = json.loads(params_text)
            if isinstance(parsed, dict):
                rule = parsed.get('rule') if 'rule' in parsed else parsed
                if isinstance(rule, dict):
                    content_text = rule_to_text(rule)
                else:
                    content_text = str(parsed)
            else:
                content_text = str(parsed)
        except Exception:
            content_text = params_text

    return {
        'id': row.get('hashid', ''),
        'type': type_str,
        'scope': scope_str,
        'content': content_text,
        'priority': int(row.get('level', 0) or 0),
        'status': status_map.get(int(row.get('status', -1)), '未知')
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
    请求体示例：{"type":0,"scope":["ALL"],"priority":0,"content":{"date":"2025-10-11","useDate":"2025-10-08"}}
    """
    try:
        etype = int(payload.get('type', int(AutorunType.COMPENSATION)))
        if etype != int(AutorunType.COMPENSATION):
            raise ValueError('仅支持调休类型')
        scope = payload.get('scope') or ['ALL']
        if not isinstance(scope, list):
            raise ValueError('scope 必须为列表')
        level = int(payload.get('priority', 0))
        content = payload.get('content') or {}
        if not isinstance(content, dict):
            raise ValueError('content 必须为对象')
        date_str = str(content.get('date'))
        use_date_str = str(content.get('useDate'))
        # 基础校验
        datetime.date.fromisoformat(date_str)
        datetime.date.fromisoformat(use_date_str)
        parameters = {"rule": {"date": date_str, "useDate": use_date_str}}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f'无效参数: {e}')

    # 查重逻辑
    rows = fetch_records()
    for r in rows:
        params_text = r.get('parameters')
        if isinstance(params_text, str) and params_text:
            try:
                parsed = json.loads(params_text)
                rule = parsed.get('rule') if 'rule' in parsed else parsed
                if isinstance(rule, dict):
                    if rule.get('date') == date_str and rule.get('useDate') == use_date_str:
                        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='该调休规则已存在')
            except Exception:
                continue

    logger.info(f"收到新增调休任务请求：{identity} {parameters}")
    hid, _ = upsert_record(etype=etype, scope=scope, level=level, parameters=parameters)
    # 刷新一次状态，方便前端立刻看到“生效中/待生效”
    refresh_statuses()
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
        etype = int(payload.get('type', int(AutorunType.TIMETABLE)))
        if etype != int(AutorunType.TIMETABLE):
            raise ValueError('仅支持作息表调整类型')
        scope = payload.get('scope') or ['ALL']
        if not isinstance(scope, list):
            raise ValueError('scope 必须为列表')
        level = int(payload.get('priority', 0))
        content = payload.get('content') or {}
        if not isinstance(content, dict):
            raise ValueError('content 必须为对象')
        date_str = str(content.get('date'))
        timetable_id = content.get('timetableId')
        if not isinstance(timetable_id, str) or not timetable_id:
            raise ValueError('timetableId 必须为非空字符串')
        # 校验日期
        datetime.date.fromisoformat(date_str)
        parameters = {"rule": {"date": date_str, "timetableId": timetable_id}}
        # 可选编辑 id（支持顶层或 content 内）
        hashid: Optional[str] = None
        pid = payload.get('id')
        cid = content.get('id')
        if isinstance(pid, str) and pid:
            hashid = pid
        elif isinstance(cid, str) and cid:
            hashid = cid
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f'无效参数: {e}')

    # 查重逻辑（同一天同一作息表仅允许一条），编辑时跳过自身
    rows = fetch_records()
    for r in rows:
        try:
            if int(r.get('etype')) != etype:
                continue
        except Exception:
            continue
        if hashid and r.get('hashid') == hashid:
            continue
        params_text = r.get('parameters')
        if isinstance(params_text, str) and params_text:
            try:
                parsed = json.loads(params_text)
                rule = parsed.get('rule') if 'rule' in parsed else parsed
                if isinstance(rule, dict):
                    if str(rule.get('date')) == date_str and str(rule.get('timetableId')) == timetable_id:
                        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='该作息表调整规则已存在')
            except Exception:
                continue

    logger.info(f"收到新增/更新作息表任务请求：{identity} {parameters} edit_id={hashid}")
    hid, _ = upsert_record(etype=etype, scope=scope, level=level, parameters=parameters, hashid=hashid)
    # 刷新一次状态，方便前端立刻看到“生效中/待生效”
    refresh_statuses()
    return {"status": 200, "id": hid}

@router.delete('/web/autorun/{hashid}')
def delete_autorun_record(hashid: str, identity: Annotated[str, Depends(get_current_identity)]):
    logger.info(f"收到删除自动任务记录请求：{identity} 删除 {hashid}")
    affected = delete_record(hashid)
    if affected == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='记录不存在')
    return {"status": 200, "deleted": affected, "id": hashid}
