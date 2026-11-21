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


def _get(query: str) -> dict:
    """直连优先，代理兜底。

    体彩接口公网直连可达；宿主代理（127.0.0.1:65053）常随会话关闭，
    强制走代理会在代理停止后静默拿不到任何数据。直连失败才回退代理。
    """
    req = urllib.request.Request(API + query, headers=HEADERS)
    proxy = (os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
             or "http://127.0.0.1:65053")
    openers = [
        urllib.request.build_opener(urllib.request.ProxyHandler({})),
        urllib.request.build_opener(
            urllib.request.ProxyHandler({"http": proxy, "https": proxy})),
    ]
    last = None
    for op in openers:
        try:
            with op.open(req, timeout=25) as resp:
                return json.loads(resp.read().decode("utf-8", "ignore"))
        except Exception as ex:  # noqa: BLE001
            last = ex
    raise last


def fetch_live() -> dict[str, dict]:
    """直播中/刚结束场次的真实状态、比分与分钟，按 matchId 索引。

    列表接口（getMatchDataPageListV1）对刚开赛场次的状态与比分更新滞后：
    20:30 开赛的场次在列表里仍是「10 待开奖 / 比分为空」，
    而本接口已给出「5 直播中 / 第 10 分钟 / 0:0」。以本接口为准。
    """
    try:
        data = _get("getMatchLiveV1.qry?channel=c")
    except Exception as ex:  # noqa: BLE001
        print(f"[live] 直播接口失败：{ex}")
        return {}
    out = {}
    for m in data.get("value") or []:
        out[str(m.get("matchId"))] = {
            "status": STATUS_MAP.get(str(m.get("matchStatus") or ""), ""),
            "status_text": str(m.get("matchStatusName") or ""),
            "minute": str(m.get("matchMinute") or "").strip(),
            "score": str(m.get("sectionsNo999") or "").strip(),
            "half": str(m.get("sectionsNo1") or "").strip(),
        }
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
    live = fetch_live()
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
            row = {
                "score": str(m.get("sectionsNo999") or ""),
                "half": str(m.get("sectionsNo1") or ""),
                "status": STATUS_MAP.get(raw_status, ""),
                "status_text": str(m.get("matchStatusName") or ""),
                "minute": "",
                "home": str(m.get("homeTeamAbbName") or ""),
                "away": str(m.get("awayTeamAbbName") or ""),
                "match_id": m.get("matchId"),
            }
            # 直播接口为准：覆盖状态/比分/半场/分钟（列表接口状态滞后）
            ov = live.get(str(m.get("matchId")))
            if ov:
                row.update(ov)
            rows[f"{date}|{num}"] = row
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
