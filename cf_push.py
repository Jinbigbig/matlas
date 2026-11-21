"""Matlas 实时数据 → Cloudflare KV 推送器（方案 A 本地侧）。

把 live_server.live_for() 生成的数据推到 CF KV，供边缘 Worker 读取。
数据逻辑与本地 API 完全共用（同一份 live_for），只是出口从 HTTP 换成 KV。

用法：
    python cf_push.py --once         推一次（定时任务 / 手工）
    python cf_push.py --loop         常驻循环，每 PUSH_INTERVAL 秒推一次
    python cf_push.py --date 2026-11-21 --once   只推指定日期

凭证取自 .env：CF_ACCOUNT_ID / CF_API_TOKEN / CF_KV_NAMESPACE_ID。
走 CF REST API（Writes KV），单次请求约 1-3 秒，与隧道回源无关。
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import live_server  # noqa: E402

CF_API = "https://api.cloudflare.com/client/v4"

# CF 免费版 KV 每日写入上限 1000 次，留出余量避免打穿后整轮 429。
DAILY_BUDGET = 900
# 比分没变时，赔率最多回刷一次的间隔（秒），保证赔率不会长期停在旧值。
REFRESH_SEC = 600
# 参与「是否推送」判定的字段：只有比分与状态变化才触发写入。
CORE_FIELDS = ("match_id", "status", "score", "half")
# 赔率类字段不进核心指纹：它们每分钟都在动，若参与判定会瞬间耗尽配额。
SKIP_FIELDS = {"updated", "odds", "odds_ticks", "trend_html", "odds_full"}

STATE_FILE = ROOT / "data" / ".cf_push_state.json"


class Quota(Exception):
    """当日写入预算或 CF 配额用尽，本轮必须停下。"""


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _load_dotenv() -> None:
    """读项目 .env 的 KEY=VALUE（不覆盖已有环境变量）。"""
    p = ROOT / ".env"
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


def _kv_write(key: str, obj) -> bool:
    """PUT 一个 JSON 值到 CF KV。返回是否成功；配额用尽抛 Quota。"""
    account = _env("CF_ACCOUNT_ID")
    token = _env("CF_API_TOKEN")
    ns = _env("CF_KV_NAMESPACE_ID")
    if not (account and token and ns):
        print("[push] 缺少 CF_ACCOUNT_ID / CF_API_TOKEN / CF_KV_NAMESPACE_ID", file=sys.stderr)
        return False
    body = json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    url = f"{CF_API}/accounts/{account}/storage/kv/namespaces/{ns}/values/{urllib.parse.quote(key, safe='/')}"
    req = urllib.request.Request(
        url,
        data=body,
        method="PUT",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return 200 <= resp.status < 300
    except urllib.error.HTTPError as ex:
        if ex.code == 429:
            raise Quota("CF KV 写入额度已用尽（429）") from ex
        print(f"[push] KV 写入失败 {key}: HTTP {ex.code}", file=sys.stderr)
        return False
    except Exception as ex:  # noqa: BLE001
        print(f"[push] KV 写入失败 {key}: {ex}", file=sys.stderr)
        return False


def _utc_today() -> str:
    return dt.datetime.now(dt.timezone.utc).date().isoformat()


def _load_state() -> dict:
    """读推送状态；跨 UTC 日自动清零计数。"""
    try:
        st = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        st = {}
    if not isinstance(st, dict) or st.get("budget_date") != _utc_today():
        st = {"budget_date": _utc_today(), "writes": 0, "fp": {}, "ts": {}, "index_ts": 0}
    st.setdefault("fp", {})
    st.setdefault("ts", {})
    st.setdefault("writes", 0)
    st.setdefault("index_ts", 0)
    return st


def _save_state(st: dict) -> None:
    try:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(
            json.dumps(st, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass


def _fingerprint(obj, *, core: bool = True) -> str:
    """内容指纹。core=True 只算比分/状态，赔率变动不参与判定。"""
    if not isinstance(obj, dict):
        return ""
    if core:
        slim = {
            "date": obj.get("date"),
            "m": [{k: m.get(k) for k in CORE_FIELDS} for m in (obj.get("matches") or [])],
        }
    else:
        slim = {k: v for k, v in obj.items() if k not in SKIP_FIELDS}
    raw = json.dumps(slim, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def push_date(date: str, st: dict) -> bool:
    """推送某日数据：比分/状态变了才写，否则每 REFRESH_SEC 回刷一次赔率。"""
    full = live_server.live_for(date, light=False)
    if not full:
        print(f"[push] {date} 无数据，跳过")
        return False
    light = live_server.live_for(date, light=True)
    now = int(time.time())
    ok = True
    wrote = 0
    for suffix, obj in (("live", full), ("light", light)):
        if not obj:
            continue
        key = f"{suffix}/{date}.json"
        fp = _fingerprint(obj)
        stale = now - int(st["ts"].get(key, 0)) >= REFRESH_SEC
        if st["fp"].get(key) == fp and not stale:
            continue
        if st["writes"] >= DAILY_BUDGET:
            raise Quota(f"已达每日写入预算 {DAILY_BUDGET}")
        if _kv_write(key, obj):
            st["fp"][key] = fp
            st["ts"][key] = now
            st["writes"] += 1
            wrote += 1
            _save_state(st)
        else:
            ok = False
    if wrote:
        print(f"[push] {date}: 完整 {len(full.get('matches', []))} 场 / 写入 {wrote} 项"
              f" / 今日累计 {st['writes']} → {'OK' if ok else 'FAIL'}")
    return ok


def push_index(st: dict, *, force: bool = False) -> bool:
    """日期列表变了才推；否则每 REFRESH_SEC 回刷一次 updated 时间。"""
    dates = live_server.available_dates()
    idx = {"updated": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "dates": dates}
    fp = hashlib.md5(json.dumps(dates, ensure_ascii=False).encode("utf-8")).hexdigest()
    now = int(time.time())
    stale = now - int(st.get("index_ts", 0)) >= REFRESH_SEC
    if not force and st["fp"].get("index.json") == fp and not stale:
        return True
    if st["writes"] >= DAILY_BUDGET:
        raise Quota(f"已达每日写入预算 {DAILY_BUDGET}")
    if _kv_write("index.json", idx):
        st["fp"]["index.json"] = fp
        st["index_ts"] = now
        st["writes"] += 1
        _save_state(st)
        print(f"[push] index（{len(dates)} 天）→ OK / 今日累计 {st['writes']}")
        return True
    print("[push] index → FAIL")
    return False


def push_all(*, only_date: str | None = None, days: int = 2) -> bool:
    """推今天与明天的实时数据。

    免费版 KV 只有 1000 写/天，历史日期与更远未来由构建产物提供，
    不重复占配额；实时比分只在这两天有意义。
    """
    if only_date:
        targets = [only_date]
    else:
        today = dt.date.today()
        targets = [(today + dt.timedelta(days=i)).isoformat() for i in range(days)]
    st = _load_state()
    try:
        results = [push_date(d, st) for d in targets]
        results.append(push_index(st))
    except Quota as ex:
        print(f"[push] 停止本轮：{ex}", file=sys.stderr)
        _save_state(st)
        return False
    _save_state(st)
    return all(results)


def main() -> int:
    ap = argparse.ArgumentParser(description="Matlas 实时数据推送到 Cloudflare KV")
    ap.add_argument("--once", action="store_true", help="推一次后退出")
    ap.add_argument("--loop", action="store_true", help="常驻循环推送")
    ap.add_argument("--date", help="只推指定日期 YYYY-MM-DD")
    ap.add_argument("--interval", type=int, default=int(_env("PUSH_INTERVAL", "60")), help="循环间隔秒（默认 60）")
    ap.add_argument("--days", type=int, default=2, help="推送今天起 N 天（默认 2）")
    args = ap.parse_args()

    _load_dotenv()

    if args.loop:
        print(f"[push] 常驻模式，每 {args.interval}s 推送一次")
        while True:
            try:
                push_all(only_date=args.date, days=args.days)
            except Exception as ex:  # noqa: BLE001
                print(f"[push] 本轮异常: {ex}", file=sys.stderr)
            time.sleep(args.interval)
        return 0

    ok = push_all(only_date=args.date, days=args.days)
    print(f"[push] {'完成' if ok else '存在失败项'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
