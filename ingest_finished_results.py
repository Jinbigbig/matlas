"""实时赛果录入：把体彩直播里「已结束」但赛果库缺的场次补进赛果库。

背景：赛果库 results_data.json 由 jinbet 上午补录，当晚结束的比赛要等次日
才有赛果，导致 matlas 卡片的四维命中标签（方向/比分/进球/半全场）当晚不亮。
直播接口 live_scores.json 已有全场/半场比分与状态，本脚本据此直接补录，
再走 import_jinbet → build → publish，命中判定沿用既有口径，不改前端。

录入字段与 jinbet 赛果库一致：fullScore / halfScore / winFlag 等。
只补「直播已结束且赛果库尚无」的场次，幂等；不覆盖已有赛果。

用法：
    python ingest_finished_results.py [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from matlas.config import write_text_safe  # noqa: E402

LIVE_SCORES = ROOT / "data" / "live_scores.json"
RESULTS = ROOT / "data" / "results_data.json"
DAYS_DIR = ROOT / "data" / "days"


def _read(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _win_flag(full: str) -> str:
    """H/D/A：由全场比分推导，与 jinbet 赛果库 winFlag 同口径。"""
    try:
        h, a = (int(x) for x in full.replace(":", "-").split("-")[:2])
    except (ValueError, TypeError):
        return ""
    return "H" if h > a else ("A" if h < a else "D")


def _day_meta(date: str) -> dict[str, dict]:
    """当日 data/days 的索引：code 与（主,客）→ 赛果库附加字段。"""
    day = _read(DAYS_DIR / f"{date}.json") or {}
    out: dict[str, dict] = {}
    for m in day.get("matches") or []:
        code = str(m.get("code") or "")
        home = str((m.get("home") or {}).get("name") or "")
        away = str((m.get("away") or {}).get("name") or "")
        if not code:
            continue
        odds = m.get("odds") or {}
        out[code] = {
            "home": home,
            "away": away,
            "league": str(m.get("competition") or ""),
            "matchId": str((m.get("extras") or {}).get("match_id") or ""),
            "odds": odds,
        }
        out[(home, away)] = out[code]
    return out


def ingest(dry: bool = False) -> int:
    live = _read(LIVE_SCORES)
    results = _read(RESULTS)
    if not live or not isinstance(results, dict):
        print("[ingest] 缺少 live_scores.json 或 results_data.json，跳过", file=sys.stderr)
        return 0

    added: dict[str, dict] = {}
    for key, ls in (live.get("matches") or {}).items():
        # key = "YYYY-MM-DD|周六005"
        if str(ls.get("status")) != "已结束" or "|" not in key:
            continue
        date, code = key.split("|", 1)
        home = str(ls.get("home") or "")
        away = str(ls.get("away") or "")
        full = str(ls.get("score") or "").replace(":", "-")
        half = str(ls.get("half") or "").replace(":", "-")
        if not (date and code and home and away and full):
            continue

        # 已有赛果（按编号或队名）则跳过，不覆盖
        existing_keys = [k for k, v in results.items()
                         if k.startswith(f"{date}_")
                         and (str(v.get("matchNumStr")) == code
                              or (v.get("home") == home and v.get("away") == away))]
        if existing_keys or any(k.startswith(f"{date}_{home}_{away}") for k in results):
            continue
        out_key = f"{date}_{home}_{away}"
        if out_key in added:
            continue

        meta = _day_meta(date)
        m = meta.get(code) or meta.get((home, away)) or {}
        odds = m.get("odds") or {}
        rec = {
            "home": home,
            "away": away,
            "score": full,
            "halfScore": half,
            "fullScore": full,
            "winFlag": _win_flag(full),
            "league": m.get("league", ""),
            "leagueAbbr": m.get("league", ""),
            "matchId": str(ls.get("match_id") or m.get("matchId") or ""),
            "matchNumStr": code,
            "matchNo": code[2:] if len(code) > 2 else "",
            "status": "2",
        }
        # 赔率（有就带上，与赛果库同字段名）
        for src_k, dst_k in (("home", "胜"), ("draw", "平"), ("away", "负")):
            if odds.get(src_k) is not None:
                rec[dst_k] = odds[src_k]
        if odds.get("handicap") is not None:
            rec["handicap"] = f"{odds['handicap']:+g}"
        added[out_key] = rec

    if not added:
        print("[ingest] 无新增已结束赛果")
        return 0

    for k, rec in added.items():
        print(f"[ingest] + {k}: {rec['fullScore']} (半 {rec['halfScore']}) {rec['winFlag']}")
    if dry:
        print(f"[ingest] dry-run：{len(added)} 场未写入")
        return len(added)

    merged = dict(results)
    merged.update(added)
    write_text_safe(RESULTS, json.dumps(merged, ensure_ascii=False, indent=1) + "\n")
    print(f"[ingest] 已录入 {len(added)} 场 → data/results_data.json")
    return len(added)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="实时赛果录入：已结束场次补进赛果库")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    raise SystemExit(0 if ingest(args.dry_run) >= 0 else 1)
