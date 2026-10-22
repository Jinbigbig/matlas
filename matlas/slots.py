"""槽位登记表：页面每个功能块 ↔ 契约字段 ↔ 数据来源 ↔ 接线状态。

这是「留记号」的唯一出处。框架（渲染层）先全部铺好，数据谁供、什么时候供，
都记在这张表里；换源只改这里和对应适配器，不动渲染层。

约定：
  - status = "ready"    渲染层已接、契约已通，缺数据时自动省略该块
  - status = "pending"  契约已留位，但还没有任何源往里写
  - status = "todo"     连生成逻辑都还没有（需要新写代码）

注意：`status` 只描述**框架**，不描述今天线上有没有数据。
今天没有数据的块，页面会自动不画 —— 这是刻意设计，不是缺陷。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Slot:
    key: str            # 契约字段 / 渲染函数标识
    name: str           # 页面上叫什么
    contract: str       # 契约字段
    sources: tuple[str, ...]  # 候选数据来源（按优先级）
    status: str         # ready / pending / todo
    note: str = ""


SLOTS: tuple[Slot, ...] = (
    # ---------------- 结论区 ----------------
    Slot(
        "main_pick", "主推", "Match.main_pick",
        ("jinbet V3.4 引擎结论摘要",), "ready",
        "一句话主推，页面第一视觉重心；缺则整块不出现",
    ),
    Slot(
        "confidence", "置信度", "Match.confidence",
        ("jinbet 引擎",), "ready",
        "词表固定 高/中/低/冷门",
    ),
    Slot(
        "forecasts", "四宫格结论", "Match.forecasts[]",
        ("jinbet 引擎 V3.4",), "ready",
        "方向/比分/进球/半全场，各带首选+次选与概率",
    ),
    Slot(
        "handicap", "让球结论", "Match.handicap",
        ("jinbet 让球分级（RULES §3.3 阈值已定）",), "ready",
        "盘口赔率在 Odds.handicap*，结论在 Handicap，两者分离",
    ),
    Slot(
        "risk", "风险提示", "Match.risk",
        ("jinbet 冷门过滤 / 风险否决", "人工标注"), "ready",
        "三档 info/warn/block；block 不隐藏页面，留档必须完整",
    ),
    # ---------------- 数据区 ----------------
    Slot(
        "metrics", "六维战力雷达", "Match.metrics_home / metrics_away",
        ("jinbet 引擎六维",), "ready",
        "轴：进攻/防守/控制/状态/阵容/战意（与球小策 radar 六轴同名）",
    ),
    Slot(
        "momentum", "进球威胁度走势", "Match.momentum",
        ("jinbet λ 曲线离散化",), "ready",
        "7 点标签 0'~90'，与球小策 momentum 同构",
    ),
    Slot(
        "odds", "市场数据", "Match.odds",
        ("竞彩官方", "7M", "腾讯体育"), "pending",
        "**没有任何抓取适配器** —— 现在只能靠上游写进 JSON",
    ),
    Slot(
        "standings", "积分排名", "Team.rank/points/played/win/draw/loss/gf/ga",
        ("腾讯 matchweb rank/listV2", "Fox Sports SSR", "7M", "懂球帝 standing"), "ready",
        "四个源在 jinbet 侧已验证可用，Matlas 侧只消费字段",
    ),
    Slot(
        "h2h", "历史交锋", "Match.h2h[]",
        ("懂球帝 pre_analysis_v1", "香港赛马会赛前简报", "results_data.json"), "ready",
    ),
    Slot(
        "recent", "近期战绩", "Match.recent_home / recent_away[]",
        ("results_data.json（官方赛果库，自 2025-12-31）",), "ready",
    ),
    Slot(
        "injuries", "伤停与缺阵", "Match.injuries[]",
        ("lineupstoday", "香港赛马会赛前简报", "德甲/荷甲官方"), "ready",
    ),
    Slot(
        "reference", "外部对照", "Match.reference",
        (
            "球小策开源数据集 ddzyx/qiuxiaoce-football-data（CC BY-NC 4.0，每日约 3 场）",
            "Agent Skill: qiuxiaoce-football-data@2.14.0（/match-pack/{id}，50 点/场）",
        ), "ready",
        "只做比对，永不参与本站概率计算；必须署名留链",
    ),
    # ---------------- 留档区 ----------------
    Slot(
        "ledger", "留档核验", "Match.fingerprint()",
        ("本地计算 sha256",), "ready",
        "只覆盖赛前字段，赛后回填不改变指纹",
    ),
    Slot(
        "result", "赛果结算", "Match.result",
        ("官方赛果源（results_data.json 等）",), "todo",
        "**目标缺口**：result.*_hit 目前靠人工填，没有 settle 函数按比分自动判定",
    ),
)


def by_status(status: str) -> list[Slot]:
    return [s for s in SLOTS if s.status == status]


def summary() -> str:
    total = len(SLOTS)
    ready = len(by_status("ready"))
    pending = len(by_status("pending"))
    todo = len(by_status("todo"))
    return f"槽位 {total} 个：已接线 {ready} / 待接线 {pending} / 待开发 {todo}"


def markdown() -> str:
    """生成 SLOTS.md。代码是唯一出处，文档只是它的投影。"""
    icon = {"ready": "✅", "pending": "⏸", "todo": "❌"}
    lines = [
        "# 槽位登记表",
        "",
        "> 本文件由 `matlas/slots.py` 生成，**不要手改** —— 改代码里的 `SLOTS` 再重新生成。",
        f"> 当前：{summary()}",
        "",
        "框架（渲染层）已为每个槽位铺好，缺数据时该块自动不渲染；",
        "数据由谁供、什么时候供，全部记在这张表里。换源只改本表和对应适配器。",
        "",
        "| 状态 | 模块 | 契约字段 | 数据来源（按优先级） | 备注 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for s in SLOTS:
        src = "<br>".join(s.sources) if s.sources else "—"
        lines.append(
            f"| {icon.get(s.status, '·')} | **{s.name}** | `{s.contract}` | {src} | {s.note} |"
        )
    lines += [
        "",
        "## 状态含义",
        "",
        "- ✅ **ready**：渲染层已接、契约已通。今天没数据只会让该块消失，不影响构建。",
        "- ⏸ **pending**：契约留了位，但还没有任何源往里写。",
        "- ❌ **todo**：连生成逻辑都没有，需要新写代码。",
        "",
        "## Agent Skill 记号",
        "",
        "球小策的官方 Skill 包（`qiuxiaoce-football-data`）可作为外部对照与高阶指标的候补源，",
        "接入方式与计费已在调研中记录，**当前不启用**，仅在上表第 13 项留位。",
        "",
    ]
    return "\n".join(lines)
