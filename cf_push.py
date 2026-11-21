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
    """PUT 一个 JSON 值到 CF KV。返回是否成功。"""
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
    except Exception as ex:  # noqa: BLE001
        print(f"[push] KV 写入失败 {key}: {ex}", file=sys.stderr)
        return False


def push_date(date: str) -> bool:
    """生成并推送某日的完整版 + 轻量版 + 更新 index。"""
    full = live_server.live_for(date, light=False)
    if not full:
        print(f"[push] {date} 无数据，跳过")
        return False
    light = live_server.live_for(date, light=True)
    ok1 = _kv_write(f"live/{date}.json", full)
    ok2 = _kv_write(f"light/{date}.json", light) if light else True
    print(f"[push] {date}: 完整 {len(full.get('matches', []))} 场 / "
          f"轻量 {len((light or {}).get('matches', []))} 场 → "
          f"{'OK' if ok1 and ok2 else 'FAIL'}")
    return ok1 and ok2


def push_index() -> bool:
    dates = live_server.available_dates()
    idx = {
        "updated": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "dates": dates,
    }
    ok = _kv_write("index.json", idx)
    print(f"[push] index（{len(dates)} 天）→ {'OK' if ok else 'FAIL'}")
    return ok


def push_all(*, only_date: str | None = None, days: int = 3) -> bool:
    """推送最近 N 天（覆盖比赛列表跨日显示），再写 index。"""
    if only_date:
        targets = [only_date]
    else:
        dates = live_server.available_dates()
        # 加上 fixtures 里当天有赛程但尚未 import 的日期
        fx_days = ((live_server._read(live_server.FIXTURES) or {}).get("days")) or {}
        today = dt.date.today().isoformat()
        all_dates = sorted(set(dates) | set(fx_days.keys()))
        targets = [d for d in all_dates if d >= (dt.date.today() - dt.timedelta(days=days - 1)).isoformat()]
        if today not in targets:
            targets.append(today)
    results = [push_date(d) for d in sorted(set(targets))]
    results.append(push_index())
    return all(results)


def main() -> int:
    ap = argparse.ArgumentParser(description="Matlas 实时数据推送到 Cloudflare KV")
    ap.add_argument("--once", action="store_true", help="推一次后退出")
    ap.add_argument("--loop", action="store_true", help="常驻循环推送")
    ap.add_argument("--date", help="只推指定日期 YYYY-MM-DD")
    ap.add_argument("--interval", type=int, default=int(_env("PUSH_INTERVAL", "60")), help="循环间隔秒（默认 60）")
    ap.add_argument("--days", type=int, default=3, help="推送最近 N 天（默认 3）")
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
