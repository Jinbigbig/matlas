"""数据契约层。

这里是整个项目的地基，也是唯一「对外契约」：
无论上游是 jinbet 的 V3.4 引擎、任何第三方数据商的接口，
还是手写的 JSON，只要产出的字典能通过 `Match.from_dict` 解析，
下游全部页面、Schema.org、llms.txt、sitemap 就能直接跑通。

设计原则：
1. 字段尽量可选（None 即「这一项今天没有」，页面会自动省掉对应区块）；
2. 不承载任何推导过程，只承载「结论」与「支撑它的数字」；
3. 结论部分可单独哈希，用于「赛前固化、赛后回填」的不可篡改台账。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, asdict
from datetime import date as _date
from typing import Any, Iterable

SCHEMA_VERSION = "1.0"

CONFIDENCE_ORDER = {"high": 0, "medium": 1, "low": 2, "none": 3}
CONFIDENCE_LABEL = {
    "high": "高",
    "medium": "中",
    "low": "低",
    "none": "冷门",
}


def _clean(d: dict[str, Any]) -> dict[str, Any]:
    """丢掉所有 None 值，让 JSON 保持精简。"""
    out: dict[str, Any] = {}
    for k, v in d.items():
        if v is None:
            continue
        if isinstance(v, dict):
            v = _clean(v)
        elif isinstance(v, list):
            v = [_clean(x) if isinstance(x, dict) else x for x in v]
        out[k] = v
    return out


# ---------------------------------------------------------------- 子结构


@dataclass
class Team:
    name: str
    slug: str = ""
    league: str = ""
    country: str = ""
    rank: int | None = None
    points: int | None = None
    played: int | None = None
    win: int | None = None
    draw: int | None = None
    loss: int | None = None
    gf: int | None = None
    ga: int | None = None
    form: str = ""          # 近 5 场，如 "WWDLW"，左旧右新
    logo: str = ""

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Team":
        return cls(**{k: v for k, v in d.items() if k in cls.__annotations__})


@dataclass
class Metrics:
    """六维战力，0-100，用于雷达图。缺项填 None 会自动塌到 0 且不画该轴标签外的点。"""

    attack: float = 0.0
    defence: float = 0.0
    control: float = 0.0
    form: float = 0.0
    value: float = 0.0
    motivation: float = 0.0

    AXES: tuple[tuple[str, str], ...] = field(
        default=(
            ("attack", "进攻"),
            ("defence", "防守"),
            ("control", "控制"),
            ("form", "状态"),
            ("value", "阵容"),
            ("motivation", "战意"),
        ),
        repr=False,
    )

    def values(self) -> list[float]:
        return [float(getattr(self, k)) for k, _ in Metrics.AXES]

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Metrics":
        return cls(**{k: float(v) for k, v in d.items() if k in cls.__annotations__ and k != "AXES"})


@dataclass
class Odds:
    """赔率与市场。全部可选，有就渲染，没有就跳过整块。"""

    home: float | None = None
    draw: float | None = None
    away: float | None = None
    handicap: float | None = None      # 主队让球，负值为受让
    handicap_home: float | None = None
    handicap_away: float | None = None
    total: float | None = None         # 进球数盘口线，如 2.5
    over: float | None = None
    under: float | None = None
    bookmaker: str = ""

    def implied(self) -> dict[str, float] | None:
        """去水后的 1X2 隐含概率，仅在国内合规语境下作为「市场参考」展示。"""
        if not (self.home and self.draw and self.away):
            return None
        s = 1 / self.home + 1 / self.draw + 1 / self.away
        return {
            "home": round(1 / self.home / s, 4),
            "draw": round(1 / self.draw / s, 4),
            "away": round(1 / self.away / s, 4),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Odds":
        return cls(**{k: v for k, v in d.items() if k in cls.__annotations__})


@dataclass
class Forecast:
    """一条推演结论。kind 决定它落在落地页的哪个宫格。"""

    KINDS = ("direction", "score", "goals", "htft")

    kind: str
    label: str          # 展示文本，如 "主胜" / "2-1" / "3 球" / "平-胜"
    prob: float         # 0-1
    rank: int = 1       # 1 = 首选
    note: str = ""

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Forecast":
        return cls(
            kind=str(d.get("kind", "")),
            label=str(d.get("label", "")),
            prob=float(d.get("prob", 0.0)),
            rank=int(d.get("rank", 1)),
            note=str(d.get("note", "")),
        )


@dataclass
class H2HItem:
    date: str = ""
    competition: str = ""
    home: str = ""
    away: str = ""
    score: str = ""
    home_id: str = ""


@dataclass
class RecentItem:
    date: str = ""
    competition: str = ""
    opponent: str = ""
    venue: str = ""     # home / away
    score: str = ""
    outcome: str = ""   # W / D / L


@dataclass
class Injury:
    team: str = ""      # home / away
    player: str = ""
    reason: str = ""
    status: str = ""    # out / doubt / suspended


@dataclass
class Result:
    """赛后回填。半场/全场比分 + 四个维度是否命中。"""

    half_score: str = ""
    full_score: str = ""
    direction_hit: bool | None = None
    score_hit: bool | None = None
    goals_hit: bool | None = None
    htft_hit: bool | None = None
    settled_at: str = ""

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Result":
        return cls(**{k: v for k, v in d.items() if k in cls.__annotations__})


@dataclass
class Momentum:
    """0-90 分钟进球威胁度，用于逐场落地页的走势曲线。"""

    labels: list[str] = field(default_factory=list)
    home: list[float] = field(default_factory=list)
    away: list[float] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Momentum":
        return cls(
            labels=list(d.get("labels", [])),
            home=[float(x) for x in d.get("home", [])],
            away=[float(x) for x in d.get("away", [])],
        )


# ---------------------------------------------------------------- 主结构


@dataclass
class Match:
    match_id: str                    # 全局唯一，用于 URL 与文件名
    day: str                         # YYYY-MM-DD
    code: str = ""                   # 编号，如 "周三004"
    competition: str = ""
    round: str = ""
    kickoff: str = ""                # ISO8601 或 "YYYY-MM-DD HH:MM"
    venue: str = ""

    home: Team = field(default_factory=lambda: Team(name=""))
    away: Team = field(default_factory=lambda: Team(name=""))

    odds: Odds | None = None
    metrics_home: Metrics | None = None
    metrics_away: Metrics | None = None
    momentum: Momentum | None = None

    forecasts: list[Forecast] = field(default_factory=list)
    confidence: str = "none"         # high / medium / low / none
    is_cold_start: bool = False      # 冷启动：样本不足，不进精选

    h2h: list[H2HItem] = field(default_factory=list)
    recent_home: list[RecentItem] = field(default_factory=list)
    recent_away: list[RecentItem] = field(default_factory=list)
    injuries: list[Injury] = field(default_factory=list)

    result: Result | None = None
    source_url: str = ""
    generated_at: str = ""
    extras: dict[str, Any] = field(default_factory=dict)

    # ---- 派生 ----

    @property
    def title(self) -> str:
        return f"{self.home.name} vs {self.away.name}"

    @property
    def confidence_label(self) -> str:
        return CONFIDENCE_LABEL.get(self.confidence, "未评级")

    @property
    def slug(self) -> str:
        return self.match_id

    def forecasts_of(self, kind: str) -> list[Forecast]:
        return sorted(
            [f for f in self.forecasts if f.kind == kind],
            key=lambda f: (f.rank, -f.prob),
        )

    @property
    def headline(self) -> dict[str, Forecast | None]:
        """四宫格首选。缺哪一维就退化为空，页面自动不画该宫格。"""
        return {k: (self.forecasts_of(k) or [None])[0] for k in Forecast.KINDS}

    def fingerprint(self) -> str:
        """结论指纹。

        只对「赛前结论 + 对阵 + 开球时间」取哈希，不含任何赛后字段。
        赛后回填 `result` 重建页面时，这个指纹必须保持不变 ——
        这是「结论没有事后被改过」的验证点。
        """
        payload = {
            "match_id": self.match_id,
            "day": self.day,
            "home": self.home.name,
            "away": self.away.name,
            "kickoff": self.kickoff,
            "forecasts": [
                {"kind": f.kind, "label": f.label, "prob": round(f.prob, 6), "rank": f.rank}
                for f in sorted(self.forecasts, key=lambda x: (x.kind, x.rank, x.label))
            ],
            "confidence": self.confidence,
            "odds": asdict(self.odds) if self.odds else None,
        }
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]

    # ---- IO ----

    def to_dict(self) -> dict[str, Any]:
        return _clean(
            {
                "schema": SCHEMA_VERSION,
                "match_id": self.match_id,
                "day": self.day,
                "code": self.code,
                "competition": self.competition,
                "round": self.round,
                "kickoff": self.kickoff,
                "venue": self.venue,
                "home": asdict(self.home),
                "away": asdict(self.away),
                "odds": asdict(self.odds) if self.odds else None,
                "metrics_home": asdict(self.metrics_home) if self.metrics_home else None,
                "metrics_away": asdict(self.metrics_away) if self.metrics_away else None,
                "momentum": asdict(self.momentum) if self.momentum else None,
                "forecasts": [asdict(f) for f in self.forecasts],
                "confidence": self.confidence,
                "is_cold_start": self.is_cold_start,
                "h2h": [asdict(x) for x in self.h2h],
                "recent_home": [asdict(x) for x in self.recent_home],
                "recent_away": [asdict(x) for x in self.recent_away],
                "injuries": [asdict(x) for x in self.injuries],
                "result": asdict(self.result) if self.result else None,
                "source_url": self.source_url,
                "generated_at": self.generated_at,
                "extras": self.extras or None,
            }
        )

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Match":
        ver = d.get("schema")
        if ver and ver.split(".")[0] != SCHEMA_VERSION.split(".")[0]:
            raise ValueError(f"数据契约主版本不匹配：期望 {SCHEMA_VERSION}，实到 {ver}")
        return cls(
            match_id=str(d["match_id"]),
            day=str(d.get("day", "")) or str(d.get("kickoff", ""))[:10],
            code=str(d.get("code", "")),
            competition=str(d.get("competition", "")),
            round=str(d.get("round", "")),
            kickoff=str(d.get("kickoff", "")),
            venue=str(d.get("venue", "")),
            home=Team.from_dict(d.get("home") or {}),
            away=Team.from_dict(d.get("away") or {}),
            odds=Odds.from_dict(d.get("odds") or {}) if d.get("odds") else None,
            metrics_home=Metrics.from_dict(d["metrics_home"]) if d.get("metrics_home") else None,
            metrics_away=Metrics.from_dict(d["metrics_away"]) if d.get("metrics_away") else None,
            momentum=Momentum.from_dict(d["momentum"]) if d.get("momentum") else None,
            forecasts=[Forecast.from_dict(x) for x in d.get("forecasts", [])],
            confidence=str(d.get("confidence", "none")),
            is_cold_start=bool(d.get("is_cold_start", False)),
            h2h=[H2HItem(**x) for x in d.get("h2h", [])],
            recent_home=[RecentItem(**x) for x in d.get("recent_home", [])],
            recent_away=[RecentItem(**x) for x in d.get("recent_away", [])],
            injuries=[Injury(**x) for x in d.get("injuries", [])],
            result=Result.from_dict(d["result"]) if d.get("result") else None,
            source_url=str(d.get("source_url", "")),
            generated_at=str(d.get("generated_at", "")),
            extras=d.get("extras") or {},
        )


@dataclass
class Day:
    date: str
    matches: list[Match] = field(default_factory=list)
    note: str = ""

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Day":
        date = str(d.get("date", ""))
        return cls(
            date=date,
            matches=[Match.from_dict({**m, "day": m.get("day", date)}) for m in d.get("matches", [])],
            note=str(d.get("note", "")),
        )


def sort_matches(ms: Iterable[Match]) -> list[Match]:
    """排序：先按开球时间，再按编号。同时间用编号兜底，保证每日顺序稳定。"""
    return sorted(ms, key=lambda m: (m.kickoff or "9999", m.code or "zzz"))
