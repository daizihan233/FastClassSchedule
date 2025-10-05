import datetime
# 新增导入
import json
import pathlib
from typing import Optional, Annotated, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, status, Body
from loguru import logger

from utils.calc import compensation_from_holiday, compensation_from_workday, compensation_pairs
from utils.db import fetch_records, delete_record, upsert_record, refresh_statuses
from utils.globalvar import websocket_clients
from utils.schedule.dataclasses import AutorunType
from utils.verify import get_current_identity

router = APIRouter()

ERR_CONTENT_OBJ = 'content 必须为对象'


def parse_rule_from_params(params_text: Optional[str]) -> Optional[dict]:
    if not isinstance(params_text, str) or not params_text:
        return None
    try:
        parsed = json.loads(params_text)
        if isinstance(parsed, dict):
            return parsed.get('rule') if 'rule' in parsed else parsed
    except Exception:
        return None
    return None


def parse_scope_value(scope_val: Any) -> list:
    if isinstance(scope_val, list):
        return scope_val
    if isinstance(scope_val, str) and scope_val.strip():
        try:
            v = json.loads(scope_val)
            return v if isinstance(v, list) else []
        except Exception:
            return []
    return []


def parse_payload_basic(payload: Dict[str, Any], expected_type: int) -> tuple[int, list, int, dict]:
    etype = int(payload.get('type', expected_type))
    if etype != expected_type:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f'仅支持 type={expected_type}')
    scope = validate_scope(payload.get('scope'))
    level = int(payload.get('priority', 0))
    content = payload.get('content') or {}
    if not isinstance(content, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=ERR_CONTENT_OBJ)
    content = validate_content(content)
    return etype, scope, level, content


def map_row(row: dict) -> dict:
    status_map = {0: '待生效', 1: '生效中', 2: '已过期'}
    # type 映射
    try:
        type_str = AutorunType(row.get('etype')).name
    except Exception:
        type_str = str(row.get('etype'))

    # scope
    scope_list = parse_scope_value(row.get('scope'))

    # content 解析（返回原始规则对象，不返回字符串）
    rule_obj = parse_rule_from_params(row.get('parameters')) or {}

    return {
        'id': row.get('hashid', ''),
        'type': type_str,
        'scope': scope_list,
        'content': rule_obj,
        'priority': int(row.get('level', 0) or 0),
        'status': status_map.get(int(row.get('status', -1)), '未知')
    }


def check_duplicate_rule(rows, etype: int, date_str: str, timetable_id: str | None = None,
                         skip_hashid: str | None = None):
    for r in rows:
        try:
            if int(r.get('etype')) != etype:
                continue
        except Exception:
            continue
        if skip_hashid and r.get('hashid') == skip_hashid:
            continue
        rule = parse_rule_from_params(r.get('parameters'))
        if not isinstance(rule, dict):
            continue
        if str(rule.get('date')) == date_str and (timetable_id is None or str(rule.get('timetableId')) == timetable_id):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='该规则已存在')


def get_subject_set(scope):
    # 从作用域中提取唯一 (school, grade) 组合，聚合学科集合
    pairs = set()
    for s in scope:
        parts = s.split('/')
        if len(parts) >= 2:
            pairs.add((parts[0], parts[1]))
    subject_set = set()
    for school, grade in sorted(pairs):
        path = pathlib.Path(f"./data/{school}/{grade}/subjects.json")
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text())
            for subj in data.get("subjects", []):
                v = subj.get("value")
                if v:
                    subject_set.add(v)
        except Exception:
            continue
    return subject_set


def _iter_scope_paths(scope):
    for s in scope:
        parts = s.split('/')
        if len(parts) == 3:
            yield parts[0], parts[1], parts[2]
        elif len(parts) == 2:
            # 选取任意一个班级作为代表
            school, grade = parts[0], parts[1]
            base = pathlib.Path(f"./data/{school}/{grade}")
            if base.exists():
                for p in sorted(base.iterdir()):
                    if p.is_dir():
                        yield school, grade, p.name
                        break
        elif len(parts) == 1:
            # 选取任意一个年级与班级
            school = parts[0]
            base = pathlib.Path(f"./data/{school}")
            if base.exists():
                for g in sorted(base.iterdir()):
                    if g.is_dir():
                        gb = pathlib.Path(g)
                        for c in sorted(gb.iterdir()):
                            if c.is_dir():
                                yield school, g.name, c.name
                                break
                        break


def _read_json(path: pathlib.Path) -> dict:
    return json.loads(path.read_text(encoding='utf-8'))


def _to_count_from_timetable_entry(entry: dict) -> int:
    # 从一个具体 label 的作息表条目计算节次数（最大整数索引 + 1）
    ints = [v for v in entry.values() if isinstance(v, int)]
    if not ints:
        return 0
    return max(ints) + 1


def _get_label_count(school: str, grade: str, label: str) -> int:
    tpath = pathlib.Path(f"./data/{school}/{grade}/timetable.json")
    if not tpath.exists():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f'未找到作息表：{school}/{grade}')
    data = _read_json(tpath)
    tmap = data.get('timetable') or {}
    if label not in tmap:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f'作息表不存在：{label}')
    return _to_count_from_timetable_entry(tmap[label])


