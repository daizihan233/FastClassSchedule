import json
from datetime import date, datetime
from typing import Any, Dict


def _fmt_dt(value: Any) -> str:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, str):
        return value
    return str(value)


def rule_to_text(rule: dict) -> str:
    """
    将规则变为可读的自然语言
    尽可能提取常见字段，否则回退为紧凑 JSON 字符串。
    """
    return json.dumps(rule, ensure_ascii=False)
