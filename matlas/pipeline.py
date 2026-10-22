"""构建流水线：读数据 → 渲染 → 写 GEO 文件 → 红线自检。

刻意保持单趟、无状态、幂等：同样的输入永远产出同样的 HTML，
只有明文变化（数据变了）才会改变输出。
"""

from __future__ import annotations

import shutil
from datetime import datetime, timezone

from .config import Config
from .models import Day, Match
from .render import layout as L
from .render import pages as P
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

    # 1. 今日首页 = 最新一日
    if latest:
        L.write(cfg, "index.html", P.render_day(cfg, latest, is_today=True,
                                                ranking=ranking, team_ranking=team_ranking,
                                                dates=dates_desc))
        stats["files"] += 1

    # 2. 按日归档 + 单场落地页
    for d in ordered:
        rel = f"days/{d.date}.html"
        L.write(cfg, rel, P.render_day(cfg, d, is_today=False, rel=rel,
                                       ranking=ranking, team_ranking=team_ranking,
                                       dates=dates_desc))
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

    lg_stat: dict[str, list[int]] = {}
    tm_stat: dict[str, list[int]] = {}
    for lg, ms in lg_matches.items():
        h, n = _dir_stats(ms)
        lg_stat[lg] = [len(ms), h, n]
    for tm, ms in tm_matches.items():
        if not tm:
            continue
        h, n = _dir_stats(ms)
        tm_stat[tm] = [len(ms), h, n]

    # 3. 归档索引（交易日 / 联赛 / 球队 三视图）+ 页头四按钮落地页
    L.write(cfg, "days/index.html", P.render_archive_index(
        cfg, [d.date for d in ordered],
        leagues=[(k, v[0], v[1], v[2]) for k, v in lg_stat.items()],
        teams=[(k, v[0], v[1], v[2]) for k, v in sorted(tm_stat.items(), key=lambda x: -x[1][0])],
    ))
    L.write(cfg, "data.html", P.render_stats(cfg, ordered))
    L.write(cfg, "features.html", P.render_features(cfg))
    L.write(cfg, "me.html", P.render_me(cfg))
    L.write(cfg, "search.html", P.render_search(cfg, ordered))
    stats["files"] += 5

    # 4. 联赛 / 球队专题页（卡片上的联赛名、球队名可点跳转；数据随导入自动生长）
    for lg, ms in sorted(lg_matches.items()):
        L.write(cfg, f"leagues/{lg}.html", P.render_league(cfg, lg, ms, _dir_stats(ms)))
        stats["files"] += 1
    for tm, ms in sorted(tm_matches.items()):
        if not tm:
            continue
        L.write(cfg, f"teams/{tm}.html", P.render_team(cfg, tm, ms, _dir_stats(ms)))
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
