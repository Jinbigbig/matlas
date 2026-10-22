"""纯 SVG / HTML 组件库。

约束：
- 零第三方依赖（不引 Chart.js，不引 CDN），离线可跑、可长期归档；
- 所有图形都带文字标签，不靠颜色单独编码；
- 缺失数据直接省掉对应区块，不占位、不写「暂无」以外的解释句。
"""

from __future__ import annotations

import html
import math
import re
from typing import Sequence

# 配色常量与 jinbet 报告页 CSS 变量一致（--home / --away / --ink / --muted / --rule）
HOME_COLOR = "#2563eb"
AWAY_COLOR = "#f59e0b"
INK = "#111111"
MUTED = "#6b7280"
LINE = "#e5e7eb"


def esc(s: object) -> str:
    return html.escape(str(s) if s is not None else "")


def pct(p: float, nd: int = 1) -> str:
    """概率唯一渲染口径：所有百分比都过这个函数，避免同页出现不同精度。"""
    return f"{p * 100:.{nd}f}%"


# ---------------------------------------------------------------- 徽标 / 标签


def confidence_badge(conf: str, settled: bool | None = None) -> str:
    """置信度徽标。词表与配色同 jinbet 的 tag-* 系列。"""
    label = {"high": "高", "medium": "中", "low": "低", "none": "冷门"}.get(conf, "未评级")
    tone = {
        "high": ("rgba(16,185,129,0.12)", "#10b981"),
        "medium": ("rgba(245,158,11,0.14)", "#b45309"),
        "low": ("rgba(107,114,128,0.1)", "#6b7280"),
        "none": ("rgba(220,38,38,0.1)", "#dc2626"),
    }.get(conf, ("rgba(107,114,128,0.1)", "#6b7280"))
    bg, fg = tone
    hit = ""
    if settled is True:
        hit = '<span class="hit hit-y">命中</span>'
    elif settled is False:
        hit = '<span class="hit hit-n">未中</span>'
    return (
        f'<span class="badge" style="background:{bg};color:{fg}">置信度 {esc(label)}</span>{hit}'
    )


def prob_tag(p: float) -> str:
    """概率数字：>=60 强 / 45-60 中 / <45 弱。同一字形同一大小。"""
    cls = "p-hi" if p >= 0.60 else ("p-mid" if p >= 0.45 else "p-lo")
    return f'<span class="pct {cls}">{pct(p)}</span>'


def grade(prob: float, confidence: str = "medium") -> str:
    """方向评级。词表全局唯一：可用 / 慎用 / 别跟，不得另造。

    阈值与 jinbet 一致：
      ≥50% 且置信度非低 → 可用
      ≥42%             → 慎用
      其余              → 别跟
    """
    if prob >= 0.50 and confidence != "low":
        return "可用"
    if prob >= 0.42:
        return "慎用"
    return "别跟"


def grade_tag(prob: float, confidence: str = "medium") -> str:
    """评级标签，配色沿用 jinbet 的 tag-green / tag-yellow / tag-blue。"""
    g = grade(prob, confidence)
    bg = {
        "可用": "rgba(16,185,129,0.12)",
        "慎用": "rgba(245,158,11,0.14)",
        "别跟": "rgba(107,114,128,0.1)",
    }[g]
    fg = {"可用": "#10b981", "慎用": "#b45309", "别跟": "#6b7280"}[g]
    return f'<span class="badge" style="background:{bg};color:{fg}">{g}</span>'


def mini_tag(text: str) -> str:
    return f'<span class="mini">{esc(text)}</span>'


# ---------------------------------------------------------------- 赔率九宫格


def odds_grid(items: Sequence[tuple[str, str, str]]) -> str:
    """jinbet 同款三列赔率格。items = (标签, 数值, 语调 win/draw/loss/'')。"""
    if not items:
        return ""
    cells = "".join(
        f'<div class="odds-item"><div class="label">{esc(lab)}</div>'
        f'<div class="value {tone}">{val if val.startswith("<") else esc(val)}</div></div>'
        for lab, val, tone in items
    )
    return f'<div class="odds-grid">{cells}</div>'


def insight(label: str, value: str) -> str:
    if value in (None, ""):
        return ""
    return (
        f'<div class="insight-card"><div class="insight-label">{esc(label)}</div>'
        f'<div class="insight-value">{value if value.startswith("<") else esc(value)}</div></div>'
    )


def insight_grid(items: Sequence[tuple[str, str]]) -> str:
    cells = "".join(insight(k, v) for k, v in items)
    return f'<div class="insight-grid">{cells}</div>' if cells else ""


