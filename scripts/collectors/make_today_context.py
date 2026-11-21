"""当日对阵上下文生成器：从 matlas 自采的 fixtures + odds_full 合成中间文件。

jinbet 采集脚本（intel/weather/lineups/injuries_extra/league_data）原本读引擎产物
_calc_result.json 与 scripts/matches_data.json。matlas 独立后不读 jinbet，
改由本脚本从公开赛程源生成这两个文件的最小结构，供采集脚本读取。

产出：
  scripts/matches_data.json  {today, match_count, matches:[{matchNumStr,home,away,league,matchId,odds}]}
  _calc_result.json          {today, matches:[{matchNumStr,home,away,league}]}

用法：python scripts/collectors/make_today_context.py [--date YYYY-MM-DD]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
FIXTURES = ROOT / "data" / "fixtures.json"
ODDS_FULL = ROOT / "data" / "odds_full.json"
MATCHES_DATA = ROOT / "scripts" / "matches_data.json"
CALC_RESULT = ROOT / "_calc_result.json"


def _load(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def build(date: str | None = None) -> dict:
    fx = _load(FIXTURES)
    days = fx.get("days") or {}
    today = date or dt.date.today().isoformat()
    rows = days.get(today) or []

    full = ((_load(ODDS_FULL).get("data")) or {})

    matches = []
    for r in rows:
        home = str(r.get("home") or "").strip()
        away = str(r.get("away") or "").strip()
        if not home or not away:
            continue
        code = str(r.get("code") or "").strip()
        of = full.get(f"{today}_{code}") or {}
        matches.append({
            "matchNumStr": code,
            "home": home,
            "away": away,
            "league": str(r.get("league") or "").strip(),
            "matchId": str(r.get("mid") or r.get("fid") or ""),
            "odds": of,
        })

    return {
        "today": today,
        "match_count": len(matches),
        "matches": matches,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="matlas 当日对阵上下文生成")
    ap.add_argument("--date", help="日期 YYYY-MM-DD，默认今天")
    args = ap.parse_args()

    ctx = build(args.date)
    MATCHES_DATA.parent.mkdir(parents=True, exist_ok=True)
    MATCHES_DATA.write_text(json.dumps(ctx, ensure_ascii=False), encoding="utf-8")
    # _calc_result 只需 today + matches（精简，不含赔率/排名）
    calc = {
        "today": ctx["today"],
        "matches": [
            {k: m[k] for k in ("matchNumStr", "home", "away", "league")}
            for m in ctx["matches"]
        ],
    }
    CALC_RESULT.write_text(json.dumps(calc, ensure_ascii=False), encoding="utf-8")
    print(f"[context] {ctx['today']} {len(ctx['matches'])} 场 -> matches_data.json / _calc_result.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
