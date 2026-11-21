"""体彩官方比分直播采集：补半场比分、实时状态与进行中分钟。

接口与赔率同域（webapi.sporttery.cn），容器出口被拒（HTTP 567），
故跟随 collect_lottery 在宿主侧调度。

  getMatchDataPageListV1  比赛列表：队名 / 全场比分 / 半场 / 状态（一次覆盖 8 天）
  getMatchLiveV1          直播中比赛：比赛分钟（队名字段为空，按 matchId 关联）

输出 data/live_scores.json：
  {"updated": "...", "count": n, "matches": {"<日期>|<竞彩编号>": {...}}}
"""
from __future__ import annotations

import pathlib as _pathlib

ROOT = _pathlib.Path(__file__).resolve().parent.parent.parent  # matlas 根

import datetime as dt
import json
import os
import urllib.request

OUT = ROOT / "data" / "live_scores.json"
API = "https://webapi.sporttery.cn/gateway/uniform/fb/"
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"),
    "Referer": "https://www.sporttery.cn/jc/zqbfzb/",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9",
}

# 体彩状态码 → 站内三态（未开赛 / 进行中 / 已结束）
STATUS_MAP = {
    "5": "进行中",
    "6": "已结束",
    "10": "已结束",
    "11": "已结束",
    "2": "未开赛",
    "4": "未开赛",
}


def _opener():
    """体彩接口需走本地代理，计划任务环境不继承会话变量，显式 fallback。"""
    proxy = (os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
             or "http://127.0.0.1:65053")
    return urllib.request.build_opener(
        urllib.request.ProxyHandler({"http": proxy, "https": proxy}))


def _get(query: str) -> dict:
    req = urllib.request.Request(API + query, headers=HEADERS)
    with _opener().open(req, timeout=25) as resp:
        return json.loads(resp.read().decode("utf-8", "ignore"))


def fetch_minutes() -> dict[str, str]:
    """直播中比赛的分钟数，按 matchId 建索引；该接口不给队名。"""
    try:
        data = _get("getMatchLiveV1.qry?channel=c")
    except Exception as ex:  # noqa: BLE001
        print(f"[live] 分钟接口失败：{ex}")
        return {}
    out = {}
    for m in data.get("value") or []:
        minute = str(m.get("matchMinute") or "").strip()
        if minute:
            out[str(m.get("matchId"))] = minute
    return out


def fetch_list() -> dict | None:
    """一次取回最近 8 天比赛（当前接口 pageNo=1 即全量，翻页返回空）。"""
    try:
        data = _get("getMatchDataPageListV1.qry?channel=c&pageSize=30&pageNo=1")
    except Exception as ex:  # noqa: BLE001
        print(f"[live] 列表接口失败：{ex}")
        return None
    if not data.get("success"):
        print(f"[live] 列表接口返回失败：{data.get('errorMessage')}")
        return None
    return data.get("value") or {}


def build() -> dict | None:
    minutes = fetch_minutes()
    value = fetch_list()
    if value is None:
        return None
    rows: dict[str, dict] = {}
    for day in value.get("matchInfoList") or []:
        for m in day.get("subMatchList") or []:
            date = str(m.get("businessDate") or m.get("matchDate") or "")
            num = str(m.get("matchNumStr") or "").strip()
            if not date or not num:
                continue
            raw_status = str(m.get("matchStatus") or "")
            rows[f"{date}|{num}"] = {
                "score": str(m.get("sectionsNo999") or ""),
                "half": str(m.get("sectionsNo1") or ""),
                "status": STATUS_MAP.get(raw_status, ""),
                "status_text": str(m.get("matchStatusName") or ""),
                "minute": minutes.get(str(m.get("matchId")), ""),
                "home": str(m.get("homeTeamAbbName") or ""),
                "away": str(m.get("awayTeamAbbName") or ""),
                "match_id": m.get("matchId"),
            }
    if not rows:
        return None
    return {
        "updated": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "count": len(rows),
        "matches": rows,
    }


def main() -> int:
    payload = build()
    if not payload:
        print("[live] 本轮无数据，保留原文件")
        return 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                   encoding="utf-8")
    live = sum(1 for v in payload["matches"].values() if v["status"] == "进行中")
    scored = sum(1 for v in payload["matches"].values() if v["score"])
    print(f"[live] {payload['count']} 场（进行中 {live} / 有比分 {scored}）→ {OUT.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
