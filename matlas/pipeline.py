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

    # 3. 归档索引 + 页头四按钮落地页（数据/功能/我的/搜索）
    L.write(cfg, "days/index.html", P.render_archive_index(cfg, [d.date for d in ordered]))
    L.write(cfg, "data.html", P.render_stats(cfg, ordered))
    L.write(cfg, "features.html", P.render_features(cfg))
    L.write(cfg, "me.html", P.render_me(cfg))
    L.write(cfg, "search.html", P.render_search(cfg, ordered))
    stats["files"] += 5

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
