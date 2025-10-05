import datetime
import json
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger


def decode_rule(params_text: Any) -> Dict[str, Any]:
    """从 records.parameters 提取规则 dict（兼容直接 rule 或平铺）。"""
    parsed = None
    if isinstance(params_text, str) and params_text:
        try:
            parsed = json.loads(params_text)
        except Exception:
            parsed = None
    elif isinstance(params_text, dict):
        parsed = params_text
    # 修正：无论上述分支如何，统一在此判断 parsed 是否为 dict，并提取 rule
    if isinstance(parsed, dict):
        rule = parsed.get('rule') if isinstance(parsed.get('rule'), dict) else parsed
        if isinstance(rule, dict):
            return rule
    return {}


def parse_scope_field(raw: Any) -> List[str]:
    """将数据库中的 scope 字段规范化为 List[str] 返回。"""
    if isinstance(raw, list):
        return [str(x) for x in raw]
    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            return []
        try:
            parsed = json.loads(s)
            if isinstance(parsed, list):
                return [str(x) for x in parsed]
            return [s]
        except Exception:
            return [s]
    return []


def scope_specificity(entry: str, school: str, grade: int | str, class_number: int | str | None) -> int:
    """
    作用域匹配与特异度：ALL->0; school->1; school/grade->2; school/grade/class->3；不匹配 -1。
    class_number 可为 None，此时最多匹配到 2 段。
    """
    try:
        s = str(entry).strip()
    except Exception:
        return -1
    if not s:
        return -1
    if s.upper() == 'ALL':
        return 0
    ctx = [str(school), str(grade)] + ([str(class_number)] if class_number is not None else [])
    parts = s.split('/')
    if len(parts) > len(ctx):
        return -1
    for i, p in enumerate(parts):
        if p != ctx[i]:
            return -1
    return len(parts)


def row_applicable_specificity(row: Dict[str, Any], school: str, grade: int | str,
                               class_number: int | str | None) -> int:
    raw = row.get('scope')
    scopes: List[str]
    if isinstance(raw, list):
        scopes = [str(x) for x in raw]
    elif isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            scopes = [str(x) for x in parsed] if isinstance(parsed, list) else [raw]
        except Exception as err:
            logger.error(err)
            scopes = [raw]
    else:
        return -1
    best = -1
    for s in scopes:
        spec = scope_specificity(s, school, grade, class_number)
        if spec > best:
            best = spec
    return best


def row_etype(row: Dict[str, Any]) -> Optional[int]:
    try:
        return int(row.get('etype'))
    except Exception:
        return None


def row_level(row: Dict[str, Any]) -> int:
    try:
        return int(row.get('level', 0) or 0)
    except Exception:
        return 0


def collect_applicable_candidates(
    rows: List[Dict[str, Any]], *, etype: int, school: str, grade: int | str, class_number: int | str | None,
    date_obj: datetime.date
) -> List[Tuple[int, int, Dict[str, Any]]]:
    """
    收集在指定 date_obj 生效且作用域匹配的候选规则，返回 (level, specificity, rule) 列表。
    """
    candidates: List[Tuple[int, int, Dict[str, Any]]] = []
    for r in rows:
        try:
            if row_etype(r) != etype:
                continue
            rule = decode_rule(r.get('parameters'))
            d = datetime.date.fromisoformat(str(rule.get('date')))
            if d != date_obj:
                continue
            spec = row_applicable_specificity(r, school, grade, class_number)
            if spec < 0:
                continue
            level = row_level(r)
            candidates.append((level, spec, rule))
        except Exception:
            continue
    candidates.sort(key=lambda x: (x[0], x[1]))
    return candidates