# ---------------------------------------------------------------- 近况圆点


def form_dots(outcomes: Sequence[str]) -> str:
    """近几场胜平负：W/D/L 圆点。outcomes 取 'W'/'D'/'L' 或中文首字。"""
    zh = {"W": ("胜", "w"), "D": ("平", "d"), "L": ("负", "l"),
          "胜": ("胜", "w"), "平": ("平", "d"), "负": ("负", "l")}
    dots = []
    for o in outcomes:
        if o is None:
            continue
        key = str(o).strip()[:1].upper()
        if key not in zh and str(o).strip()[:1] not in zh:
            continue
        label, cls = zh.get(key) or zh[str(o).strip()[:1]]
        dots.append(f'<span class="form-dot {cls}">{label}</span>')
    return f'<div class="form-row">{"".join(dots)}</div>' if dots else ""


_LOGO_OK = re.compile(r"^(https?://|/|\.{0,2}/|assets/)")
_ABS_LOGO = re.compile(r"^(https?://|/)")


def crest_img(team, cls: str = "crest", pre: str = "") -> str:
    """队徽。有合法 logo 出 <img>，没有则用队名首字做**同尺寸**圆形占位。

    占位不是假数据：它就是队名首字，作用是把卡片高度撑到和有队徽时一致，
    否则列表里会有的一半高一半矮。协议只放行 http(s) 与相对路径。
    站点相对路径（assets/...）按页深补 pre 前缀；绝对 URL 与根路径原样使用。
    """
    logo = (getattr(team, "logo", "") or "").strip()
    if logo and _LOGO_OK.match(logo):
        src = logo if _ABS_LOGO.match(logo) else pre + logo
        return (
            f'<img class="{cls}" src="{esc(src)}" alt="{esc(team.name)}队徽"'
            f' loading="lazy" width="48" height="48">'
        )
    initial = (getattr(team, "name", "") or "?").strip()[:1] or "?"
    return f'<div class="{cls} crest-ph" aria-hidden="true">{esc(initial)}</div>'


def team_side(team, side: str = "home", pre: str = "") -> str:
    """行内单侧队伍展示（队徽与队名同一行，用于窄幅版面）。"""
    name = f'<span class="{side}">{esc(team.name)}</span>'
    logo = (getattr(team, "logo", "") or "").strip()
    if not logo or not _LOGO_OK.match(logo):
        return name
    src = logo if _ABS_LOGO.match(logo) else pre + logo
    img = (
        f'<img class="crest" src="{esc(src)}" alt="{esc(team.name)}队徽"'
        f' loading="lazy" width="32" height="32">'
    )
    return f'<span class="tm">{img}{name}</span>'


def card_header(*, match_id: str = "", league: str = "", time_: str = "", extra: str = "") -> str:
    left = " ".join(
        f'<span class="{cls}">{esc(v)}</span>'
        for cls, v in (("match-id", match_id), ("match-league", league), ("match-time", time_))
        if v
    )
    right = extra or ""
    if not left and not right:
        return ""
    return f'<div class="card-header"><div>{left}</div><div>{right}</div></div>'


# ---------------------------------------------------------------- 表格


def table(headers: Sequence[str], rows: Sequence[Sequence[str]], *, cls: str = "") -> str:
    if not rows:
        return ""
    head = "".join(f"<th>{esc(h)}</th>" for h in headers)
    body = []
    for r in rows:
        tds = "".join(f"<td>{c if c.startswith('<') else esc(c)}</td>" for c in r)
        body.append(f"<tr>{tds}</tr>")
    return (
        f'<div class="tw"><table class="{cls}"><thead><tr>{head}</tr></thead>'
        f'<tbody>{"".join(body)}</tbody></table></div>'
    )


def duo_table(
    title: str,
    row_labels: Sequence[str],
    left_vals: Sequence[str],
    right_vals: Sequence[str],
    left_name: str,
    right_name: str,
) -> str:
    """主 / 客对照表：项目 | 主队 | 客队。值缺就整行不画。"""
    rows = []
    for lab, a, b in zip(row_labels, left_vals, right_vals):
        if a in (None, "", "-") and b in (None, "", "-"):
            continue
        rows.append([lab, a, b])
    if not rows:
        return ""
    return table([title, left_name, right_name], rows, cls="duo")


# ---------------------------------------------------------------- 雷达图


