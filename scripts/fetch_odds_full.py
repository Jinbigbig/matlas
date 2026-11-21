"""全玩法赔率采集器：直接抓体彩官方接口，写入 matlas 自己的 data/odds_full.json。

数据源：webapi.sporttery.cn getMatchCalculatorV1（含胜平负/让球/比分/总进球/半全场）。
与 jinbet 无关：不读、不写 jinbet 任何文件，不调用其脚本。

用法：
    python scripts/fetch_odds_full.py            # 采集一次
    python scripts/fetch_odds_full.py --dry-run  # 只打印统计，不写文件
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import traceback
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "odds_full.json"
LOG = ROOT / "data" / "odds_full.log"
API = "https://webapi.sporttery.cn/gateway/uniform/football/getMatchCalculatorV1.qry?channel=c"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
    "Referer": "https://www.sporttery.cn/jc/jsq/zqhhgg/",
    "Accept": "application/json, text/plain, */*",
}

# 比分 key（s00s00 → 0:0 ... s05s05 → 5:5，胜其他/平其他/负其他）
CRS = {f"s{h:02d}s{a:02d}": f"{h}:{a}" for h in range(6) for a in range(6)}
CRS.update({"s1sh": "胜其他", "s1sd": "平其他", "s1sa": "负其他"})
# 总进球 s0-s6 → 0-6，s7 → 7+
TTG = {f"s{i}": str(i) for i in range(7)}
TTG["s7"] = "7+"
# 半全场
HAFU = {
    "hh": "胜胜", "hd": "胜平", "ha": "胜负",
    "dh": "平胜", "dd": "平平", "da": "平负",
    "ah": "负胜", "ad": "负平", "aa": "负负",
}


def _num(v) -> str:
    """保留赔率原始字符串，过滤空/0。"""
    s = str(v or "").strip()
    if not s:
        return ""
    try:
        return s if float(s) > 0 else ""
    except ValueError:
        return ""


def _opener():
    """体彩接口在本机需走 WorkBuddy 本地代理（127.0.0.1:65053），
    无代理直连返回 HTTP 567；计划任务环境不继承会话代理变量，故显式 fallback。"""
    proxy = (os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
             or "http://127.0.0.1:65053")
    return urllib.request.build_opener(urllib.request.ProxyHandler({"http": proxy, "https": proxy}))


def fetch() -> str:
    req = urllib.request.Request(API, headers=HEADERS)
    with _opener().open(req, timeout=30) as resp:
        return resp.read().decode("utf-8")


def parse(text: str) -> dict[str, dict]:
    """返回 {date_code: 全玩法赔率}；date_code 形如 2026-11-21_周六005。"""
    payload = json.loads(text)
    if not payload.get("success"):
        raise RuntimeError(f"接口返回失败: {payload.get('errorMessage')}")
    out: dict[str, dict] = {}
    for day in payload.get("value", {}).get("matchInfoList", []):
        business_date = day.get("businessDate", "")
        for m in day.get("subMatchList", []):
            code = str(m.get("matchNumStr") or "").strip()
            if not business_date or not code:
                continue
            key = f"{business_date}_{code}"

            had = m.get("had") or {}
            hhad = m.get("hhad") or {}
            spf = {"胜": _num(had.get("h")), "平": _num(had.get("d")), "负": _num(had.get("a"))}

            rq = []
            handicap = hhad.get("goalLine") or hhad.get("goalLineValue") or ""
            if handicap and any(_num(hhad.get(k)) for k in ("h", "d", "a")):
                rq.append({
                    "handicap": str(handicap),
                    "胜": _num(hhad.get("h")),
                    "平": _num(hhad.get("d")),
                    "负": _num(hhad.get("a")),
                })

            def mapped(src: dict, table: dict) -> dict[str, str]:
                return {label: _num(src.get(k)) for k, label in table.items() if _num(src.get(k))}

            out[key] = {
                "spf": spf,
                "rq": rq,
                "score": mapped(m.get("crs") or {}, CRS),
                "goals": mapped(m.get("ttg") or {}, TTG),
                "htft": mapped(m.get("hafu") or {}, HAFU),
            }
    return out


def log(msg: str) -> None:
    line = f"{dt.datetime.now():%Y-%m-%d %H:%M:%S} {msg}"
    print(line)
    try:
        with LOG.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def main() -> int:
    ap = argparse.ArgumentParser(description="matlas 全玩法赔率采集器")
    ap.add_argument("--dry-run", action="store_true", help="只统计不写文件")
    args = ap.parse_args()

    try:
        data = parse(fetch())
    except Exception as ex:  # noqa: BLE001
        log(f"采集失败: {type(ex).__name__}: {ex}")
        try:
            with LOG.open("a", encoding="utf-8") as f:
                f.write(traceback.format_exc())
        except OSError:
            pass
        return 1

    payload = {
        "updated": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source": "sporttery getMatchCalculatorV1",
        "count": len(data),
        "data": data,
    }
    if args.dry_run:
        sample = next(iter(data.values()), {})
        print(f"[odds_full] 采集 {len(data)} 场（未写入）")
        print(f"[odds_full] 样本: {json.dumps(sample, ensure_ascii=False)[:300]}")
        return 0

    try:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        tmp = OUT.with_suffix(f".{dt.datetime.now():%H%M%S}.tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        tmp.replace(OUT)
    except Exception as ex:  # noqa: BLE001
        log(f"写入失败: {type(ex).__name__}: {ex}")
        return 1
    log(f"写入 {len(data)} 场, updated={payload['updated']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
