"""把采集器落地的 JSON 增量同步到 PostgreSQL。

数据源全部是 matlas/data/ 下自采的文件，本模块只负责把变化的文件
按 key 写进 live_data 表；API 侧优先读库，库不可用自动退回读文件。

key 约定（与 live_server.py 共用）：
  odds_ticks / results_data / fixtures  ->  data/ 对应文件的整个对象
  days/<date>                           ->  matlas data/days/<date>.json

用法：
  python db_sync.py            # 同步一次
  python db_sync.py --force    # 忽略 mtime 状态，全量写一次
  python db_sync.py --status   # 查看库可用性与各源状态
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
DAYS_DIR = DATA / "days"
STATE = DATA / ".db_sync_state.json"

SOURCES = [
    ("odds_full", DATA / "odds_full.json"),
    ("odds_ticks", DATA / "odds_ticks.json"),
    ("results_data", DATA / "results_data.json"),
    ("fixtures", DATA / "fixtures.json"),
    ("intel", DATA / "intel.json"),
    ("injuries", DATA / "injuries.json"),
]


def _load_state() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save_state(state: dict) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")


def _collect(force: bool = False):
    """返回待写入的 (key, payload) 列表与新状态。"""
    state = {} if force else _load_state()
    pending = []
    new_state = dict(state)

    for key, path in SOURCES:
        try:
            mt = path.stat().st_mtime
        except OSError:
            continue
        if not force and state.get(key) == mt:
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        pending.append((key, payload))
        new_state[key] = mt

    if DAYS_DIR.exists():
        for path in sorted(DAYS_DIR.glob("20??-??-??.json")):
            key = f"days/{path.stem}"
            try:
                mt = path.stat().st_mtime
            except OSError:
                continue
            if not force and state.get(key) == mt:
                continue
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            pending.append((key, payload))
            new_state[key] = mt

    return pending, new_state


def sync_once(force: bool = False) -> dict:
    import pg_store

    if not pg_store.available():
        return {"ok": False, "reason": "postgres unavailable", "written": 0}
    # 空库（新卷/首次部署）：忽略本地 mtime 状态，强制全量灌入一次。
    if not force and pg_store.count() <= 0:
        force = True
    pending, new_state = _collect(force)
    written = pg_store.write_many(pending) if pending else 0
    if written and written == len(pending):
        _save_state(new_state)
    return {
        "ok": True,
        "written": written,
        "scanned": len(pending),
        "at": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def status() -> dict:
    import pg_store

    state = _load_state()
    return {
        "postgres": pg_store.available(),
        "dsn_host": pg_store.DSN.split("@")[-1] if "@" in pg_store.DSN else pg_store.DSN,
        "tracked_keys": len(state),
        "data_dir": str(DATA),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="matlas 采集数据入库同步")
    ap.add_argument("--force", action="store_true", help="忽略 mtime 状态全量写入")
    ap.add_argument("--status", action="store_true", help="查看同步状态")
    args = ap.parse_args()

    if args.status:
        print(json.dumps(status(), ensure_ascii=False, indent=2))
        return 0

    result = sync_once(force=args.force)
    print(json.dumps(result, ensure_ascii=False), flush=True)
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
