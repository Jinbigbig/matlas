"""把 `data/squads/` 里的球员评分注入每日比赛 JSON 的 `squad` 字段。

为什么要单独一步、而不是塞进 `import_jinbet.py`：
- import 是**有损**的（会按上游重写整份 day JSON），今天注入的字段明天就没了；
- 评分源每天凌晨更新一次，与 import 的生命周期不同，分开跑更好控。

匹配规则：
- 队名：直接用源站的中文队名（与站内 96% 一致），差异走 `TEAM_ALIAS`；
- 球员：不跨源匹配姓名。`watch` 只在源站中文名与伤停名单**完全相等**时标注 ——
  两边译法不同（港译 vs 自译），模糊匹配的误标比不标更糟。

用法：
    python -m matlas.enrich_squads              # 近 7 天
    python -m matlas.enrich_squads --days 30
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SQUAD_DIR = ROOT / "data" / "squads"
DAY_DIR = ROOT / "data" / "days"

SOURCE = "球小策球员数据中心"
SOURCE_URL = "https://www.qiuxiaoce.com/player-rankings/"
TOP_N = 5

# 站内队名 → 源站队名（仅列实测对不上的，按 difflib 相似度人工确认）
TEAM_ALIAS = {
    "弗鲁米嫩": "弗鲁米嫩塞",
    "帕梅拉斯": "帕尔梅拉斯",
    "米竞技": "米内罗竞技",
    "米内罗": "米内罗竞技",
    "巴竞技": "巴拉纳竞技",
    "布拉干RB": "布拉干蒂诺RB",
    "瓦斯科": "瓦斯科达伽马",
    "沙佩科": "沙佩科恩斯",
    "浦项": "浦项制铁",
    "纽喷气机": "纽卡斯尔喷气机",
    "腓特烈": "腓特烈斯塔",
}


def _f(v) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f


def load_index() -> tuple[dict[str, list[dict]], str]:
    idx: dict[str, list[dict]] = {}
    updated = ""
    for f in sorted(SQUAD_DIR.glob("*.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        updated = max(updated, d.get("updated_at") or "")
        for p in d.get("players") or []:
            team = (p.get("team_name") or "").strip()
            if team:
                idx.setdefault(team, []).append(p)
    return idx, updated


def build_side(m: dict, side: str, idx: dict[str, list[dict]]) -> dict | None:
    team = (m.get(side) or {}).get("name", "")
    pool = idx.get(team) or idx.get(TEAM_ALIAS.get(team, ""), [])
    if not pool:
        return None

    inj_names = {i.get("player") for i in (m.get("injuries") or [])
                 if i.get("team") == side and i.get("player")}
    inj_status = {i.get("player"): i.get("status") for i in (m.get("injuries") or [])
                  if i.get("team") == side and i.get("player")}

    rows = []
    for p in pool:
        gim = _f(p.get("gim"))
        form = _f(p.get("form_rating"))
        name = (p.get("display_name") or p.get("player_name") or "").strip()
        watch = ""
        if name and name in inj_names:
            watch = inj_status.get(name) or "out"
        rows.append({
            "name": name,
            "pos": (p.get("position") or "").strip(),
            "oti": _f(p.get("oti")),
            "dii": _f(p.get("dii")),
            "gim": gim,
            "form": form,
            "cons": _f(p.get("consistency_score")),
            "fatigue": (p.get("fatigue_risk") or "").strip(),
            "watch": watch,
        })

    scored = [r for r in rows if r["gim"] is not None]
    scored.sort(key=lambda r: -r["gim"])
    top = scored[:TOP_N]
    forms = [r["form"] for r in rows if r["form"] is not None]
    core = [r["gim"] for r in top]

    return {
        "team": team,
        "n": len(rows),
        "core_avg": round(sum(core) / len(core), 1) if core else None,
        "form_avg": round(sum(forms) / len(forms), 2) if forms else None,
        "high_fatigue": sum(1 for r in rows if r["fatigue"] == "High"),
        "top": top,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=3,
                    help="只处理最近 N 天（默认 3）。历史页不回填 —— "
                         "评分源是「当下快照」，灌进两周前的页面会造成时间错位")
    args = ap.parse_args(argv)

    idx, updated = load_index()
    if not idx:
        print("[enrich] data/squads 为空，先跑 python -m matlas.fetch_squads")
        return 1

    all_files = sorted(DAY_DIR.glob("*.json"))
    files = all_files[-args.days:]
    stale = [f for f in all_files if f not in files]

    # 清掉范围外的旧注入，避免历史页挂着「今天的评分」
    cleaned = 0
    for f in stale:
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        dropped = False
        for m in d.get("matches") or []:
            sq = m.get("squad")
            if isinstance(sq, dict) and sq.get("source") == SOURCE:
                m.pop("squad", None)
                dropped = True
        if dropped:
            f.write_text(json.dumps(d, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
            cleaned += 1
    touched = miss_team = 0
    missing: set[tuple[str, str]] = set()

    for f in files:
        d = json.loads(f.read_text(encoding="utf-8"))
        changed = False
        for m in d.get("matches") or []:
            home = build_side(m, "home", idx)
            away = build_side(m, "away", idx)
            if not home and not away:
                for side in ("home", "away"):
                    tn = (m.get(side) or {}).get("name", "")
                    if tn and tn not in idx:
                        missing.add((m.get("competition", ""), tn))
                if m.pop("squad", None) is not None:
                    changed = True
                continue
            if home is None or away is None:
                tn = (m.get("away" if home else "home") or {}).get("name", "")
                if tn:
                    missing.add((m.get("competition", ""), tn))
            m["squad"] = {
                "source": SOURCE,
                "url": SOURCE_URL,
                "updated": updated,
                "home": home,
                "away": away,
            }
            changed = True
            touched += 1
        if changed:
            f.write_text(json.dumps(d, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    print(f"[enrich] {len(files)} 天 / 注入 {touched} 场 / 评分更新于 {updated[:16]}"
          + (f" / 清理范围外 {cleaned} 天" if cleaned else ""))
    if missing:
        miss_team = len(missing)
        print(f"[enrich] 有 {miss_team} 支球队在评分库里找不到（该侧区块自动省略）：")
        for comp, tn in sorted(missing)[:15]:
            print(f"    {comp} · {tn}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
