#!/usr/bin/env python3
"""jinbet 历史数据 → matlas data/days/*.json 一次性导入器。

来源（只读）：
  C:/Users/Jin/jinbet/predictions/{date}/pred_snapshot.json   每日预测快照
  C:/Users/Jin/jinbet/results_history/{date}.json             赛果回填（key: {date}_{主}_{客}）
  C:/Users/Jin/jinbet/results_data.json                      赛果回填回退源（归档缺失的日期）

映射规则（宁缺勿错，缺的槽位留空，渲染层自动降级）：
  code      <- id（周三001）            match_id <- {date}-{三位编号}
  forecasts <- prob_home/draw/away（方向 3 条）+ top_scores（比分前 6）
  odds      <- odds.胜/平/负；让球 <- rq_handicap / rq_best_pick / rq_best_odds
  result    <- results_history 按 matchNumStr，再按（主,客）名兜底；
               direction_hit / score_hit 由此计算
  其余（六维雷达 / 动量 / 近况 / 伤停）jinbet 快照没有，一律不造假留空。

用法：python import_jinbet.py [--dry-run]
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

PRED_DIR = Path("C:/Users/Jin/jinbet/predictions")
RES_DIR = Path("C:/Users/Jin/jinbet/results_history")
# 引擎全量赛果库（results_history 归档缺失时回退）：key = {date}_{主}_{客}
RESULTS_DATA_JSON = Path("C:/Users/Jin/jinbet/results_data.json")
ODDS_JSON = Path("C:/Users/Jin/jinbet/odds_data.json")
# 网易竞彩赛程开赛时间（jinbet/_fetch_match_times.py 抓取维护）
MATCH_TIMES_JSON = Path("C:/Users/Jin/jinbet/match_times.json")
# 赛前环境三件套（jinbet/_fetch_* 产出，缺失自动跳过）
INJURIES_JSON = Path("C:/Users/Jin/jinbet/injuries.json")
WEATHER_JSON = Path("C:/Users/Jin/jinbet/weather.json")
REFEREE_JSON = Path("C:/Users/Jin/jinbet/referee.json")
_results_data_cache: dict | None = None
OUT_DIR = Path("C:/Users/Jin/matlas/data/days")

# ---- jinbet 侧成熟数据源（赛前信息 / 积分分析）----
# qq_standings.json：腾讯体育积分榜（欧冠/英超/意甲/德甲/西甲），rank/p/w/d/l/pts
STANDINGS_JSON = Path("C:/Users/Jin/jinbet/qq_standings.json")
# fox_standings.json：fox 体育积分榜（欧罗巴/解放者杯），groups[].teams[] 分组结构
FOX_STANDINGS_JSON = Path("C:/Users/Jin/jinbet/fox_standings.json")
# uefa_standings.json：欧协联积分榜，同 fox 的分组结构
UEFA_STANDINGS_JSON = Path("C:/Users/Jin/jinbet/uefa_standings.json")
# scripts/matches_data.json：网易当日抓取，home_recent 等 gf/ga 近况序列
MATCHES_DATA_JSON = Path("C:/Users/Jin/jinbet/scripts/matches_data.json")

# 竞彩短名 → 积分榜行键（腾讯榜全名 / fox·uefa 榜中文名）。宁缺勿错：只收已核实条目，
# 匹配不到就不填积分。fox/uefa 的行键是中文简称（zh 字段），如「尤文」「格拉茨风暴」。
TEAM_ALIAS = {
    "巴黎圣曼": "巴黎圣日耳曼", "巴黎": "巴黎圣日耳曼", "维拉": "阿斯顿维拉",
    "拜仁": "拜仁慕尼黑", "布伦特": "布伦特福德", "纽卡斯尔": "纽卡斯尔联",
    "诺丁汉": "诺丁汉森林", "伊普斯": "伊普斯维奇", "加拉塔萨": "加拉塔萨雷",
    "毕尔巴鄂": "毕尔巴鄂竞技", "比利亚雷": "比利亚雷亚尔", "拉科": "拉科鲁尼亚",
    "门兴": "门兴格拉德巴赫", "桑坦德": "桑坦德竞技", "莱红牛": "RB莱比锡",
    "皇馬": "皇家马德里", "巴萨": "巴塞罗那", "马竞": "马德里竞技",
    # ---- fox 欧罗巴 ----
    "尤文图斯": "尤文", "格风暴": "格拉茨风暴", "波兹南": "波兹南莱赫",
    "萨迪纳摩": "萨格勒布迪纳摩", "贝西克塔": "贝西克塔斯", "安德莱": "安德莱赫特",
    "奥林匹亚": "奥林匹亚科斯", "圣吉联合": "圣吉尔联", "利勒斯特": "利勒斯特罗姆",
    "克里特": "OFI克里特", "阿尔克马": "阿尔克马尔",
    # ---- uefa 欧协联 ----
    "克拉约瓦": "克拉约瓦大学",
    # ---- fox 解放者杯 ----
    "基多体大": "基多大学", "帕梅拉斯": "帕尔梅拉斯", "弗鲁米嫩": "弗鲁米嫩塞",
    "德尔瓦耶独立": "山谷独立", "普拉滕斯": "普拉滕塞", "拉普大学": "大学生",
}

# 联赛名归一：与 matlas 既有叫法/队徽映射（logos.LEAGUE_CREST）对齐。
LEAGUE_ALIAS = {
    "日职": "日职联",
    "日乙": "日职乙",
    "韩职": "韩K联",
    "英联赛杯": "英联杯",
    "沙职": "沙特联",
    "美职": "美职联",
}

# 结果文件里未必与预测侧完全同名的球队，不做模糊匹配——精确匹配不到就当没赛果。
_NAME_NORM = str.strip


def _load_standings() -> dict[str, dict[str, dict]]:
    """积分榜聚合 → {联赛: {队名: row}}，三源合并：

    - 腾讯 qq_standings（欧冠/英超/意甲/德甲/西甲），行键=全名；
    - fox（欧罗巴/解放者杯）、uefa（欧协联）分组结构，行键=中文简称 zh
      （zh 为空的行宁缺勿错直接跳过）。
    某个文件缺失/损坏时该来源置空，不影响其余来源。
    """
    out: dict[str, dict[str, dict]] = {}

    def _merge(lg: str, row: dict, key: str) -> None:
        if lg and key and isinstance(row, dict):
            out.setdefault(lg, {})[key] = row

    try:
        d = json.loads(STANDINGS_JSON.read_text(encoding="utf-8"))
        for lg, v in (d.get("leagues") or {}).items():
            for t in v.get("teams") or []:
                _merge(lg, t, t.get("name") or "")
    except (OSError, ValueError):
        pass
    for path in (FOX_STANDINGS_JSON, UEFA_STANDINGS_JSON):
        try:
            d = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for lg, v in (d.get("leagues") or {}).items():
            for g in v.get("groups") or []:
                for t in g.get("teams") or []:
                    _merge(lg, t, t.get("zh") or "")
    return out


def _load_net_form() -> dict[str, dict]:
    """网易当日近况 → {编号(周四001): {home_7/home_home/away_7/away_away: [gf/ga]}}。

    只取「当天」的 matches_data.json（临时文件会被每日覆盖），历史天没有存档，
    因此只有最新一个交易日的场次带这份赛前状态，其余天留空降级。
    """
    try:
        d = json.loads(MATCHES_DATA_JSON.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    out = {}
    for m in d.get("matches") or []:
        num = str(m.get("matchNumStr", "")).strip()
        if not num:
            continue
        out[num] = {
            "home_7": m.get("home_recent") or [],
            "home_home": m.get("home_recent_home") or [],
            "away_7": m.get("away_recent") or [],
            "away_away": m.get("away_recent_away") or [],
        }
    return out


def _f(v) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _parse_handicap(v) -> float | None:
    """'-1' / '+0.5' -> float；中文盘口（半一 etc.）解析不了就返回 None。"""
    if not isinstance(v, str):
        return None
    v = v.strip().replace("＋", "+").replace("－", "-")
    return _f(v)


def _score_fmt(s: str) -> str:
    return (s or "").replace(":", "-").strip()


def _load_results(date: str) -> dict:
    """当日赛果：优先 results_history/{date}.json（按日归档，历史稳定）；

    归档缺失的日期（如近期尚未跑归档）回退 results_data.json —— 引擎维护的
    全量赛果库（key: {date}_{主}_{客}，每日刷新），按日期前缀过滤出当日记录。
    """
    p = RES_DIR / f"{date}.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    global _results_data_cache
    if _results_data_cache is None:
        try:
            _results_data_cache = json.loads(RESULTS_DATA_JSON.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            _results_data_cache = {}
    return {k: v for k, v in _results_data_cache.items() if k.startswith(f"{date}_")}


def _result_index(raw: dict) -> tuple[dict[str, dict], dict[tuple[str, str], dict]]:
    by_code: dict[str, dict] = {}
    by_name: dict[tuple[str, str], dict] = {}
    for rec in raw.values():
        if not isinstance(rec, dict):
            continue
        code = str(rec.get("matchNumStr", "")).strip()
        if code:
            by_code.setdefault(code, rec)
        by_name.setdefault((_NAME_NORM(rec.get("home", "")), _NAME_NORM(rec.get("away", ""))), rec)
    return by_code, by_name


def _ensure_results_cache() -> dict:
    """results_data.json 全量赛果库缓存（H2H 与 history 池共用）。"""
    global _results_data_cache
    if _results_data_cache is None:
        try:
            _results_data_cache = json.loads(RESULTS_DATA_JSON.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            _results_data_cache = {}
    return _results_data_cache


def _h2h_index() -> dict:
    """历史交锋索引：全量赛果库按两队无序对聚合，日期升序。"""
    idx: dict[tuple[str, str], list[dict]] = {}
    for key, rec in _ensure_results_cache().items():
        if not isinstance(rec, dict):
            continue
        try:
            gf, ga = (int(x) for x in str(rec.get("fullScore", "")).split(":"))
        except ValueError:
            continue
        h, a = _NAME_NORM(rec.get("home", "")), _NAME_NORM(rec.get("away", ""))
        if not h or not a:
            continue
        idx.setdefault(tuple(sorted((h, a))), []).append({
            "date": key.split("_", 1)[0],
            "competition": str(rec.get("league", "")),
            "home": str(rec.get("home", "")),
            "away": str(rec.get("away", "")),
            "gf": gf, "ga": ga,
        })
    for v in idx.values():
        v.sort(key=lambda e: e["date"])
    return idx


def _history_pool() -> list[dict]:
    """历史赛果池（喂给六维战力 power.compute 做先例样本，含去水胜率）。"""
    out: list[dict] = []
    for key, rec in _ensure_results_cache().items():
        if not isinstance(rec, dict):
            continue
        try:
            gf, ga = (int(x) for x in str(rec.get("fullScore", "")).split(":"))
        except ValueError:
            continue
        try:
            oh, od, oa = float(rec.get("胜")), float(rec.get("平")), float(rec.get("负"))
        except (TypeError, ValueError):
            oh = od = oa = None
        if oh and od and oa:
            s = 1 / oh + 1 / od + 1 / oa
            ph, pa = (1 / oh) / s, (1 / oa) / s
        else:
            ph = pa = None
        out.append({
            "date": key.split("_", 1)[0],
            "competition": str(rec.get("league", "")),
            "home": str(rec.get("home", "")),
            "away": str(rec.get("away", "")),
            "gf": gf, "ga": ga, "ph": ph, "pa": pa,
        })
    return out


def _direction_hit(top_label: str, win_flag: str) -> bool | None:
    if not top_label or not win_flag:
        return None
    want = {"主胜": "H", "平": "D", "客胜": "A"}.get(top_label.strip())
    return None if want is None else want == win_flag


def _load_env() -> dict:
    """赛前环境：伤停（按队）/ 天气（按编号）/ 裁判（对阵模糊匹配）。

    各 json 均为当日快照，附带日期防错配：天气/伤停仅注入 date==快照日；
    裁判文章提前 1-3 天发布，注入 ref_date 与场次日期差 ≤2 天的场次。
    """
    env: dict = {"inj": {}, "weather": {}, "refs": []}

    def _read(p: Path):
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return None

    d = _read(INJURIES_JSON)
    if d:
        env["inj"] = d.get("teams") or {}
        env["env_date"] = str(d.get("updated", ""))[:10]
    d = _read(WEATHER_JSON)
    if d:
        env["weather"] = d.get("matches") or {}
        env["weather_date"] = str(d.get("date", ""))[:10]
    d = _read(REFEREE_JSON)
    if d:
        env["refs"] = d.get("matches") or []
        env["ref_date"] = str(d.get("updated", ""))[:10]
    return env


def _name_match(a: str | None, b: str | None) -> bool:
    """队名双向包含匹配（竞彩简称 ↔ 文章全/简称）。"""
    return bool(a and b and len(a) >= 2 and len(b) >= 2 and (a in b or b in a))


def convert_match(date: str, m: dict, by_code: dict, by_name: dict,
                  standings: dict | None = None,
                  net_form: dict | None = None,
                  odds_idx: dict | None = None,
                  times_idx: dict | None = None,
                  times_days: set | None = None,
                  env: dict | None = None,
                  h2h_idx: dict | None = None) -> dict:
    standings = standings or {}
    net_form = net_form or {}
    code = str(m.get("id", "")).strip()
    num = re.search(r"(\d+)$", code)
    match_id = f"{date}-{int(num.group(1)):03d}" if num else ""

    league = LEAGUE_ALIAS.get(m.get("league", ""), m.get("league", ""))
    home = str(m.get("home", "")).strip()
    away = str(m.get("away", "")).strip()

    # ---- 方向预测：胜/平/负三条，按概率降序排 rank ----
    dir_items = [
        ("主胜", _f(m.get("prob_home"))),
        ("平", _f(m.get("prob_draw"))),
        ("客胜", _f(m.get("prob_away"))),
    ]
    forecasts = []
    for i, (lab, p) in enumerate(sorted(
            [(l, p) for l, p in dir_items if p is not None],
            key=lambda x: -x[1]), 1):
        forecasts.append({"kind": "direction", "label": lab, "prob": round(p / 100, 4), "rank": i})
    top_dir = next((f["label"] for f in forecasts if f["rank"] == 1), "")

    # ---- 比分预测：top_scores 前 6 ----
    top_scores = [x for x in (m.get("top_scores") or []) if isinstance(x, dict)]
    top_score_label = ""
    goals_prob: dict[int, float] = {}
    for i, x in enumerate(top_scores[:6], 1):
        lab = _score_fmt(str(x.get("score", "")))
        p = _f(x.get("prob"))
        if not lab or p is None:
            continue
        if i == 1:
            top_score_label = lab
        forecasts.append({"kind": "score", "label": lab, "prob": round(p / 100, 4), "rank": i})
    # ---- 进球数预测：由同一比分分布聚合总进球（真实推导，非造假）----
    for x in top_scores:
        s = str(x.get("score", ""))
        p = _f(x.get("prob"))
        if ":" in s and p is not None:
            try:
                g = int(s.split(":")[0]) + int(s.split(":")[1])
                goals_prob[g] = goals_prob.get(g, 0.0) + p
            except (ValueError, IndexError):
                pass
    for i, (g, p) in enumerate(sorted(goals_prob.items(), key=lambda x: -x[1])[:3], 1):
        forecasts.append({"kind": "goals", "label": f"{g} 球", "prob": round(p / 100, 4), "rank": i})

    # ---- 半全场预测：htft.top 前 3（2026-10-22 起引擎输出）----
    # htft = {"half": {home/draw/away 半场概率}, "cells": {"主/主": 概率...},
    #         "top": [["客/客", 32.6], ...]}；概率为百分数，归一为小数。
    htft = m.get("htft") if isinstance(m.get("htft"), dict) else {}
    top_htft = ""
    for i, item in enumerate(htft.get("top") or [], 1):
        if not isinstance(item, (list, tuple)) or len(item) < 2:
            continue
        lab, p = str(item[0]).strip(), _f(item[1])
        if not lab or p is None:
            continue
        if i == 1:
            top_htft = lab
        forecasts.append({"kind": "htft", "label": lab, "prob": round(p / 100, 4), "rank": i})

    # ---- 赔率 ----
    raw_odds = m.get("odds") or {}
    odds: dict = {}
    for k, src in (("home", "胜"), ("draw", "平"), ("away", "负")):
        v = _f(raw_odds.get(src))
        if v:
            odds[k] = v
    spread = _parse_handicap(m.get("rq_handicap"))
    if spread is not None:
        odds["handicap"] = spread
    pick = str(m.get("rq_best_pick", "")).strip()
    # rq_best_odds 是「我们选边的结论赔率」，与市场盘口赔率不同口径，
    # 不放进 odds（市场表），改由 handicap 槽位/extras 承载，避免误导。

    # ---- 赛果 ----
    rec = by_code.get(code) or by_name.get((home, away))
    result = None
    if rec:
        full = _score_fmt(str(rec.get("fullScore", "")))
        half = _score_fmt(str(rec.get("halfScore", "")))
        win_flag = str(rec.get("winFlag", "")).strip()
        # goals_hit：首选总进球 vs 实际总进球（fullScore "3-2" -> 5 球）
        top_goals = next(
            (f["label"] for f in forecasts if f["kind"] == "goals" and f["rank"] == 1), "")
        goals_hit = None
        if top_goals and "-" in full:
            try:
                gh, ga = (int(x) for x in full.split("-"))
                goals_hit = top_goals == f"{gh + ga} 球"
            except ValueError:
                pass
        # htft_hit：首选半全场（如 "客/客"）vs 实际半全场。
        # 实际由 halfScore/fullScore 推：半场主>客=主 …；全场同规则。
        htft_hit = None
        if top_htft and "-" in full and "-" in half:
            try:
                fh, fa = (int(x) for x in half.split("-"))
                sh, sa = (int(x) for x in full.split("-"))
                def _side(a: int, b: int) -> str:
                    return "主" if a > b else ("客" if a < b else "平")
                htft_hit = top_htft == f"{_side(fh, fa)}/{_side(sh, sa)}"
            except ValueError:
                pass
        if full:
            result = {
                "full_score": full,
                "half_score": half,
                "direction_hit": _direction_hit(top_dir, win_flag),
                "score_hit": (top_score_label == full) if top_score_label else None,
                "goals_hit": goals_hit,
                "htft_hit": htft_hit,
                "settled_at": date,
            }

    # ---- 置信度：stars 1-5 -> high/medium/low ----
    stars = m.get("stars") or 0
    confidence = {5: "high", 4: "high", 3: "medium", 2: "low", 1: "low"}.get(int(stars), "none")

    extras = {}
    for k in ("lam_home", "lam_away", "lam_total", "upset_prob", "upset_level",
              "rq_best_ev", "rq_best_odds"):
        if m.get(k) is not None:
            extras[k] = m[k]
    if m.get("data_n"):
        extras["data_n"] = m["data_n"]
    if m.get("headline"):
        extras["headline"] = m["headline"]
    if htft:
        if isinstance(htft.get("half"), dict):
            extras["htft_half"] = htft["half"]   # 半场胜平负概率（百分数）
        if isinstance(htft.get("cells"), dict):
            extras["htft_cells"] = htft["cells"]  # 九选项概率（百分数）
    # 网易赛前状态（仅当日场次有）：近 7 场 / 近 7 同主客场的进失球序列
    if code in net_form:
        extras["form_net"] = net_form[code]
    # 竞彩全玩法赔率快照（胜平负/让球多行/比分/总进球/半全场），赔率页与投注页用
    kickoff = ""
    if odds_idx:
        of = odds_idx.get((date, code)) or odds_idx.get((date, home, away))
        if of:
            extras["odds_full"] = of
            kickoff = str(of.get("kickoff", "") or "")
    # 网易赛程开赛时间（match_times.json）优先，仅套用窗口内日期
    if times_idx and date in (times_days or set()):
        kickoff = str(times_idx.get(code, "") or "") or kickoff
    # 赛前环境：伤停（按队名）/ 天气（按编号）/ 裁判（对阵模糊匹配），仅当日/近2日
    if env:
        same_day = env.get("env_date") == date
        if same_day:
            inj = env.get("inj") or {}
            hi, ai = inj.get(home), inj.get(away)
            if hi or ai:
                extras["injuries"] = {"home": hi or None, "away": ai or None}
        if env.get("weather_date") == date:
            w = (env.get("weather") or {}).get(code)
            if w:
                extras["weather"] = {k: w[k] for k in
                                     ("t_min", "t_max", "pop", "rain", "wind", "grade", "city")
                                     if k in w}
        try:
            from datetime import date as _dd
            ref_ok = env.get("ref_date") and abs(
                (_dd.fromisoformat(date) - _dd.fromisoformat(env["ref_date"])).days) <= 2
        except Exception:
            ref_ok = False
        if ref_ok:
            for r in env.get("refs") or []:
                if _name_match(r.get("home"), home) and _name_match(r.get("away"), away):
                    nat = str(r.get("nation") or "").rstrip("籍") or None
                    extras["referee"] = {k: r[k] for k in
                                         ("ref", "age", "h", "d", "a",
                                          "yellow", "red", "pen")
                                         if r.get(k) is not None}
                    if nat:
                        extras["referee"]["nation"] = nat
                    break
    def _team_side(name: str) -> dict:
        """队侧槽位：积分榜命中则填 rank/points/played/win/draw/loss。"""
        side = {"name": name, "league": league}
        row = standings.get(league, {}).get(name) \
            or standings.get(league, {}).get(TEAM_ALIAS.get(name, ""))
        if row:
            side.update({
                "rank": row.get("rank"), "points": row.get("pts"),
                "played": row.get("p"), "win": row.get("w"),
                "draw": row.get("d"), "loss": row.get("l"),
            })
        return side

    out = {
        "match_id": match_id,
        "day": date,
        "code": code,
        "competition": league,
        "kickoff": kickoff,
        "home": _team_side(home),
        "away": _team_side(away),
        "forecasts": forecasts,
        "confidence": confidence,
        "is_cold_start": bool(m.get("cold")),
        "extras": extras,
    }
    if odds:
        out["odds"] = odds
    if pick and spread is not None:
        out["handicap"] = {"spread": spread, "pick": pick, "prob": None, "hit": None}
    if result:
        out["result"] = result
    # 顶层伤停列表（单场页 _injury_panel 按此渲染；extras 里的结构化副本供其他页用）
    inj_rows = []
    inj_ex = extras.get("injuries") or {}
    for side_key, status in (("home", "out"), ("away", "out")):
        side = inj_ex.get(side_key) or {}
        for p in side.get("out") or []:
            inj_rows.append({"team": side_key, "player": str(p.get("name", "")),
                             "reason": str(p.get("reason", "")), "status": status})
        for p in side.get("doubtful") or []:
            inj_rows.append({"team": side_key, "player": str(p.get("name", "")),
                             "reason": str(p.get("reason", "")), "status": "doubt"})
    if inj_rows:
        out["injuries"] = inj_rows
    # 历史交锋：全量赛果库中两队交手记录（任意主客，按当时主客呈现），本场前最近 5 场
    if h2h_idx:
        pair = tuple(sorted((_NAME_NORM(home), _NAME_NORM(away))))
        meets = [e for e in h2h_idx.get(pair, []) if e["date"] < date]
        if meets:
            out["h2h"] = [{"date": e["date"], "competition": e["competition"],
                           "home": e["home"], "away": e["away"],
                           "score": f'{e["gf"]}-{e["ga"]}'} for e in meets[-5:]]
    return out


def _load_match_times() -> tuple[set, dict]:
    """开赛时间索引（match_times.json，编号 -> ko 完整时间）。

    times 仅以编号（周X001）为键、跨周会重复，因此只允许套用在
    payload.date ± 1 天内的场次，防跨周脏数据。
    """
    try:
        d = json.loads(MATCH_TIMES_JSON.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set(), {}
    import datetime as _dt

    base = _dt.date.fromisoformat(str(d.get("date", "")))
    days = {str(base + _dt.timedelta(days=off)) for off in (-1, 0, 1)}
    times = {str(k): str((v or {}).get("ko", ""))
             for k, v in (d.get("times") or {}).items()}
    return days, times


def _load_odds_index() -> dict[tuple, dict]:
    """竞彩全玩法赔率（odds_data.json，jinbet/update_odds_net.py 抓取维护）。

    键：(日期, 周X编号) 主键 + (日期, 主队, 客队) 回退键；值为
    {spf: 胜平负, rq: 让球多行, score: 全部比分, goals: 总进球, htft: 半全场}。
    """
    try:
        d = json.loads(ODDS_JSON.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    idx: dict[tuple, dict] = {}
    for item in (d.get("data") or {}).values():
        dk = str(item.get("date_key", ""))
        date, _, rest = dk.partition("_")
        if len(date) != 10 or not rest:
            continue
        names = rest.split("_")
        entry = {
            "spf": {"胜": item.get("胜"), "平": item.get("平"), "负": item.get("负")},
            "rq": item.get("让球") or [],
            "score": item.get("比分") or {},
            "goals": item.get("总进球") or {},
            "htft": item.get("半全场") or {},
            "kickoff": str(item.get("matchTime", "") or "")[:5],
        }
        num = str(item.get("matchNumStr", "")).strip()
        if num:
            idx[(date, num)] = entry
        if len(names) >= 2:
            idx[(date, names[0], names[1])] = entry
    return idx


def main() -> None:
    dry = "--dry-run" in sys.argv
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    standings = _load_standings()
    net_form = _load_net_form()
    odds_idx = _load_odds_index()
    times_days, times_idx = _load_match_times()
    env = _load_env()
    h2h_idx = _h2h_index()
    history = _history_pool()
    n_days = n_matches = n_results = 0
    for d in sorted(PRED_DIR.iterdir()):
        if len(d.name) != 10 or not d.is_dir():
            continue
        snap = d / "pred_snapshot.json"
        if not snap.exists():
            continue
        s = json.loads(snap.read_text(encoding="utf-8"))
        date = str(s.get("date", d.name))
        by_code, by_name = _result_index(_load_results(date))
        matches = []
        seen: set[str] = set()
        for i, m in enumerate(s.get("matches", [])):
            cm = convert_match(date, m, by_code, by_name,
                               standings=standings, net_form=net_form,
                               odds_idx=odds_idx,
                               times_idx=times_idx, times_days=times_days,
                               env=env, h2h_idx=h2h_idx)
            if not cm["match_id"] or cm["match_id"] in seen:
                cm["match_id"] = f"{date}-{i + 1:03d}"
            seen.add(cm["match_id"])
            if cm.get("result"):
                n_results += 1
            matches.append(cm)
        day = {
            "date": date,
            "note": "数据源：jinbet 每日预测快照，赛果赛后回填。",
            "matches": matches,
        }
        n_days += 1
        n_matches += len(matches)
        if not dry:
            (OUT_DIR / f"{date}.json").write_text(
                json.dumps(day, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
            )
        print(f"{date}: {len(matches)} 场 / 回填赛果 {sum(1 for x in matches if x.get('result'))}")
    if not dry:
        # 历史赛果池（六维战力先例样本）；放 data/ 根目录，避免被 load_days 当交易日读取
        (OUT_DIR.parent / "history.json").write_text(
            json.dumps(history, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        n_h2h = sum(
            1 for p in OUT_DIR.glob("*.json")
            for mm in json.loads(p.read_text(encoding="utf-8")).get("matches", [])
            if mm.get("h2h")
        )
        print(f"[i] history 池 {len(history)} 条 → data/history.json；含历史交锋场次 {n_h2h}")
    print(f"\n{'[dry-run] ' if dry else ''}共 {n_days} 个交易日 / {n_matches} 场 / 赛果 {n_results} 场")


if __name__ == "__main__":
    main()
