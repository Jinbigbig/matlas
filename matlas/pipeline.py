"""构建流水线：读数据 → 渲染 → 写 GEO 文件 → 红线自检。

刻意保持单趟、无状态、幂等：同样的输入永远产出同样的 HTML，
只有明文变化（数据变了）才会改变输出。
"""

from __future__ import annotations

from datetime import datetime, timezone

from .config import Config
from .models import Day, Match
from .render import layout as L
from .render import pages as P
from . import seo
from .source.base import DataSource


def render(cfg: Config, days: list[Day], source: DataSource | None = None) -> dict[str, int]:
    cfg.ensure_dirs()
    stats: dict[str, int] = {"days": len(days), "matches": 0, "files": 0}

    ordered = sorted(days, key=lambda d: d.date)
    latest = ordered[-1] if ordered else None

    # 1. 今日首页 = 最新一日
    if latest:
        L.write(cfg, "index.html", P.render_day(cfg, latest, is_today=True))
        stats["files"] += 1

    # 2. 按日归档 + 单场落地页
    for d in ordered:
        rel = f"days/{d.date}.html"
        L.write(cfg, rel, P.render_day(cfg, d, is_today=False, rel=rel))
        stats["files"] += 1
        for m in d.matches:
            L.write(cfg, f"matches/{m.match_id}.html", P.render_match(cfg, m))
            stats["files"] += 1
            stats["matches"] += 1

    # 3. 归档索引
    L.write(cfg, "days/index.html", P.render_archive_index(cfg, [d.date for d in ordered]))
    stats["files"] += 1

    # 4. GEO 基建
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
