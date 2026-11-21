"""matlas PostgreSQL 文档存储：key -> JSONB payload。

设计原则：数据库不可用时全部操作静默回退，绝不抛异常打断服务。
调用方据此把「读库失败」当作「无此记录」，退回原来的 JSON 文件链路。

连接参数来自环境变量 MATLAS_PG_DSN，默认指向 compose 里的 postgres 服务。
本机直接跑 Python（非容器）时把 MATLAS_PG_DSN 指到 localhost 即可。
"""
from __future__ import annotations

import datetime as dt
import json
import os

DEFAULT_DSN = "postgresql://matlas:matlas@postgres:5432/matlas"
DSN = os.environ.get("MATLAS_PG_DSN", DEFAULT_DSN)

_CONN = None
_FAILED = False


def _connect():
    """惰性连接；失败后本次进程内不再重试，避免每次请求都卡超时。"""
    global _CONN, _FAILED
    if _FAILED:
        return None
    if _CONN is not None:
        return _CONN
    try:
        import psycopg2
        _CONN = psycopg2.connect(DSN, connect_timeout=3)
        _CONN.autocommit = True
        return _CONN
    except Exception:  # noqa: BLE001 - 驱动缺失/库未起/网络不通都按不可用处理
        _FAILED = True
        return None


def available() -> bool:
    return _connect() is not None


def read(key: str):
    """读一个 key 的 payload；库不可用或无记录返回 None。"""
    conn = _connect()
    if conn is None:
        return None
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT payload FROM live_data WHERE key = %s", (key,))
            row = cur.fetchone()
        return row[0] if row else None
    except Exception:  # noqa: BLE001
        return None


def count() -> int:
    """返回 live_data 行数；库不可用返回 -1。用于识别空库首次初始化。"""
    conn = _connect()
    if conn is None:
        return -1
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM live_data")
            return int(cur.fetchone()[0])
    except Exception:  # noqa: BLE001
        return -1


def read_after(key: str, since: str):
    """读 updated_at 晚于 since 的记录，用于 api 侧感知同步更新。"""
    conn = _connect()
    if conn is None:
        return []
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT key, payload FROM live_data WHERE updated_at > %s", (since,)
            )
            return cur.fetchall()
    except Exception:  # noqa: BLE001
        return []


def write(key: str, payload) -> bool:
    """UPSERT 一个 key；成功返回 True。"""
    conn = _connect()
    if conn is None:
        return False
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO live_data(key, payload, updated_at) VALUES(%s, %s::jsonb, %s) "
                "ON CONFLICT(key) DO UPDATE SET payload=EXCLUDED.payload, updated_at=EXCLUDED.updated_at",
                (key, json.dumps(payload, ensure_ascii=False), _now()),
            )
        return True
    except Exception:  # noqa: BLE001
        return False


def write_many(items) -> int:
    """批量 UPSERT；items 为 (key, payload) 序列；返回成功条数。"""
    conn = _connect()
    if conn is None:
        return 0
    stamp = _now()
    try:
        with conn.cursor() as cur:
            for key, payload in items:
                cur.execute(
                    "INSERT INTO live_data(key, payload, updated_at) VALUES(%s, %s::jsonb, %s) "
                    "ON CONFLICT(key) DO UPDATE SET payload=EXCLUDED.payload, updated_at=EXCLUDED.updated_at",
                    (key, json.dumps(payload, ensure_ascii=False), stamp),
                )
        return len(items)
    except Exception:  # noqa: BLE001
        return 0


def _now() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
