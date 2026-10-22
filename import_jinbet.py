#!/usr/bin/env python3
"""jinbet 历史数据 → matlas data/days/*.json 一次性导入器。

来源（只读）：
  C:/Users/Jin/jinbet/predictions/{date}/pred_snapshot.json   每日预测快照
  C:/Users/Jin/jinbet/results_history/{date}.json             赛果回填（key: {date}_{主}_{客}）

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
OUT_DIR = Path("C:/Users/Jin/matlas/data/days")

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
    p = RES_DIR / f"{date}.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


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


def _direction_hit(top_label: str, win_flag: str) -> bool | None:
    if not top_label or not win_flag:
        return None
    want = {"主胜": "H", "平": "D", "客胜": "A"}.get(top_label.strip())
    return None if want is None else want == win_flag


def convert_match(date: str, m: dict, by_code: dict, by_name: dict) -> dict:
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
        if full:
            result = {
                "full_score": full,
                "half_score": half,
                "direction_hit": _direction_hit(top_dir, win_flag),
                "score_hit": (top_score_label == full) if top_score_label else None,
                "goals_hit": goals_hit,
                "htft_hit": None,
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

    out = {
        "match_id": match_id,
        "day": date,
        "code": code,
        "competition": league,
        "kickoff": "",
        "home": {"name": home, "league": league},
        "away": {"name": away, "league": league},
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
    return out


def main() -> None:
    dry = "--dry-run" in sys.argv
    OUT_DIR.mkdir(parents=True, exist_ok=True)
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
            cm = convert_match(date, m, by_code, by_name)
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
    print(f"\n{'[dry-run] ' if dry else ''}共 {n_days} 个交易日 / {n_matches} 场 / 赛果 {n_results} 场")


if __name__ == "__main__":
    main()
