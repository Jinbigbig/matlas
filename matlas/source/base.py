"""数据源适配层。

设计意图：Matlas **不自带任何采集能力**。
它只认「符合 models.Match 契约的字典」，上游是谁无所谓 ——
本地 JSON、jinbet 引擎导出的结果、第三方接口，都走同一个入口。

已实现：
  - LocalDirSource    读 data/days/*.json（默认，离线可用）
  - QiuxiaoceReference 对照源适配器（默认关闭，见 RULES.md §5）

待接线（等下一步指示）：
  - JinbetBridge     接 jinbet V3.4 引擎产物
  - OddsScraper      赔率 / 积分榜 / 阵容抓取
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Protocol

from ..models import Day, Match


class DataSource(Protocol):
    name: str

    def load_days(self) -> list[Day]:
        ...


class LocalDirSource:
    """本地每日 JSON 数据源。每个文件对应一个交易日。"""

    name = "local"

    def __init__(self, days_dir: Path, only: Iterable[str] | None = None):
        self.days_dir = Path(days_dir)
        self.only = set(only) if only else None

    def load_days(self) -> list[Day]:
        if not self.days_dir.exists():
            return []
        days: list[Day] = []
        for p in sorted(self.days_dir.glob("*.json")):
            if self.only and p.stem not in self.only:
                continue
            raw = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(raw, dict) and "matches" in raw:
                days.append(Day.from_dict(raw))
            elif isinstance(raw, list):
                days.append(Day(date=p.stem, matches=[Match.from_dict(m) for m in raw]))
        return sorted(days, key=lambda d: d.date)


def merge_reference(day: Day, ref: dict[str, Any], source_label: str) -> Day:
    """把对照源结论并入当日数据，放进 `extras.reference`，不覆盖主结论。

    对照源永远只是「别人怎么看」，不参与本站任何概率计算，
    页面上也会单独标注来源，避免与主结论混排。
    """
    idx = {str(r.get("code", "")): r for r in ref.get("matches", [])}
    for m in day.matches:
        r = idx.get(m.code)
        if not r:
            continue
        m.extras.setdefault("reference", {
            "source": source_label,
            "label": r.get("label", ""),
            "level": r.get("level", ""),
        })
    return day