def radar_svg(
    home_vals: Sequence[float],
    away_vals: Sequence[float],
    axes: Sequence[str],
    home_name: str,
    away_name: str,
    *,
    size: int = 320,
    max_val: float = 100.0,
) -> str:
    """六维战力雷达。纯 SVG，含图例与轴刻度，不依赖颜色单独区分两队。"""
    n = len(axes)
    if n < 3:
        return ""
    cx = cy = size / 2
    r = size / 2 - 46
    rings = (0.25, 0.5, 0.75, 1.0)

    def pt(i: int, ratio: float) -> tuple[float, float]:
        ang = -math.pi / 2 + 2 * math.pi * i / n
        return cx + r * ratio * math.cos(ang), cy + r * ratio * math.sin(ang)

    parts: list[str] = [
        f'<svg class="radar" viewBox="0 0 {size} {size}" role="img" '
        f'aria-label="{esc(home_name)} 与 {esc(away_name)} 六维战力对比">'
    ]

    for ring in rings:
        poly = " ".join(f"{x:.1f},{y:.1f}" for x, y in (pt(i, ring) for i in range(n)))
        parts.append(
            f'<polygon points="{poly}" fill="none" stroke="{LINE}" stroke-width="1"/>'
        )
    for i in range(n):
        x, y = pt(i, 1.0)
        parts.append(f'<line x1="{cx}" y1="{cy}" x2="{x:.1f}" y2="{y:.1f}" stroke="{LINE}" stroke-width="1"/>')

    def series(vals: Sequence[float], color: str, dash: str) -> None:
        nonlocal parts
        poly = " ".join(
            f"{x:.1f},{y:.1f}"
            for x, y in (pt(i, max(0.0, min(1.0, v / max_val))) for i, v in enumerate(vals))
        )
        parts.append(
            f'<polygon points="{poly}" fill="{color}" fill-opacity="0.14" '
            f'stroke="{color}" stroke-width="1.6" stroke-dasharray="{dash}"/>'
        )
        for i, v in enumerate(vals):
            x, y = pt(i, max(0.0, min(1.0, v / max_val)))
            parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2.6" fill="{color}"/>')

    series(away_vals, AWAY_COLOR, "0")
    series(home_vals, HOME_COLOR, "0")

    for i, name in enumerate(axes):
        x, y = pt(i, 1.19)
        anchor = "middle"
        if x > cx + 6:
            anchor = "start"
        elif x < cx - 6:
            anchor = "end"
        parts.append(
            f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}" dominant-baseline="central" '
            f'font-size="12" fill="{MUTED}">{esc(name)}</text>'
        )
    parts.append(f'<text x="{cx}" y="{size - 8}" text-anchor="middle" font-size="10" fill="{MUTED}">0–100</text>')
    parts.append("</svg>")

    legend = (
        '<div class="legend">'
        f'<span><i style="background:{HOME_COLOR}"></i>{esc(home_name)}（实线）</span>'
        f'<span><i style="background:{AWAY_COLOR}"></i>{esc(away_name)}（实线）</span>'
        "</div>"
    )
    return legend + "".join(parts)


# ---------------------------------------------------------------- 走势曲线


def momentum_svg(
    labels: Sequence[str],
    home: Sequence[float],
    away: Sequence[float],
    home_name: str,
    away_name: str,
    *,
    w: int = 560,
    h: int = 200,
) -> str:
    """进球威胁度随时间变化。两条线用色 + 虚实 + 端点标记三重区分。"""
    if len(labels) < 2 or len(home) != len(labels) or len(away) != len(labels):
        return ""
    pad_l, pad_r, pad_t, pad_b = 34, 12, 14, 26
    iw, ih = w - pad_l - pad_r, h - pad_t - pad_b
    top = max(1.0, max(home), max(away)) * 1.15

    def xy(i: int, v: float) -> tuple[float, float]:
        return pad_l + iw * i / (len(labels) - 1), pad_t + ih * (1 - v / top)

    parts = [f'<svg class="mom" viewBox="0 0 {w} {h}" role="img" aria-label="全场进球威胁度走势">']
    for frac in (0.0, 0.5, 1.0):
        y = pad_t + ih * frac
        parts.append(f'<line x1="{pad_l}" y1="{y:.1f}" x2="{w - pad_r}" y2="{y:.1f}" stroke="{LINE}" stroke-width="1"/>')
        val = int(round(top * (1 - frac)))
        parts.append(
            f'<text x="{pad_l - 6}" y="{y:.1f}" text-anchor="end" dominant-baseline="central" '
            f'font-size="10" fill="{MUTED}">{val}</text>'
        )

    def line(vals: Sequence[float], color: str, dash: str, name: str) -> None:
        pts = [xy(i, v) for i, v in enumerate(vals)]
        d = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
        parts.append(
            f'<polyline points="{d}" fill="none" stroke="{color}" stroke-width="2" '
            f'stroke-dasharray="{dash}" stroke-linejoin="round"/>'
        )
        for x, y in pts:
            parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2.6" fill="#fff" stroke="{color}" stroke-width="1.6"/>')
        lx, ly = pts[-1]
        parts.append(
            f'<text x="{lx - 4:.1f}" y="{ly - 8:.1f}" text-anchor="end" font-size="11" fill="{color}">{esc(name)}</text>'
        )

    line(home, HOME_COLOR, "0", home_name)
    line(away, AWAY_COLOR, "5 3", away_name)

    for i, lab in enumerate(labels):
        x = pad_l + iw * i / (len(labels) - 1)
        parts.append(
            f'<text x="{x:.1f}" y="{h - 8}" text-anchor="middle" font-size="10" fill="{MUTED}">{esc(lab)}</text>'
        )
    parts.append("</svg>")
    legend = (
        '<div class="legend">'
        f'<span><i style="background:{HOME_COLOR}"></i>{esc(home_name)}（实线）</span>'
        f'<span><i style="background:{AWAY_COLOR}"></i>{esc(away_name)}（虚线）</span>'
        "</div>"
    )
    return legend + "".join(parts)


