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


def compute(days: list[Day], history: list[dict] | None = None) -> int:
    """按时间序遍历全部场次，为每场计算 metrics_home/away 与 momentum。返回出图场次数。

    history：jinbet 全量赛果库（import 写出 data/history.json），补充
    站内收录期之外的先例样本；与站内场次按 (日期, 主, 客) 去重。
    """
    hist: dict[str, list] = defaultdict(list)   # 队名 -> [(日期, 联赛, 进球, 失球, 去水胜率)]
    tbl: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(lambda: [0, 0]))  # 联赛 -> 队 -> [积分, 场次]

    ordered = sorted((d for d in days if d.matches), key=lambda d: d.date)
    day_set = {(d.date, m.home.name, m.away.name) for d in ordered for m in d.matches}
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

    def _record(date: str, comp: str, home: str, away: str, gf: int, ga: int,
                ph: float | None, pa: float | None) -> None:
        hist[home].append((date, comp, gf, ga, ph))
        hist[away].append((date, comp, ga, gf, pa))
        th, ta = tbl[comp][home], tbl[comp][away]
        th[1] += 1
        ta[1] += 1
        if gf > ga:
            th[0] += 3
        elif gf == ga:
            th[0] += 1
            ta[0] += 1
        else:
            ta[0] += 3

    # 事件时间线：history 池 + 站内场次按日期归并（同日历史先入，站内场次后算）
    events: list[tuple[str, int, object]] = []
    for h in (history or []):
        if (h["date"], h["home"], h["away"]) in day_set:
            continue
        events.append((h["date"], 0, h))
    for d in ordered:
        for m in d.matches:
            events.append((d.date, 1, m))
    events.sort(key=lambda e: (e[0], e[1]))

    for date, kind, obj in events:
        if kind == 0:
            h = obj
            _record(h["date"], h["competition"], h["home"], h["away"],
                    h["gf"], h["ga"], h.get("ph"), h.get("pa"))
            continue
        m = obj
        day_date = date
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
                _record(day_date, m.competition, m.home.name, m.away.name,
                        gf, ga, dp[0] if dp else None, dp[1] if dp else None)

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


# ---------------------------------------------------------------- 球队看板


SERIES_N = 10       # 球队页走势图窗口


def _outcome(gf: int, ga: int) -> str:
    return "w" if gf > ga else ("d" if gf == ga else "l")


def _same_team(a: str | None, b: str | None) -> bool:
    """队名双向包含匹配（历史库用竞彩全称，站点多用简称）。"""
    return bool(a and b and len(a) >= 2 and len(b) >= 2 and (a in b or b in a))


def team_board(days: list[Day], history: list[dict] | None = None) -> dict[str, dict]:
    """按球队聚合：最新六维 + 全量真实战绩 + 站内赔率/让球走势。

    history：jinbet 全量赛果库（data/history.json）。场次、进失球、近期状态按
    「站内 + 历史」全量统计——这些都是已完赛的真实结果，不该只算站内收录的那几周。
    六维取该队最后一次站内出场的战力（compute 已把 history 并入滚动窗口）；
    赔率与让球只有站内场次有，走势仍按站内。
    """
    ordered = sorted((d for d in days if d.matches), key=lambda d: d.date)
    board: dict[str, dict] = {}

    def slot(name: str, league: str) -> dict:
        b = board.get(name)
        if b is None:
            b = board[name] = {
                "name": name, "league": league,
                "metrics": None, "matches": 0, "settled": 0,
                "gf": 0, "ga": 0, "form": [], "recent": [], "series": [],
            }
        return b

    for day in ordered:
        for m in day.matches:
            score = _parse_score(m.result.full_score) if m.result else None
            for side, name in (("home", m.home.name), ("away", m.away.name)):
                if not name:
                    continue
                b = slot(name, m.competition)
                b["league"] = m.competition or b["league"]
                b["matches"] += 1
                met = m.metrics_home if side == "home" else m.metrics_away
                if met is not None:
                    b["metrics"] = met
                if not score:
                    continue
                gf, ga = score if side == "home" else (score[1], score[0])
                # 市场端：该队获胜赔率 + 该队让球（负为让出）
                price = hcp = None
                if m.odds:
                    price = m.odds.home if side == "home" else m.odds.away
                    if m.odds.handicap is not None:
                        hcp = m.odds.handicap if side == "home" else -m.odds.handicap
                b["series"].append({
                    "date": m.day, "code": m.code, "id": m.match_id,
                    "opp": m.away.name if side == "home" else m.home.name,
                    "ha": side, "gf": gf, "ga": ga,
                    "res": _outcome(gf, ga),
                    "price": round(price, 2) if isinstance(price, (int, float)) else None,
                    "hcp": hcp,
                })

    # 全量真实赛果线：站内已结算 + 历史库，按「日期 + 双方」去重（站内优先）
    seats = {(m.day, frozenset((m.home.name, m.away.name)))
             for d in ordered for m in d.matches if m.home.name and m.away.name}
    names = set(board)
    alias: dict[str, str | None] = {}

    def resolve(n: str) -> str | None:
        if n in alias:
            return alias[n]
        if n in names:
            alias[n] = n
        else:
            alias[n] = next((s for s in names if _same_team(n, s)), None)
        return alias[n]

    events: list[tuple[str, str, str, int, int]] = []
    for d in ordered:
        for m in d.matches:
            score = _parse_score(m.result.full_score) if m.result else None
            if score and m.home.name and m.away.name:
                events.append((m.day, m.home.name, m.away.name, score[0], score[1]))
    for h in (history or []):
        try:
            gf, ga = int(h["gf"]), int(h["ga"])
        except (KeyError, TypeError, ValueError):
            continue
        date = str(h.get("date") or "")
        hp, ap = str(h.get("home") or ""), str(h.get("away") or "")
        home, away = resolve(hp), resolve(ap)
        # 对手不在站点池里也照样给本方计场次——历史的真实结果不该因为对面陌生就丢掉
        if not home and not away:
            continue
        home, away = home or hp, away or ap
        if (date, frozenset((home, away))) in seats:
            continue
        events.append((date, home, away, gf, ga))

    events.sort(key=lambda e: e[0])
    seen: set[tuple[str, frozenset]] = set()
    for date, home, away, gf, ga in events:
        pair = (date, frozenset((home, away)))
        if pair in seen:          # 同场镜像/重复记录只计一次
            continue
        seen.add(pair)
        for name, g_for, g_against in ((home, gf, ga), (away, ga, gf)):
            b = board.get(name)
            if b is None:
                continue
            b["settled"] += 1
            b["gf"] += g_for
            b["ga"] += g_against
            b["form"].append(_outcome(g_for, g_against))
            b["recent"].append({
                "date": date, "opp": away if name == home else home,
                "ha": "home" if name == home else "away",
                "gf": g_for, "ga": g_against,
                "res": _outcome(g_for, g_against),
            })

    for b in board.values():
        n = b["settled"]
        b["gf_avg"] = round(b["gf"] / n, 2) if n else 0.0
        b["ga_avg"] = round(b["ga"] / n, 2) if n else 0.0
        b["pts_rate"] = round(
            100 * sum(3 if r in ("w",) else 1 if r == "d" else 0 for r in b["form"])
            / (3 * len(b["form"])), 1) if b["form"] else 0.0
        vals = b["metrics"].values() if b["metrics"] else []
        b["power"] = round(sum(vals) / len(vals)) if vals else None
        b["series"] = b["series"][-SERIES_N:]
        b["form"] = b["form"][-10:]
        b["recent"] = b["recent"][-10:]
    return board
