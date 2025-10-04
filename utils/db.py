import datetime
import hashlib
import json
import os
import sqlite3
from typing import Optional, List, Dict, Any, Tuple

DB_PATH: Optional[str] = None

_def_none = object()


def _get_rule_date(parameters: Any) -> Optional[datetime.date]:
    if not isinstance(parameters, dict):
        return None
    rule = parameters.get('rule', _def_none)
    if isinstance(rule, dict):
        target = rule
    else:
        target = parameters
    try:
        return datetime.date.fromisoformat(str(target.get('date')))
    except Exception:
        return None


def init_db(db_path: str):
    global DB_PATH
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS records (
            hashid TEXT PRIMARY KEY,
            etype INTEGER NOT NULL,
            scope TEXT NOT NULL,
            parameters TEXT NOT NULL,
            level INTEGER NOT NULL,
            status INTEGER NOT NULL
        )
    ''')
    conn.commit()
    conn.close()
    DB_PATH = db_path


def get_connection() -> sqlite3.Connection:
    if not DB_PATH:
        # 默认路径与 main.py 初始化一致
        default_path = './data/records.db'
        os.makedirs(os.path.dirname(default_path), exist_ok=True)
        return sqlite3.connect(default_path)
    return sqlite3.connect(DB_PATH)


def _get_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    cur = conn.cursor()
    cur.execute(f"PRAGMA table_info({table})")
    cols = {row[1] for row in cur.fetchall()}
    return cols


def fetch_records(limit: Optional[int] = None) -> List[Dict[str, Any]]:
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cols = _get_columns(conn, 'records')
    base_cols = ['hashid', 'etype', 'parameters', 'level', 'status']
    select_cols = base_cols.copy()
    has_scope = 'scope' in cols
    if has_scope:
        select_cols.insert(2, 'scope')  # 放在 parameters 前

    sql = f"SELECT {', '.join(select_cols)} FROM records ORDER BY level DESC, hashid DESC"
    if limit is not None:
        sql += ' LIMIT ?'
        cur.execute(sql, (limit,))
    else:
        cur.execute(sql)
    rows = [dict(r) for r in cur.fetchall()]

    if not has_scope:
        for r in rows:
            # 维持类型为 str，便于上层统一解析为 list
            r['scope'] = '[]'

    conn.close()
    return rows


def delete_record(hashid: str) -> int:
    """按 hashid 删除记录，返回受影响行数"""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute('DELETE FROM records WHERE hashid = ?', (hashid,))
    affected = cur.rowcount
    conn.commit()
    conn.close()
    return affected


def _calc_hashid(etype: int, scope: List[str], level: int, parameters: Dict[str, Any]) -> str:
    payload = json.dumps({'etype': etype, 'scope': scope, 'level': level, 'parameters': parameters},
                         ensure_ascii=False, sort_keys=True)
    seed = f"{etype}|{level}|{payload}"
    return hashlib.sha256(seed.encode('utf-8')).hexdigest()[:16]


def upsert_record(etype: int, scope: List[str], level: int, parameters: Dict[str, Any],
                  hashid: Optional[str] = None) -> Tuple[str, int]:
    """
    插入或替换一条记录。
    :return: (hashid, affected_rows)
    """
    hid = hashid or _calc_hashid(etype, scope, level, parameters)
    conn = get_connection()
    cur = conn.cursor()
    status = _derive_status_for_record(etype, parameters)
    cur.execute(
        'INSERT OR REPLACE INTO records (hashid, etype, scope, parameters, level, status) VALUES (?, ?, ?, ?, ?, ?)',
        (
            hid,
            etype,
            json.dumps(scope, ensure_ascii=False),
            json.dumps(parameters, ensure_ascii=False),
            level,
            status
        )
    )
    affected = cur.rowcount
    conn.commit()
    conn.close()
    return hid, affected


def _derive_status_for_record(etype: int, parameters: Dict[str, Any], today: Optional[datetime.date] = None) -> int:
    """
    计算记录状态：0 待生效, 1 生效中, 2 已过期
    对于 etype in (0, 1)：在 parameters = {"rule": {"date": "YYYY-MM-DD", ...}}
    的语义下使用 date 字段判断状态；其他类型默认 0。
    """
    if today is None:
        today = datetime.date.today()
    if etype not in (0, 1):
        return 0
    d = _get_rule_date(parameters)
    if not d:
        return 0
    if today < d:
        return 0
    if today == d:
        return 1
    return 2


def refresh_statuses(today: Optional[datetime.date] = None) -> int:
    """遍历 records 并刷新 status 字段，返回更新条数"""
    if today is None:
        today = datetime.date.today()
    conn = get_connection()
    cur = conn.cursor()
    cur.execute('SELECT hashid, etype, parameters, status FROM records')
    rows = cur.fetchall()
    updated = 0
    for hid, etype, params_text, status in rows:
        try:
            params = json.loads(params_text)
        except Exception:
            params = {}
        new_status = _derive_status_for_record(int(etype), params, today)
        if int(status) != new_status:
            cur.execute('UPDATE records SET status = ? WHERE hashid = ?', (new_status, hid))
            updated += 1
    conn.commit()
    conn.close()
    return updated