# ---------------------------------------------------------------- 主推 / 风险 / 对照


def main_pick_bar(text: str, *, tag: str = "", hit: bool | None = None) -> str:
    """一句话主推。整页视觉重心之一，放在四宫格上方。

    `tag` 传已渲染好的评级标签（走 grade_tag，词表只有 可用/慎用/别跟）。
    """
    if not text:
        return ""
    mark = ""
    if hit is True:
        mark = '<span class="hit hit-y">命中</span>'
    elif hit is False:
        mark = '<span class="hit hit-n">未中</span>'
    return (
        f'<div class="mainpick"><div class="mp-lab">主推</div>'
        f'<div class="mp-txt">{esc(text)}</div>'
        f'<div class="mp-tag">{tag}{mark}</div></div>'
    )


def risk_note(level: str, note: str, factors: Sequence[str] = ()) -> str:
    """风险提示条。level: info / warn / block，决定左侧色条与标签。"""
    if not note and not factors:
        return ""
    label, cls = {
        "info": ("提示", "r-info"),
        "warn": ("注意", "r-warn"),
        "block": ("否决", "r-block"),
    }.get(level, ("提示", "r-info"))
    items = "".join(f"<li>{esc(f)}</li>" for f in factors if f)
    ul = f'<ul class="risk-factors">{items}</ul>' if items else ""
    body = f'<div class="risk-txt">{esc(note)}</div>' if note else ""
    return (
        f'<div class="risk-note {cls}">'
        f'<span class="risk-lab">{esc(label)}</span>{body}{ul}</div>'
    )


def reference_table(
    rows: Sequence[tuple[str, str, str]],
    *,
    source: str = "",
    url: str = "",
    license_: str = "",
) -> str:
    """第三方对照表。rows = (维度, 本站, 外部)。

    值按**已渲染 HTML** 处理，原样插入（调用方负责转义文本部分），
    这样才能在单元格里放 prob_tag / 命中徽标。
    """
    if not rows:
        return ""
    head = f'<th>维度</th><th>本站</th>'
    head += f"<th>{esc(source) or '外部'}</th>"
    trs = "".join(
        f"<tr><td>{esc(dim)}</td><td>{ours}</td><td>{theirs}</td></tr>"
        for dim, ours, theirs in rows
    )
    note = ""
    if source:
        src = f'<a href="{esc(url)}">{esc(source)}</a>' if url else esc(source)
        note = f'<p class="panel-hint">外部对照：{src}'
        note += f"（{esc(license_)}）" if license_ else ""
        note += "　仅供比对，不参与本站结论</p>"
    return (
        f'<div class="tw"><table class="ref-table"><thead><tr>{head}</tr></thead>'
        f"<tbody>{trs}</tbody></table></div>{note}"
    )


# ---------------------------------------------------------------- 卡片


def panel(title: str, body: str, *, hint: str = "") -> str:
    if not body:
        return ""
    h = f'<p class="panel-hint">{esc(hint)}</p>' if hint else ""
    return (
        f'<section class="panel"><h3>{esc(title)}</h3>{h}{body}</section>'
    )


def kv_rows(pairs: Sequence[tuple[str, str]]) -> str:
    rows = [[k, v] for k, v in pairs if v not in (None, "")]
    return table(["项目", "内容"], rows, cls="kv") if rows else ""