def _infer_label_for_date(school: str, grade: str, cls: str, date_str: str) -> str:
    spath = pathlib.Path(f"./data/{school}/{grade}/{cls}/schedule.json")
    if not spath.exists():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f'未找到班级课表：{school}/{grade}/{cls}')
    data = _read_json(spath)
    dlist = data.get('daily_class')
    if not isinstance(dlist, list) or len(dlist) != 7:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='课表 daily_class 配置不正确')
    try:
        idx = datetime.date.fromisoformat(date_str).isoweekday() % 7  # 周日=0，周一=1
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='content.date 格式错误')
    label = dlist[idx].get('timetable')
    if not isinstance(label, str) or not label:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='当天作息表未配置')
    return label


def get_need_count(scope, date_str=None, timetable_id=None):
    """
    计算节次数（toCount）：
    - type=3（ALL）：基于 content.timetableId 的作息表标签，按 timetable.json 条目最大整数+1，遇到“只有一个 0”视为 0 节。
    - type=2（SCHEDULE）：基于 date 推断当天的作息表标签（从 scope 对应的某个班 schedule.json 的 daily_class），再用上面的规则计算。
    多个 scope 若计算不一致，返回 400。
    """
    counts = set()
    for school, grade, cls in _iter_scope_paths(scope):
        if timetable_id:
            c = _get_label_count(school, grade, timetable_id)
        else:
            label = _infer_label_for_date(school, grade, cls, date_str)
            c = _get_label_count(school, grade, label)
        counts.add(c)
    if not counts:
        return 0
    if len(counts) > 1:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f'所选作用域的节次数不一致：{sorted(counts)}')
    return counts.pop()

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


async def _notify_ws_by_scope(scope: list[str]):
    # 根据 scope 解析到 (school, grade) 键，并向对应 WS 连接广播 SyncConfig
    targets: set[tuple[str, int]] = set()
    if not isinstance(scope, list):
        return
    for s in scope:
        try:
            if not isinstance(s, str):
                continue
            val = s.strip()
            if not val:
                continue
            if val.upper() == 'ALL':
                targets.update(websocket_clients.keys())
                continue
            parts = val.split('/')
            if len(parts) == 1:
                school = parts[0]
                # 该学校下所有已连接的 grade
                targets.update({(sch, grd) for (sch, grd) in websocket_clients.keys() if sch == school})
            else:
                school = parts[0]
                grade_str = parts[1]
                try:
                    grade = int(grade_str)
                except Exception:
                    # 若无法解析为 int，则尝试与已连接的键做字符串比较
                    for (sch, grd) in websocket_clients.keys():
                        if sch == school and str(grd) == grade_str:
                            targets.add((sch, grd))
                    continue
                targets.add((school, grade))
        except Exception:
            continue
    # 广播
    for key in targets:
        mgr = websocket_clients.get(key)
        if mgr:
            try:
                await mgr.broadcast("SyncConfig")
            except Exception:
                continue

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
    await _notify_ws_by_scope(scope)
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
    await _notify_ws_by_scope(scope)
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
        await _notify_ws_by_scope(scope_to_notify)
    return {"status": 200, "deleted": affected, "id": hashid}


def validate_scope(scope):
    if not isinstance(scope, list) or not scope:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='scope 必须为非空列表')
    for s in scope:
        if not isinstance(s, str) or not s:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='scope 编码必须为字符串')
    return scope


def validate_content(content):
    if not isinstance(content, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='content 必须为对象')
    date_str = content.get('date')
    if not isinstance(date_str, str):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='content.date 必须为字符串')
    try:
        datetime.date.fromisoformat(date_str)
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='content.date 格式错误')
    return content


def validate_periods(periods, need_count, subject_set):
    if not isinstance(periods, list):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='periods 必须为数组')
    if len(periods) != need_count:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f'periods 长度必须为 {need_count}')
    no_set = set()
    for idx, p in enumerate(periods):
        if not isinstance(p, dict):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='periods 元素必须为对象')
        no = p.get('no')
        subject = p.get('subject')
        if not isinstance(no, int) or no != idx + 1 or no in no_set:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='periods.no 必须递增且不重复')
        no_set.add(no)
        if subject_set and subject not in subject_set:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='periods.subject 非法')
    return periods


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
        scope = validate_scope(payload.get('scope'))
        level = int(payload.get('priority', 0))
        content = validate_content(payload.get('content'))
        date_str = content['date']
        schedule = content.get('schedule')
        if not isinstance(schedule, dict):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='content.schedule 必须为对象')
        periods = schedule.get('periods')
        subject_set = get_subject_set(scope)
        need_count = get_need_count(scope, date_str=date_str)
        validate_periods(periods, need_count, subject_set)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f'无效参数: {e}')
    rows = fetch_records()
    check_duplicate_rule(rows, etype, date_str)
    parameters = {"rule": {"date": date_str, "schedule": {"periods": periods}}}
    logger.info(f"收到新增课程表调整任务请求：{identity} {parameters}")
    hid, _ = upsert_record(etype=etype, scope=scope, level=level, parameters=parameters)
    refresh_statuses()
    await _notify_ws_by_scope(scope)
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
        scope = validate_scope(payload.get('scope'))
        level = int(payload.get('priority', 0))
        content = validate_content(payload.get('content'))
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
        validate_periods(periods, need_count, subject_set)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f'无效参数: {e}')
    rows = fetch_records()
    check_duplicate_rule(rows, etype, date_str, timetable_id)
    parameters = {"rule": {"date": date_str, "timetableId": timetable_id, "schedule": {"periods": periods}}}
    logger.info(f"收到新增全部调整任务请求：{identity} {parameters}")
    hid, _ = upsert_record(etype=etype, scope=scope, level=level, parameters=parameters)
    refresh_statuses()
    await _notify_ws_by_scope(scope)
    return {"status": 200, "id": hid}
