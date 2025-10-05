import datetime
import json
import pathlib
from typing import Any, Optional, Dict, Tuple, Set

from utils.globalvar import websocket_clients
from utils.schedule.dataclasses import AutorunType


def _fmt_dt(value: Any) -> str:
    if isinstance(value, (datetime.date, datetime.datetime)):
        return value.isoformat()
    if isinstance(value, str):
        return value
    return str(value)


def rule_to_text(rule: dict) -> str:
    """
    将规则变为可读的自然语言（兼容保留）
    """
    return json.dumps(rule, ensure_ascii=False)


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


def validate_scope(scope):
    from fastapi import HTTPException, status
    if not isinstance(scope, list) or not scope:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='scope 必须为非空列表')
    for s in scope:
        if not isinstance(s, str) or not s:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='scope 编码必须为字符串')
    return scope


def validate_content(content):
    from fastapi import HTTPException, status
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
    from fastapi import HTTPException, status
    if not isinstance(periods, list):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='periods 必须为数组')
    if len(periods) != need_count:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f'periods 长度必须为 {need_count}')
    no_set: Set[int] = set()
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


def parse_payload_basic(payload: Dict[str, Any], expected_type: int) -> Tuple[int, list, int, dict]:
    from fastapi import HTTPException, status
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


def _read_json(path: pathlib.Path) -> dict:
    return json.loads(path.read_text(encoding='utf-8'))


def get_subject_set(scope):
    subject_set: Set[str] = set()
    pairs: Set[Tuple[str, str]] = set()
    for s in scope:
        if not isinstance(s, str):
            continue
        parts = s.split('/')
        if len(parts) >= 2:
            pairs.add((parts[0], parts[1]))
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


def _yield_first_class_in_grade(school: str, grade: str):
    base = pathlib.Path(f"./data/{school}/{grade}")
    if base.exists():
        for p in sorted(base.iterdir()):
            if p.is_dir():
                yield school, grade, p.name
                break


def _yield_any_grade_and_class_in_school(school: str):
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


def _iter_scope_paths(scope):
    for s in scope:
        if not isinstance(s, str):
            continue
        parts = s.split('/')
        if len(parts) == 3:
            yield parts[0], parts[1], parts[2]
        elif len(parts) == 2:
            yield from _yield_first_class_in_grade(parts[0], parts[1])
        elif len(parts) == 1:
            yield from _yield_any_grade_and_class_in_school(parts[0])


def _to_count_from_timetable_entry(entry: dict) -> int:
    ints = [v for v in entry.values() if isinstance(v, int)]
    if not ints:
        return 0
    return max(ints) + 1


def _get_label_count(school: str, grade: str, label: str) -> int:
    from fastapi import HTTPException, status
    tpath = pathlib.Path(f"./data/{school}/{grade}/timetable.json")
    if not tpath.exists():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f'未找到作息表：{school}/{grade}')
    data = _read_json(tpath)
    tmap = data.get('timetable') or {}
    if label not in tmap:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f'作息表不存在：{label}')
    return _to_count_from_timetable_entry(tmap[label])


def _infer_label_for_date(school: str, grade: str, cls: str, date_str: str) -> str:
    from fastapi import HTTPException, status
    spath = pathlib.Path(f"./data/{school}/{grade}/{cls}/schedule.json")
    if not spath.exists():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f'未找到班级课表：{school}/{grade}/{cls}')
    data = _read_json(spath)
    dlist = data.get('daily_class')
    if not isinstance(dlist, list) or len(dlist) != 7:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='课表 daily_class 配置不正确')
    try:
        idx = datetime.date.fromisoformat(date_str).isoweekday() % 7
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='content.date 格式错误')
    label = dlist[idx].get('timetable')
    if not isinstance(label, str) or not label:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='当天作息表未配置')
    return label


def get_need_count(scope, date_str: Optional[str] = None, timetable_id: Optional[str] = None) -> int:
    counts: Set[int] = set()
    for school, grade, cls in _iter_scope_paths(scope):
        if timetable_id:
            c = _get_label_count(school, grade, timetable_id)
        else:
            label = _infer_label_for_date(school, grade, cls, date_str or '')
            c = _get_label_count(school, grade, label)
        counts.add(c)
    if not counts:
        return 0
    if len(counts) > 1:
        from fastapi import HTTPException, status
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f'所选作用域的节次数不一致：{sorted(counts)}')
    return counts.pop()


def _row_is_duplicate(r: dict, etype: int, date_str: str, timetable_id: Optional[str],
                      skip_hashid: Optional[str]) -> bool:
    try:
        if int(r.get('etype')) != etype:
            return False
    except Exception:
        return False
    if skip_hashid and r.get('hashid') == skip_hashid:
        return False
    rule = parse_rule_from_params(r.get('parameters'))
    if not isinstance(rule, dict):
        return False
    if str(rule.get('date')) != date_str:
        return False
    if timetable_id is not None and str(rule.get('timetableId')) != timetable_id:
        return False
    return True


def check_duplicate_rule(rows, etype: int, date_str: str, timetable_id: Optional[str] = None,
                         skip_hashid: Optional[str] = None):
    from fastapi import HTTPException, status
    if any(_row_is_duplicate(r, etype, date_str, timetable_id, skip_hashid) for r in (rows or [])):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='该规则已存在')


def _targets_for_all() -> Set[Tuple[str, int]]:
    return set(websocket_clients.keys())


def _targets_for_school(school: str) -> Set[Tuple[str, int]]:
    return {(sch, grd) for (sch, grd) in websocket_clients.keys() if sch == school}


def _targets_for_grade(school: str, grade_str: str) -> Set[Tuple[str, int]]:
    targets: Set[Tuple[str, int]] = set()
    try:
        grade = int(grade_str)
        targets.add((school, grade))
        return targets
    except Exception:
        pass
    for (sch, grd) in websocket_clients.keys():
        if sch == school and str(grd) == grade_str:
            targets.add((sch, grd))
    return targets


async def notify_ws_by_scope(scope: list[str]):
    targets: Set[Tuple[str, int]] = set()
    if not isinstance(scope, list):
        return
    for s in scope:
        if not isinstance(s, str):
            continue
        val = s.strip()
        if not val:
            continue
        if val.upper() == 'ALL':
            targets |= _targets_for_all()
            continue
        parts = val.split('/')
        if len(parts) == 1:
            targets |= _targets_for_school(parts[0])
        else:
            targets |= _targets_for_grade(parts[0], parts[1])
    for key in targets:
        mgr = websocket_clients.get(key)
        if mgr:
            try:
                await mgr.broadcast("SyncConfig")
            except Exception:
                continue


def map_row(row: dict) -> dict:
    status_map = {0: '待生效', 1: '生效中', 2: '已过期'}
    try:
        type_str = AutorunType(row.get('etype')).name
    except Exception:
        type_str = str(row.get('etype'))
    scope_list = parse_scope_value(row.get('scope'))
    rule_obj = parse_rule_from_params(row.get('parameters')) or {}
    return {
        'id': row.get('hashid', ''),
        'type': type_str,
        'scope': scope_list,
        'content': rule_obj,
        'priority': int(row.get('level', 0) or 0),
        'status': status_map.get(int(row.get('status', -1)), '未知')
    }
