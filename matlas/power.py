"""六维战力与动量曲线：用站内历史赛果自算（方案 A，2026-10-23）。

样本不足时用联赛均值做收缩估计（经验贝叶斯，k=2~3 场伪先验），
因此所有场次都出图，不再留占位——0 先例的队给联赛中性值（约 50）。

六维口径（0-100，联赛内分位映射）：
- 进攻   = 近 10 场场均进球，向联赛场均进球收缩
- 防守   = 近 10 场场均失球，向联赛场均失球收缩（反向分位）
- 控制   = 收缩后场均净胜球
- 状态   = 近 5 场积分率，向 50% 收缩
- 阵容   = 近 10 场市场平均去水胜率（实力定价），向 50% 收缩
- 战意   = 积分率（场均积分），向场均 1.5 分收缩，联赛内分位

动量曲线 = 两队各自近 8 场逐场进球数（T-8 → T-1），
两队合计先例 ≥2 场才画线（曲线本身需要时间序列）。
"""

from __future__ import annotations

from collections import defaultdict

from .models import Day, Match, Metrics, Momentum

RECENT = 10       # 攻/防/控/阵容窗口
FORM_N = 5        # 状态窗口
MOM_N = 8         # 动量曲线窗口
K_GOAL = 3        # 进/失球收缩强度（伪先验场数）
K_RATE = 2        # 积分率/胜率收缩强度

AXES_KEYS = ("attack", "defence", "control", "form", "value", "motivation")


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


def _pct(raw: float, pool: list[float], *, lower_better: bool = False) -> float:
    """联赛内分位 0-100。pool 为该联赛该轴全部原始值。"""
    if len(pool) < 2:
        return 50
    vals = [-v for v in pool] if lower_better else pool
    x = -raw if lower_better else raw
    below = sum(1 for v in vals if v < x)
    return round(below / (len(vals) - 1) * 100)


def compute(days: list[Day]) -> int:
    """按时间序遍历全部场次，为每场计算 metrics_home/away 与 momentum。返回出图场次数。"""
    hist: dict[str, list] = defaultdict(list)   # 队名 -> [(日期, 联赛, 进球, 失球, 去水胜率)]
    tbl: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(lambda: [0, 0]))  # 联赛 -> 队 -> [积分, 场次]

    ordered = sorted((d for d in days if d.matches), key=lambda d: d.date)
    # 全局联赛均值先验（先扫一遍赛果）
    gf_all, ga_all, n_all = 0.0, 0.0, 0
    for day in ordered:
        for m in day.matches:
            if m.result and m.result.full_score:
                p = _parse_score(m.result.full_score)
                if p:
                    gf_all += p[0]
                    ga_all += p[1]
                    n_all += 1
    lg_gf = gf_all / n_all if n_all else 1.3
    lg_ga = ga_all / n_all if n_all else 1.3

    # 各联赛均值（结果数充足时优先用本联赛先验）
    comp_gf: dict[str, list[float]] = defaultdict(list)
    for day in ordered:
        for m in day.matches:
            if m.result and m.result.full_score:
                p = _parse_score(m.result.full_score)
                if p:
                    comp_gf[m.competition].extend(p)
    comp_avg = {
        comp: sum(v) / len(v) for comp, v in comp_gf.items() if len(v) >= 30
    }

    raws: dict[int, dict[str, dict[str, float | None]]] = {}
    pools: dict[tuple[str, str], list[float]] = defaultdict(list)

    for day in ordered:
        for m in day.matches:
            prior = comp_avg.get(m.competition, lg_gf)  # 收缩目标：本联赛场均进球
            sides: dict[str, dict[str, float | None]] = {}
            for key, name in (("home", m.home.name), ("away", m.away.name)):
                rec = hist.get(name, [])
                dp = _devig(m.odds) if m.odds else None
                my_p = (dp[0] if key == "home" else dp[1]) if dp else None
                raw: dict[str, float | None] = {k: None for k in AXES_KEYS}

                last = rec[-RECENT:]
                f5 = rec[-FORM_N:]
                # 进攻/防守：向联赛场均进球收缩（进攻目标 prior，防守目标同量级）
                gf = (sum(r[2] for r in last) + K_GOAL * prior) / (len(last) + K_GOAL)
                ga = (sum(r[3] for r in last) + K_GOAL * prior) / (len(last) + K_GOAL)
                raw["attack"] = gf
                raw["defence"] = ga
                raw["control"] = gf - ga
                # 状态：近 5 场积分率，向 50% 收缩
                pts5 = sum(3 if r[2] > r[3] else 1 if r[2] == r[3] else 0 for r in f5)
                raw["form"] = 100 * (pts5 + K_RATE * 1.5) / (3 * (len(f5) + K_RATE))
                # 阵容：市场平均去水胜率，向 50% 收缩
                v = [r[4] for r in last if r[4] is not None]
                raw["value"] = 100 * (sum(v) + K_RATE * 0.5 * max(len(v), 1)) / (len(v) + K_RATE) if v else 50.0
                # 战意：积分率（场均积分，向 1.5 分收缩），联赛内分位
                pl = tbl.get(m.competition, {}).get(name, [0, 0])
                raw["motivation"] = 100 * (pl[0] + K_RATE * 1.5) / (3 * (pl[1] + K_RATE))
                sides[key] = raw
                for axis, val in raw.items():
                    if val is not None:
                        pools[(m.competition, axis)].append(val)
            raws[id(m)] = sides

            # 赛果回填（先算后记，先例不含本场）
            if m.result and m.result.full_score:
                parsed = _parse_score(m.result.full_score)
                if parsed:
                    gf, ga = parsed
                    dp = _devig(m.odds) if m.odds else None
                    hist[m.home.name].append((day.date, m.competition, gf, ga, dp[0] if dp else None))
                    hist[m.away.name].append((day.date, m.competition, ga, gf, dp[1] if dp else None))
                    th, ta = tbl[m.competition][m.home.name], tbl[m.competition][m.away.name]
                    th[1] += 1
                    ta[1] += 1
                    if gf > ga:
                        th[0] += 3
                    elif gf == ga:
                        th[0] += 1
                        ta[0] += 1
                    else:
                        ta[0] += 3

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
                    "form": _pct(raw["form"], pools[(m.competition, "form")]),
                    "value": _pct(raw["value"], pools[(m.competition, "value")]),
                    "motivation": _pct(raw["motivation"], pools[(m.competition, "motivation")]),
                }
                vals = {k: round(v) if v is not None else None for k, v in vals.items()}
                met[key] = Metrics(**vals) if all(v is not None for v in vals.values()) else None
            if met["home"] and met["away"]:
                m.metrics_home, m.metrics_away = met["home"], met["away"]

            # 动量曲线：两队各自近 8 场逐场进球（合计先例 ≥2 场才画）
            hr, ar = hist.get(m.home.name, []), hist.get(m.away.name, [])
            n = min(len(hr), len(ar), MOM_N)
            if n >= 2:
                m.momentum = Momentum(
                    labels=[f"T-{n - i}" for i in range(n)],
                    home=[float(r[2]) for r in hr[-n:]],
                    away=[float(r[2]) for r in ar[-n:]],
                )
            if m.metrics_home and m.metrics_away:
                drawn += 1
    return drawn
