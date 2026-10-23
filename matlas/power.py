"""六维战力与动量曲线：用站内历史赛果自算（方案 A，2026-10-23）。

六维口径（0-100，联赛内分位映射）：
- 进攻   = 近 10 场场均进球（分位越高越靠前）
- 防守   = 近 10 场场均失球（反向分位，失球越少分越高）
- 控制   = 近 10 场场均净胜球
- 状态   = 近 5 场积分 / 满分积分
- 阵容   = 近 10 场市场平均去水胜率（市场对球队实力的定价）
- 战意   = 同联赛积分排名分位（排名越靠前分越高）

动量曲线 = 两队各自近 8 场逐场进球数（T-8 → T-1）。
先例场次不足 MIN_PRIOR 的队不出图，面板维持占位文案。
"""

from __future__ import annotations

from collections import defaultdict

from .models import Day, Match, Metrics, Momentum

RECENT = 10       # 攻/防/控/阵容窗口
FORM_N = 5        # 状态窗口
MOM_N = 8         # 动量曲线窗口
MIN_PRIOR = 5     # 出图最少先例场次


def _parse_score(score: str) -> tuple[int, int] | None:
    try:
        h, a = score.split("-")
        return int(h), int(a)
    except (ValueError, AttributeError):
        return None


def _devig(odds) -> tuple[float, float] | None:
    """胜平负去水后返回 (主队胜率, 客队胜率)。"""
    h, d, a = odds.home, odds.draw, odds.away
    if not (h and d and a):
        return None
    s = 1 / h + 1 / d + 1 / a
    return (1 / h) / s, (1 / a) / s


def _pct(raw: float | None, pool: list[float], *, lower_better: bool = False) -> float | None:
    """联赛内分位 0-100。pool 为该联赛该轴全部原始值。"""
    if raw is None or len(pool) < 2:
        return None
    vals = [-v for v in pool] if lower_better else pool
    x = -raw if lower_better else raw
    below = sum(1 for v in vals if v < x)
    return round(below / (len(vals) - 1) * 100)


def compute(days: list[Day]) -> int:
    """按时间序遍历全部场次，为每场计算 metrics_home/away 与 momentum。返回出图场次数。"""
    hist: dict[str, list] = defaultdict(list)   # 队名 -> [(日期, 联赛, 进球, 失球, 去水胜率)]
    pts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))  # 联赛 -> 队 -> 积分
    played: dict[str, set[str]] = defaultdict(set)  # 联赛 -> 已完赛队集合

    # 先按日期排序，保证先例严格早于本场
    ordered = sorted((d for d in days if d.matches), key=lambda d: d.date)
    # raw 暂存：match -> {"home": {axis: raw}, "away": {...}}；pool: (联赛, 轴) -> [raw]
    raws: dict[int, dict[str, dict[str, float | None]]] = {}
    pools: dict[tuple[str, str], list[float]] = defaultdict(list)

    for day in ordered:
        for m in day.matches:
            sides: dict[str, dict[str, float | None]] = {}
            for key, name in (("home", m.home.name), ("away", m.away.name)):
                rec = hist.get(name, [])
                dp = _devig(m.odds) if m.odds else None
                my_p = (dp[0] if key == "home" else dp[1]) if dp else None
                raw: dict[str, float | None] = {k: None for k in ("attack", "defence", "control", "form", "value", "motivation")}
                if len(rec) >= MIN_PRIOR:
                    last = rec[-RECENT:]
                    raw["attack"] = sum(r[2] for r in last) / len(last)
                    raw["defence"] = sum(r[3] for r in last) / len(last)
                    raw["control"] = sum(r[2] - r[3] for r in last) / len(last)
                    f5 = rec[-FORM_N:]
                    raw["form"] = sum(3 if r[2] > r[3] else 1 if r[2] == r[3] else 0 for r in f5) / (3 * FORM_N) * 100
                    v = [r[4] for r in last if r[4] is not None]
                    raw["value"] = sum(v) / len(v) * 100 if v else None
                    # 战意：同联赛积分榜排名分位（仅统计本场前已完赛的队）
                    table = pts.get(m.competition, {})
                    ranked = sorted(table.items(), key=lambda kv: -kv[1])
                    n = len(ranked)
                    if n >= MIN_PRIOR:
                        pos = next((i for i, (t, _) in enumerate(ranked) if t == name), None)
                        raw["motivation"] = (1 - pos / (n - 1)) * 100 if pos is not None else None
                sides[key] = raw
                for axis, v in raw.items():
                    if v is not None:
                        pools[(m.competition, axis)].append(v)
            raws[id(m)] = sides

            # 赛果回填（先算后记，先例不含本场）
            if m.result and m.result.full_score:
                parsed = _parse_score(m.result.full_score)
                if parsed:
                    gf, ga = parsed
                    dp = _devig(m.odds) if m.odds else None
                    hist[m.home.name].append((day.date, m.competition, gf, ga, dp[0] if dp else None))
                    hist[m.away.name].append((day.date, m.competition, ga, gf, dp[1] if dp else None))
                    if gf > ga:
                        pts[m.competition][m.home.name] += 3
                    elif gf == ga:
                        pts[m.competition][m.home.name] += 1
                        pts[m.competition][m.away.name] += 1
                    else:
                        pts[m.competition][m.away.name] += 3
                    played[m.competition].update((m.home.name, m.away.name))

    # 第二遍：分位映射并写入
    drawn = 0
    for day in ordered:
        for m in day.matches:
            sides = raws.get(id(m))
            if not sides:
                continue
            met: dict[str, Metrics | None] = {}
            for key in ("home", "away"):
                raw = sides[key]
                vals = {
                    "attack": _pct(raw["attack"], pools[(m.competition, "attack")]),
                    "defence": _pct(raw["defence"], pools[(m.competition, "defence")], lower_better=True),
                    "control": _pct(raw["control"], pools[(m.competition, "control")]),
                    "form": raw["form"],
                    "value": _pct(raw["value"], pools[(m.competition, "value")]),
                    "motivation": _pct(raw["motivation"], pools[(m.competition, "motivation")]),
                }
                vals = {k: round(v) if v is not None else None for k, v in vals.items()}
                met[key] = Metrics(**vals) if all(v is not None for v in vals.values()) else None
            if met["home"] and met["away"]:
                m.metrics_home, m.metrics_away = met["home"], met["away"]

            # 动量曲线：两队各自近 8 场逐场进球
            hr, ar = hist.get(m.home.name, []), hist.get(m.away.name, [])
            if len(hr) >= MIN_PRIOR and len(ar) >= MIN_PRIOR:
                n = min(len(hr), len(ar), MOM_N)
                m.momentum = Momentum(
                    labels=[f"T-{n - i}" for i in range(n)],
                    home=[float(r[2]) for r in hr[-n:]],
                    away=[float(r[2]) for r in ar[-n:]],
                )
            if m.metrics_home and m.metrics_away:
                drawn += 1
    return drawn
