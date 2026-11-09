"""构建流水线：读数据 → 渲染 → 写 GEO 文件 → 红线自检。

刻意保持单趟、无状态、幂等：同样的输入永远产出同样的 HTML，
只有明文变化（数据变了）才会改变输出。
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone

from .config import Config
from .models import Day, Match
from .render import layout as L
from .render import pages as P
from . import power
from . import seo
from .source.base import DataSource


def _copy_assets(cfg: Config) -> int:
    """把 `assets/`（队徽等静态图）复制到产物目录。

    样式表由 layout 直接写进 out/assets/style.css，这里只补其余静态资源，
    所以必须用 dirs_exist_ok=True 合并而不是覆盖整个目录。
    """
    src = cfg.site_root / "assets"
    if not src.is_dir():
        return 0
    dst = cfg.out_dir / "assets"
    dst.mkdir(parents=True, exist_ok=True)
    n = 0
    for p in src.rglob("*"):
        if not p.is_file():
            continue
        t = dst / p.relative_to(src)
        t.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, t)
        n += 1
    return n


def render(cfg: Config, days: list[Day], source: DataSource | None = None) -> dict[str, int]:
    cfg.ensure_dirs()
    stats: dict[str, int] = {"days": len(days), "matches": 0, "files": 0}

    ordered = sorted(days, key=lambda d: d.date)
    latest = ordered[-1] if ordered else None
    ranking = P.compute_ranking(ordered)
    team_ranking = P.compute_team_ranking(ordered)
    dates_desc = [d.date for d in reversed(ordered)]  # 筛选面板时间行：最新在前
    # 全量历史赛果（jinbet 3534 场，2025-12 起）：深度页的场次/进失球/近期状态用真实总量
    hist: list = []
    _hp = cfg.data_dir / "history.json"
    if _hp.exists():
        try:
            hist = json.loads(_hp.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            hist = []
    board = power.team_board(ordered, hist)   # 球队级六维 + 赔率/让球走势（深度页与球队页共用）
    # 右栏「AI 预测」卡：最近 6 个交易日的报告预测首选（最新在前）
    ai_digest = P.build_ai_digest(ordered)
    # 未来赛程（今天+明天，竞彩在售期次）：比赛列表页里没有预测的场次靠它补全
    fixtures: dict = {}
    _fp = cfg.data_dir / "fixtures.json"
    if _fp.exists():
        try:
            fixtures = (json.loads(_fp.read_text(encoding="utf-8")) or {}).get("days") or {}
        except (json.JSONDecodeError, OSError):
            fixtures = {}

    # 1. 今日首页 = 最新一日
    if latest:
        L.write(cfg, "index.html", P.render_day(cfg, latest, is_today=True,
                                                ranking=ranking, team_ranking=team_ranking,
                                                dates=dates_desc, ai_digest=ai_digest))
        stats["files"] += 1

    # 2. 按日归档 + 单场落地页。
    # 近况/交锋按「赛前视角」聚合：渲染某日单场页时只用该日**之前**的已结算
    # 场次（时间截断），历史页可回溯、不穿越。半全场结果由 halfScore+fullScore 推导。
    def _half_ft(fh: int, fa: int, sh: int, sa: int) -> str:
        def side(a: int, b: int) -> str:
            return "主" if a > b else ("客" if a < b else "平")
        return f"{side(fh, fa)}/{side(sh, sa)}"

    from collections import defaultdict

    hist_by_team: dict[str, list] = defaultdict(list)   # 队名 -> RecentItem（时间升序）
    hist_h2h: dict[tuple[str, str], list] = defaultdict(list)  # (甲,乙) 有序对 -> 交手列表
    for d in ordered:
        for m in d.matches:
            # 先填当前场（此时 hist 只含更早日期），再落账当天结果
            home_hist = [r for r in hist_by_team.get(m.home.name, [])][-5:]
            away_hist = [r for r in hist_by_team.get(m.away.name, [])][-5:]
            m.recent_home = list(reversed(home_hist))   # 新 -> 旧
            m.recent_away = list(reversed(away_hist))
            pair = tuple(sorted((m.home.name, m.away.name)))
            # 交锋 = import 侧预算的全量赛果库（已按赛前日期截断）+ 站内已结算，去重后新→旧
            merged = {(h.date, h.home, h.away): h for h in (m.h2h or [])}
            for h in hist_h2h.get(pair, []):
                merged[(h.date, h.home, h.away)] = h
            m.h2h = sorted(merged.values(), key=lambda h: h.date, reverse=True)[:6]
            if not (m.result and m.result.full_score):
                continue
            try:
                sh, sa = (int(x) for x in m.result.full_score.split("-"))
                h_rec = "W" if sh > sa else ("D" if sh == sa else "L")
                a_rec = "W" if sa > sh else ("D" if sa == sh else "L")
                half_ft = ""
                if m.result.half_score:
                    fh, fa = (int(x) for x in m.result.half_score.split("-"))
                    half_ft = _half_ft(fh, fa, sh, sa)
            except ValueError:
                continue
            from .models import H2HItem, RecentItem

            hist_by_team[m.home.name].append(RecentItem(
                date=m.day, competition=m.competition, opponent=m.away.name,
                venue="home", score=m.result.full_score, outcome=h_rec, half_ft=half_ft))
            hist_by_team[m.away.name].append(RecentItem(
                date=m.day, competition=m.competition, opponent=m.home.name,
                venue="away", score=m.result.full_score, outcome=a_rec, half_ft=half_ft))
            hist_h2h[pair].append(H2HItem(
                date=m.day, competition=m.competition,
                home=m.home.name, away=m.away.name, score=m.result.full_score))
        rel = f"days/{d.date}.html"
        L.write(cfg, rel, P.render_day(cfg, d, is_today=False, rel=rel,
                                       ranking=ranking, team_ranking=team_ranking,
                                       dates=dates_desc, ai_digest=ai_digest))
        stats["files"] += 1
        for m in d.matches:
            L.write(cfg, f"matches/{m.match_id}.html", P.render_match(cfg, m))
            stats["files"] += 1
            stats["matches"] += 1

    # 聚合：联赛 / 球队 → 全部已收录场次（供专题页与归档索引使用）
    from collections import defaultdict

    lg_matches: dict[str, list] = defaultdict(list)
    tm_matches: dict[str, list] = defaultdict(list)
    for d in ordered:
        for m in d.matches:
            if m.competition:
                lg_matches[m.competition].append(m)
            tm_matches[m.home.name].append(m)
            tm_matches[m.away.name].append(m)

    def _dir_stats(ms: list) -> tuple[int, int]:
        rows = [m for m in ms if m.result and m.result.direction_hit is not None]
        return sum(1 for m in rows if m.result.direction_hit), len(rows)

    DIMS = ("direction", "score", "goals", "htft")

    def _dim_stats(ms: list) -> dict[str, tuple[int, int]]:
        """四个维度各自的命中数与有存档场次（半全场只有部分场次有存档）。"""
        out: dict[str, list[int]] = {d: [0, 0] for d in DIMS}
        for m in ms:
            r = m.result
            if r is None:
                continue
            for d in DIMS:
                hit = getattr(r, f"{d}_hit", None)
                if hit is None:
                    continue
                out[d][1] += 1
                if hit:
                    out[d][0] += 1
        return {d: (v[0], v[1]) for d, v in out.items()}

    lg_stat: dict[str, list] = {}
    tm_stat: dict[str, list] = {}
    for lg, ms in lg_matches.items():
        lg_stat[lg] = [len(ms), _dim_stats(ms)]
    for tm, ms in tm_matches.items():
        if not tm:
            continue
        tm_stat[tm] = [len(ms), _dim_stats(ms)]

    # 3. 归档索引（交易日 / 联赛 / 球队 三视图）+ 页头四按钮落地页
    L.write(cfg, "days/index.html", P.render_archive_index(
        cfg, [d.date for d in ordered],
        leagues=[(k, v[0], v[1]) for k, v in
                 sorted(lg_stat.items(), key=lambda x: -x[1][0])],
        teams=[(k, v[0], v[1]) for k, v in sorted(tm_stat.items(), key=lambda x: -x[1][0])],
    ))
    L.write(cfg, "data.html", P.render_stats(cfg, ordered))
    L.write(cfg, "odds.html", P.render_odds(cfg, ordered))
    L.write(cfg, "bets.html", P.render_bets(cfg, ordered))
    L.write(cfg, "preview/index.html", P.render_preview_index(cfg, ordered))
    L.write(cfg, "depth/index.html", P.render_depth(cfg, ordered, board))
    L.write(cfg, "matches.html", P.render_matches(cfg, ordered, fixtures, board))
    L.write(cfg, "features.html", P.render_features(cfg))
    L.write(cfg, "me.html", P.render_me(cfg))
    L.write(cfg, "search.html", P.render_search(cfg, ordered))
    stats["files"] += 9

    # 4. 联赛 / 球队专题页（卡片上的联赛名、球队名可点跳转；数据随导入自动生长）
    for lg, ms in sorted(lg_matches.items()):
        L.write(cfg, f"leagues/{lg}.html", P.render_league(cfg, lg, ms, _dir_stats(ms)))
        stats["files"] += 1
    for tm, ms in sorted(tm_matches.items()):
        if not tm:
            continue
        L.write(cfg, f"teams/{tm}.html",
                P.render_team(cfg, tm, ms, _dir_stats(ms), board=board.get(tm)))
        stats["files"] += 1

    # 4. 静态资源（队徽）
    stats["assets"] = _copy_assets(cfg)

    # 5. GEO 基建
    seo.write_llms(cfg, ordered, latest)
    seo.write_robots(cfg)
    seo.write_sitemaps(cfg, ordered)
    seo.write_dataset(cfg, ordered)
    stats["files"] += 5

    return stats


def stamp(m: Match) -> Match:
    if not m.generated_at:
        m.generated_at = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    return m
