"""页面渲染：今日列表、单场落地页、按日归档、归档索引。"""

from __future__ import annotations

import datetime as dt
import math
import re
from dataclasses import replace
from typing import Any

from ..config import Config
from ..models import Match, Day, Metrics, Momentum, Odds, sort_matches
from .. import logos
from . import components as C
from . import layout as L


# ---------------------------------------------------------------- 单场落地页


def _picks(m: Match) -> str:
    """四宫格：方向 / 比分 / 进球 / 半全。缺哪维就不画哪格。

    半全场：无预测结论但已结算的历史场次，展示「实际赛果」而非占位——
    半全场结果由半场/全场比分推导，是赛果数据，不需要等预测存档。
    """
    titles = {"direction": "方向", "score": "比分", "goals": "进球", "htft": "半全场"}
    cells = []
    for kind, title in titles.items():
        items = m.forecasts_of(kind)
        if not items:
            if kind == "htft":
                act = _actual_htft(m)
                if act:
                    cells.append(
                        f'<div class="pick"><div class="lab">{title}</div>'
                        f'<div class="val">{act}</div>'
                        '<div class="mini">实际赛果</div></div>'
                    )
                else:
                    cells.append(
                        '<div class="pick pick-ph"><div class="lab">半全场</div>'
                        '<div class="mini">待接入</div></div>'
                    )
            continue
        top = items[0]
        extra = ""
        if len(items) > 1:
            extra = f'<span class="mini">次选 {C.esc(items[1].label)} {C.pct(items[1].prob)}</span>'
        cells.append(
            f'<div class="pick"><div class="lab">{title}</div>'
            f'<div class="val">{C.esc(top.label)}</div>'
            f'<div>{C.prob_tag(top.prob)}</div>'
            f'<div style="margin-top:6px">{extra}</div></div>'
        )
    return f'<div class="picks4">{"".join(cells)}</div>' if cells else ""


def _tick_hcp(p: dict) -> str | None:
    """快照里的主让球档位（让球数组首项）。"""
    rq = p.get("让球") or []
    if rq:
        v = rq[0].get("handicap")
        if v not in (None, ""):
            return str(v)
    return None


def _tick_num(v) -> float | None:
    try:
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _odds_trend(m: Match) -> str:
    """赔率时序：11:10 初盘 / 14:00 / 19:00 三次快照，胜平负三线 + 让球。"""
    tk = (m.extras or {}).get("odds_ticks") or []
    if not tk:
        return ""
    pts = []
    for p in tk:
        pts.append({
            "label": str(p.get("t", ""))[-5:],
            "home": _tick_num(p.get("胜")),
            "draw": _tick_num(p.get("平")),
            "away": _tick_num(p.get("负")),
            "hcp": _tick_num(_tick_hcp(p)),
        })
    # 桌面铺满面板、移动端用 620 宽的紧凑版：同一份 SVG 只换 viewBox 会让小屏字号过小，故按屏宽切换
    wide = C.odds_lines_svg(pts, w=1000)
    compact = C.odds_lines_svg(pts, w=620)
    if not compact:
        return ""
    chart = (f'<div class="chart-wide">{wide}</div>'
             f'<div class="chart-narrow">{compact}</div>')

    base = pts[0]
    rows = []
    for i, p in enumerate(pts):
        hcp_txt = f"{p['hcp']:+g}" if p["hcp"] is not None else "—"
        hcp_txt = hcp_txt.replace("+0", "0")
        cells = [f"{v:.2f}" if v is not None else "—"
                 for v in (p["home"], p["draw"], p["away"])]
        if i == 0:
            rows.append([f"{p['label']} 初盘", *cells, hcp_txt, "—"])
            continue
        bits = []
        for key, lab in (("home", "主胜"), ("draw", "平"), ("away", "客胜")):
            if p[key] is not None and base[key] is not None and abs(p[key] - base[key]) >= 0.005:
                bits.append(f"{lab} {p[key] - base[key]:+.2f}")
        if p["hcp"] != base["hcp"]:
            b_h = f"{base['hcp']:+g}".replace("+0", "0") if base["hcp"] is not None else "—"
            bits.insert(0, f"让球 {b_h}→{hcp_txt}")
        rows.append([p["label"], *cells, hcp_txt, " · ".join(bits) or "未变"])
    table = C.table(["时点", "主胜", "平", "客胜", "让球", "较初盘"], rows)
    has_hcp = any(p["hcp"] is not None for p in pts)
    return ('<div class="of-sec"><div class="of-h">赔率变化</div>'
            + C.odds_lines_legend(has_hcp)
            + chart + table + "</div>")


def _odds_panel(m: Match) -> str:
    """赔率数据：胜平负格 + 盘口表 + 全玩法 + 时序变化曲线。"""
    o = m.odds
    tk = (m.extras or {}).get("odds_ticks") or []
    of = (m.extras or {}).get("odds_full") or {}
    # 表头数字取最新快照，与下方曲线同一口径
    last = tk[-1] if tk else {}
    nh, nd, na = (_tick_num(last.get("胜")), _tick_num(last.get("平")),
                  _tick_num(last.get("负")))
    if nh and nd and na:
        o = replace(o, home=nh, draw=nd, away=na) if o else Odds(home=nh, draw=nd, away=na)
    # 无基础赔率的场次，胜平负取全玩法里的 spf
    if not (o and o.home and o.draw and o.away):
        spf = of.get("spf") or {}
        sh, sd, sa = (_tick_num(spf.get("胜")), _tick_num(spf.get("平")),
                      _tick_num(spf.get("负")))
        if sh and sd and sa:
            o = replace(o, home=sh, draw=sd, away=sa) if o else Odds(home=sh, draw=sd, away=sa)
    rq = ((last.get("让球") or [None])[0]
          or (of.get("rq") or [None])[0]
          or {})
    hcp_val = _tick_num(rq.get("handicap"))
    if hcp_val is not None:
        if not o:
            o = Odds()
        o = replace(o, handicap=hcp_val,
                    handicap_home=_tick_num(rq.get("胜")),
                    handicap_away=_tick_num(rq.get("负")))
    rq_draw = _tick_num(rq.get("平"))

    body = ""
    imp = (o.implied() or {}) if o else {}
    grid_rows: list[tuple[str, str, str]] = []
    if o and o.home and o.draw and o.away:
        grid_rows = [
            (f"{m.home.name} 胜", f"{o.home:.2f}", "win"),
            ("平", f"{o.draw:.2f}", "draw"),
            (f"{m.away.name} 胜", f"{o.away:.2f}", "loss"),
        ]
    grid = C.odds_grid(grid_rows)

    rows = []
    if o and o.home and o.draw and o.away:
        rows.append(["胜平负", f"{o.home:.2f}", f"{o.draw:.2f}", f"{o.away:.2f}"])
    if imp:
        # §3.2：概率一律走 prob_tag，不裸写百分比
        rows.append([
            "去水概率",
            C.prob_tag(imp["home"]),
            C.prob_tag(imp["draw"]),
            C.prob_tag(imp["away"]),
        ])
    if o and o.handicap is not None and (o.handicap_home or o.handicap_away):
        rows.append([
            f"让球 {o.handicap:+g}".replace("+0", "0"),
            f"{o.handicap_home:.2f}" if o.handicap_home else "—",
            f"{rq_draw:.2f}" if rq_draw else "—",
            f"{o.handicap_away:.2f}" if o.handicap_away else "—",
        ])
    if o and o.total is not None and (o.over or o.under):
        rows.append([
            f"进球数 {o.total:g}",
            f"大 {o.over:g}" if o.over else "—",
            "—",
            f"小 {o.under:g}" if o.under else "—",
        ])
    body += grid + (C.table(["市场", m.home.name, "平", m.away.name], rows) if rows else "")
    body += _odds_trend(m)

    if not body.strip():
        return ""
    if o and o.bookmaker:
        body += f'<p class="panel-hint">来源：{C.esc(o.bookmaker)}</p>'
    return C.panel("赔率数据", body)


# 各联赛的分区线（名次 = 分界），形势分析用它给出「关键线还差几分」
_SITUATION_ZONES = {
    "英超": ((4, "欧冠线"), (17, "保级线")),
    "西甲": ((4, "欧冠线"), (17, "保级线")),
    "意甲": ((4, "欧冠线"), (17, "保级线")),
    "德甲": ((4, "欧冠线"), (15, "保级线")),
    "法甲": ((4, "欧冠线"), (15, "保级线")),
    "欧冠": ((8, "直接晋级线"), (24, "附加赛线")),
}


def _table_row(table: list[dict], name: str) -> dict | None:
    """在整榜里找该队（站点简称 ↔ 榜上全称双向包含）。"""
    for t in table:
        n = str(t.get("name") or "")
        if n and (n == name or name in n or n in name):
            return t
    return None


def _rank_range(table: list[dict], name: str, pts: int) -> tuple[int, int]:
    """新积分下的名次区间（最好~最差）。

    最好：其余队本轮不再得分，只按当前积分排；
    最差：当前积分落后 3 分以内的队本轮全赢，凭净胜球压过本队。
    """
    others = [t for t in table if t.get("name") != name]
    best = sum(1 for t in others if t["pts"] > pts) + 1
    worst = sum(1 for t in others if t["pts"] >= pts - 3) + 1
    return best, max(best, worst)


def _situation_panel(m: Match) -> str:
    """形势分析：三种结果各自把两队推到什么名次，一张满宽表说清。"""
    table = (m.extras or {}).get("table") or []
    if len(table) < 8:
        return ""
    h_row = _table_row(table, m.home.name)
    a_row = _table_row(table, m.away.name)
    if not h_row or not a_row:
        return ""

    def _head_cell(team, row: dict, side: str) -> str:
        cls = ' class="away"' if side == "away" else ""
        return (f'<th{cls}><span class="sth">'
                f'{C.crest_img(team, cls="crest", pre="../")}'
                f'<b>{C.esc(team.name)}</b>'
                f'<i>第 {row["rank"]} · {row["pts"]} 分</i></span></th>')

    def _cell(row: dict, add: int) -> str:
        pts = row["pts"] + add
        best, worst = _rank_range(table, row["name"], pts)
        tail = f'<i>最差 {worst}</i>' if best != worst else ""
        return f'<td><span class="sv"><b>{pts}</b> 分 · 第 {best} 名</span>{tail}</td>'

    rows = "".join(
        f'<tr><td class="rk {cls}">{lab}</td>{_cell(h_row, add)}{_cell(a_row, add)}</tr>'
        for lab, add, cls in (("赢", 3, "w"), ("平", 1, "d"), ("负", 0, "l"))
    )

    foot = []
    segs = []
    for pos, meaning in (_SITUATION_ZONES.get(m.competition) or ()):
        line = next((t for t in table if t["rank"] == pos), None)
        if line:
            segs.append(f'第 {pos} 名 {line["pts"]} 分（{meaning}）')
    if segs:
        foot.append(("关键线", " · ".join(segs)))
    near = [t for t in table
            if abs(t["rank"] - h_row["rank"]) <= 2
            and t.get("name") not in (h_row.get("name"), a_row.get("name"))]
    if near:
        foot.append(("名次相邻", "、".join(
            f'{t["name"]} 第 {t["rank"]} 名 {t["pts"]} 分' for t in near[:4])))
    tail_rows = "".join(
        f'<tr><th>{C.esc(k)}</th><td colspan="2">{C.esc(v)}</td></tr>' for k, v in foot
    )
    body = (
        '<div class="tw"><table class="sit-t">'
        f'<thead><tr><th class="rk">结果</th>{_head_cell(m.home, h_row, "home")}'
        f'{_head_cell(m.away, a_row, "away")}</tr></thead>'
        f'<tbody>{rows}</tbody>'
        + (f'<tfoot>{tail_rows}</tfoot>' if tail_rows else "")
        + "</table></div>"
    )
    return C.panel("形势分析", body)


def _standings_panel(m: Match) -> str:
    labels, hv, av = [], [], []
    for team, store in ((m.home, hv), (m.away, av)):
        store.append(f"第 {team.rank}" if team.rank else "")
        store.append(str(team.points) if team.points is not None else "")
        store.append(str(team.played) if team.played is not None else "")
        if team.win is not None:
            store.append(f"{team.win}-{team.draw}-{team.loss}")
        else:
            store.append("")
        store.append(f"{team.gf}-{team.ga}" if team.gf is not None and team.ga is not None else "")
    for k in range(5):
        if hv[k] and av[k]:
            labels.append(["名次", "积分", "场次", "战绩", "进/失"][k])
    # 简化：按固定指标名过滤空行
    order = ["名次", "积分", "场次", "战绩", "进/失"]
    rows = [[n, hv[i], av[i]] for i, n in enumerate(order) if hv[i] or av[i]]
    if not rows:
        return ""
    return C.panel(f"积分排名 · {m.competition}", C.table(["项目", m.home.name, m.away.name], rows, cls="duo"))


def _hc_seq(seq: str) -> str:
    """大号胜平负方块序列（近期战绩 / 历史交锋卡片内）。"""
    zh = {"W": ("胜", "w"), "D": ("平", "d"), "L": ("负", "l")}
    items = "".join(f'<span class="{zh[c][1]}">{zh[c][0]}</span>'
                    for c in str(seq or "") if c in zh)
    return f'<div class="hc-seq">{items}</div>' if items else ""


_FORM_TABS = (("近6场", "all6"), ("近12场", "all12"),
              ("同主客", "home6"), ("同赛事", "lg6"))
_MEET_TABS = _FORM_TABS


def _pair_rows(hb: dict, ab: dict, keys: tuple[tuple[str, str, str], ...]) -> str:
    """两队一组对比条：keys = (标签, 字段名, 单位)。"""
    rows = []
    for label, key, unit in keys:
        if hb.get(key) is None and ab.get(key) is None:
            continue
        rows.append(_hc_row(label, hb.get(key), ab.get(key), unit=unit))
    return _hc_block(rows)


_PAIR_KEYS = (("进球", "gf", ""), ("失球", "ga", ""),
              ("胜率", "win_rate", "%"), ("赢盘率", "plate_rate", "%"),
              ("大球率", "big_rate", "%"))


def _form_pair(m: Match, key: str) -> str:
    """一个样本口径下的两队近况：方块卡片 + 五项对比条。"""
    dish = (m.extras or {}).get("hc_dish") or {}
    hb = (dish.get("home") or {}).get(key) or {}
    ab = (dish.get("away") or {}).get(key) or {}
    if not hb and not ab:
        return ""
    cards = ""
    for team, b in ((m.home, hb), (m.away, ab)):
        if not b:
            continue
        cards += (
            '<div class="fc">'
            f'<h4>{C.esc(team.name)} 近{b.get("n")}场</h4>'
            f'{_hc_seq(str(b.get("seq") or ""))}'
            f'<p class="fc-sum"><span>{b.get("w")}胜{b.get("d")}平{b.get("l")}负</span>'
            f'<span>胜率 {_hc_fmt(b.get("win_rate"), "%")}</span></p>'
            '</div>'
        )
    return (f'<div class="hc-form2">{cards}</div>' if cards else "") \
        + _pair_rows(hb, ab, _PAIR_KEYS)


def _form_panel(m: Match) -> str:
    """近期战绩：红彩四档样本（近6/近12/同主客/同赛事）对比条 + 逐场明细折叠。

    明细来自站点已回填赛果（赛前视角可回溯），与红彩汇总互为印证。
    """
    tabs = [(lab, _form_pair(m, key)) for lab, key in _FORM_TABS]
    has_hc = any(html for _, html in tabs)
    body = _hc_teams(m) + _hc_tabs(f"fm-{m.match_id}", tabs) if has_hc else ""

    detail = ""
    for title, rows_src in ((f"{m.home.name} 近期", m.recent_home),
                            (f"{m.away.name} 近期", m.recent_away)):
        if not rows_src:
            continue
        dots = C.form_dots([r.outcome for r in rows_src])
        zh = {"W": "胜", "D": "平", "L": "负"}
        rows = [
            [r.date, r.competition, ("主" if r.venue == "home" else "客") + " " + r.opponent,
             r.score, r.half_ft or "—", zh.get(r.outcome, r.outcome)]
            for r in rows_src
        ]
        detail += (f"<h3>{C.esc(title)}</h3>{dots}"
                   + C.table(["日期", "赛事", "对手", "比分", "半全场", "结果"], rows,
                             cls="history-table"))
    if m.recent_home or m.recent_away:
        body += (f'<details class="fold"><summary>逐场明细</summary>{detail}</details>'
                 if has_hc else detail)

    if body:
        return C.panel("近期战绩", body)
    return C.panel(
        "近期战绩",
        '<p class="panel-empty">近期战绩数据源尚未接入，框架已预留，数据补齐后自动展示。</p>',
    )


def _meet_pair(m: Match, key: str) -> str:
    """一个交锋样本口径：胜平负大数字 + 方块序列 + 五项对比条。"""
    mt = (m.extras or {}).get("hc_meeting") or {}
    hb = (mt.get("home") or {}).get(key) or {}
    ab = (mt.get("away") or {}).get(key) or {}
    if not hb and not ab:
        return ""
    w, d, l = hb.get("w"), hb.get("d"), hb.get("l")
    wdl = ""
    if None not in (w, d, l):
        wdl = (
            '<div class="hc-wdl">'
            f'<div class="w"><b>{w}</b><span>{C.esc(m.home.name)}胜</span></div>'
            f'<div class="d"><b>{d}</b><span>平局</span></div>'
            f'<div class="l"><b>{l}</b><span>{C.esc(m.away.name)}胜</span></div>'
            '</div>'
        )
    seq = _hc_seq(str(hb.get("seq") or ""))
    return wdl + (f'<div class="hc-times">{seq}</div>' if seq else "") \
        + _pair_rows(hb, ab, _PAIR_KEYS)


def _h2h_panel(m: Match) -> str:
    """历史交锋：红彩统计（大数字 + 方块 + 对比条），逐场明细折叠在底部。"""
    tabs = [(lab, _meet_pair(m, key)) for lab, key in _MEET_TABS]
    has_hc = any(html for _, html in tabs)
    body = _hc_teams(m) + _hc_tabs(f"mt-{m.match_id}", tabs) if has_hc else ""
    if m.h2h:
        rows = [[h.date, h.competition, f"{h.home} {h.score} {h.away}"] for h in m.h2h]
        detail = C.table(["日期", "赛事", "对阵与比分"], rows, cls="history-table")
        body += (f'<details class="fold"><summary>逐场交锋</summary>{detail}</details>'
                 if has_hc else detail)
    if body:
        return C.panel("历史交锋", body)
    return C.panel(
        "历史交锋",
        '<p class="panel-empty">两队在本站赛果库暂无交手记录。</p>',
    )


def _injury_panel(m: Match) -> str:
    if not m.injuries:
        return C.panel(
            "伤停与缺阵",
            '<p class="panel-empty">本场暂无伤停与缺阵记录</p>',
        )
    rows = []
    for inj in m.injuries:
        who = m.home.name if inj.team == "home" else (m.away.name if inj.team == "away" else inj.team)
        status = {"out": "缺阵", "doubt": "存疑", "suspended": "停赛"}.get(inj.status, inj.status)
        rows.append([who, inj.player, inj.reason or "—", status])
    return C.panel("伤停与缺阵", C.table(["球队", "球员", "原因", "状态"], rows))


_SQ_POS = {"GK": "门将", "DF": "后卫", "MF": "中场", "FW": "前锋"}
_SQ_FAT = {"High": ("高", "tag-red"), "Medium": ("中", "tag-yellow"), "Low": ("低", "tag-green")}
_SQ_MIN_N = 8   # 源站每队至少 8 人才出块（澳超每队仅 1-5 人，整体省略，避免以偏概全）


def _sq_num(v, nd: int = 1) -> str:
    """评分展示：0-100 的量纲，无值出 —。不走 pct 类（那不是概率）。"""
    return f"{v:.{nd}f}" if isinstance(v, (int, float)) else "—"


def _sq_chg(v) -> str:
    """较上一计算周期的影响力变化：只出箭头与数值，无对比时 —。"""
    if not isinstance(v, (int, float)) or abs(v) < 0.05:
        return '<span class="sq-chg flat">—</span>'
    cls = "up" if v > 0 else "down"
    ico = "↑" if v > 0 else "↓"
    return f'<span class="sq-chg {cls}">{ico}{abs(v):.1f}</span>'


def _sq_rows(team: str, ts) -> list[list[str]]:
    rows = []
    for p in ts.top:
        pos = _SQ_POS.get((p.pos or "").upper(), p.pos or "—")
        fat_txt, fat_cls = _SQ_FAT.get(p.fatigue, ("—", ""))
        fat = f'<span class="tag {fat_cls}">{fat_txt}</span>' if fat_cls else "—"
        name = C.esc(p.name)
        if p.watch:
            lab = {"out": "缺阵", "doubt": "存疑", "suspended": "停赛"}.get(p.watch, p.watch)
            name += f' <span class="tag tag-red">{C.esc(lab)}</span>'
        if p.estimated:
            name += ' <span class="sq-est">估</span>'
        # 表格组件只对以 < 开头的单元格放行 HTML；球员名列必须以标签开头，
        # 否则名字后的状态/估算角标会被整格转义成字面文本。
        rows.append([
            C.esc(team), f'<span class="sq-who">{name}</span>', pos,
            f'<b>{_sq_num(p.gim)}</b> {_sq_chg(p.d_gim)}', _sq_num(p.oti), _sq_num(p.dii),
            _sq_num(p.form, 1), fat,
        ])
    return rows


def _squad_panel(m: Match) -> str:
    """球员情报：两队核心球员评分与体能状态。

    外部评分源，**只做参照，不参与本站概率计算**（RULES §3.4）。缺数据整块不出；
    单侧样本不足只省略该侧，不拿不完整名单冒充全队。
    """
    sq = m.squad
    if not sq:
        return ""
    home = sq.home if (sq.home and sq.home.n >= _SQ_MIN_N and sq.home.top) else None
    away = sq.away if (sq.away and sq.away.n >= _SQ_MIN_N and sq.away.top) else None
    if not home and not away:
        return ""

    parts: list[str] = []
    if home and away:
        def _cell(ts, key, nd=1):
            return _sq_num(getattr(ts, key), nd)

        sum_rows = [
            [C.esc(m.home.name), f"{home.n} 人", _cell(home, "core_avg"),
             _cell(home, "form_avg", 2), f"{home.high_fatigue} 人"],
            [C.esc(m.away.name), f"{away.n} 人", _cell(away, "core_avg"),
             _cell(away, "form_avg", 2), f"{away.high_fatigue} 人"],
        ]
        parts.append(
            '<div class="sq-sum">'
            + C.table(["球队", "库内球员", "核心影响力", "平均状态", "高强度负荷"],
                      sum_rows, cls="duo")
            + "</div>"
        )

    rows = []
    if home:
        rows += _sq_rows(m.home.name, home)
    if away:
        rows += _sq_rows(m.away.name, away)
    parts.append(C.table(
        ["球队", "球员", "位置", "影响力", "进攻威胁", "防守参与", "状态", "疲劳"],
        rows, cls="duo sq-table",
    ))
    cmp = f" · 对比 {C.esc(sq.prev[5:])}" if sq.prev else ""
    parts.append(
        f'<p class="panel-hint" style="margin-top:8px">评分源 {C.esc(sq.source)}'
        f'（{C.esc(sq.updated[:16])} 更新）{cmp} · 影响力/进攻威胁/防守参与为 0-100 综合分，'
        f"状态为近况 0-10 分。仅作参照，不参与本站结论计算。</p>"
    )
    return C.panel("球员情报", "".join(parts))


_MOOD_TAG = ("停赛：", "上阵成疑：", "成疑：", "受伤／缺阵：", "受伤：", "缺阵：")

def _mood_panel(m: Match) -> str:
    """赛前军情（extras.mood，7M 联赛稿，按场次编号匹配）。"""
    txt = str((m.extras or {}).get("mood") or "").strip()
    if not txt:
        return ""
    parts = []
    for ln in txt.split("\n"):
        ln = ln.strip()
        if not ln:
            continue
        cls = ' class="mk"' if any(t in ln[:10] for t in _MOOD_TAG) else ""
        parts.append(f"<p{cls}>{C.esc(ln)}</p>")
    return C.panel("赛前军情", '<div class="mood-text">' + "".join(parts) + "</div>")


def _pct_or(v) -> str:
    """百分比单元格：无值出 —，有值走 pct 类（红线口径）。"""
    return f'<span class="pct">{v}%</span>' if isinstance(v, (int, float)) else "—"


def _pct_flat(v) -> str:
    """正文夹句用的百分比：同走 pct 类，但不带胶囊内边距。"""
    return f'<span class="pct flat">{v}%</span>' if isinstance(v, (int, float)) else "—"


_WX_ICON = (("雷", "⛈"), ("雨", "🌧"), ("雪", "🌨"), ("雾", "🌫"),
            ("阴", "☁️"), ("云", "⛅"), ("晴", "☀️"))


def _wx_icon(name: str, w: dict | None = None) -> str:
    """有实况天气名就按名字取图标；只有预报时按降雨与风力反推，别再一律阴天。"""
    s = str(name or "")
    for k, ico in _WX_ICON:
        if k in s:
            return ico
    if w:
        pop, rain, wind = w.get("pop"), w.get("rain"), w.get("wind")
        if isinstance(pop, (int, float)) and pop >= 80:
            return "🌧"
        if isinstance(rain, (int, float)) and rain >= 3:
            return "🌧"
        if isinstance(wind, (int, float)) and wind >= 25:
            return "💨"
        if isinstance(pop, (int, float)) and pop >= 45:
            return "⛅"
        t = w.get("t_max")
        if isinstance(t, (int, float)) and t >= 26:
            return "☀️"
    return "⛅"


_WX_LV = {"ok": 0, "warn": 1, "watch": 1, "bad": 2}
_WX_TAGS = (("适宜", "ok"), ("需留意", "warn"), ("恶劣", "bad"))


def _wx_level(w: dict) -> int:
    """综合评级：上游 grade 只看降雨，低温高温与大风要一并算进去。"""
    lv = _WX_LV.get(str(w.get("grade") or ""), 0)
    t = w.get("t_actual")
    if t is None:
        t = w.get("t_max") if w.get("t_max") is not None else w.get("t_min")
    if isinstance(t, (int, float)):
        if t <= -3 or t >= 35:
            lv = max(lv, 2)
        elif t <= 6 or t >= 30:
            lv = max(lv, 1)
    pop, wind = w.get("pop"), w.get("wind")
    if isinstance(pop, (int, float)) and pop >= 85:
        lv = max(lv, 1)
    if isinstance(wind, (int, float)) and wind >= 28:
        lv = max(lv, 1)
    return lv


def _wx_say(w: dict) -> str:
    """一句话读天气：冷热、降雨、风力，只给判断不给数字堆叠。"""
    segs: list[str] = []
    t = w.get("t_actual")
    if t is None:
        lo, hi = w.get("t_min"), w.get("t_max")
        t = hi if hi is not None else lo
    if isinstance(t, (int, float)):
        if t <= 0:
            segs.append("严寒，体感与球速都受影响")
        elif t <= 8:
            segs.append("偏冷，热身与肌肉状态要留意")
        elif t >= 32:
            segs.append("高温，节奏与体能消耗偏大")
        elif t >= 27:
            segs.append("闷热，下半场体能下滑风险")
    pop = w.get("pop")
    if isinstance(pop, (int, float)):
        if pop >= 80:
            segs.append("大概率有雨，场地湿滑、球速变快")
        elif pop >= 50:
            segs.append("有降雨可能，注意地面配合")
    wind = w.get("wind")
    if isinstance(wind, (int, float)) and wind >= 20:
        segs.append("风力偏大，长传和高空球受影响")
    return "，".join(segs)


def _wx_fit(w: dict, home: str, away: str) -> str:
    """两队在该类天气下的适应度，只在双方样本都有时给结论。"""
    hb, ab = w.get("by_home") or {}, w.get("by_away") or {}
    hr, ar = hb.get("win_rate"), ab.get("win_rate")
    if not isinstance(hr, (int, float)) or not isinstance(ar, (int, float)):
        return ""
    if abs(hr - ar) < 20:
        return "两队在同类天气下表现接近"
    better, hi, lo = (home, hr, ar) if hr > ar else (away, ar, hr)
    return (f'{C.esc(better)}更适应这类天气'
            f'（{hi:g}% 对 {lo:g}%）')


def _weather_panel(m: Match) -> str:
    """比赛地天气卡片。气温/风速/湿度用红彩实况，降雨概率仍是 Open-Meteo 预报。"""
    w = (m.extras or {}).get("weather")
    if not w:
        return ""
    name = str(w.get("wx") or "").strip()
    t_act = w.get("t_actual")
    if t_act is not None:
        temp = f'{t_act}<small>℃</small>'
    elif w.get("t_min") is not None:
        temp = f'{w.get("t_min")}~{w.get("t_max")}<small>℃</small>'
    else:
        temp = "—"
    metas = []
    if w.get("humidity") is not None:
        metas.append(f'<span>湿度 <span class="pct flat">{w["humidity"]}%</span></span>')
    if w.get("wind") is not None:
        metas.append(f'<span>风速 {w["wind"]}km/h</span>')
    if w.get("pop") is not None:
        metas.append(f'<span>降雨概率 <span class="pct flat">{w["pop"]}%</span></span>')
    title = " · ".join(x for x in (name, str(w.get("city") or "")) if x)

    # 评估标签挂在首行右端，判断句与两队适应度另起一行两端对齐，避免右侧大片空档
    grade, gcls = _WX_TAGS[_wx_level(w)]
    say = _wx_say(w)

    fit = _wx_fit(w, m.home.name, m.away.name)
    teams = ""
    for team, key in ((m.home.name, "by_home"), (m.away.name, "by_away")):
        b = w.get(key) or {}
        if not b or b.get("win_rate") is None:
            continue
        teams += (
            f'<span><b>{C.esc(team)}</b> 近 {b.get("n")} 场 '
            f'{b.get("w")}胜{b.get("d")}平{b.get("l")}负 · 胜率 '
            f'<span class="pct flat">{b.get("win_rate")}%</span></span>'
        )

    row = (
        '<div class="wx-row">'
        f'<div class="wx-icon">{_wx_icon(name, w)}</div>'
        '<div class="wx-data">'
        '<div class="wx-top">'
        f'<span class="wx-temp">{temp}</span>'
        f'<span class="wx-meta">{"".join(metas)}</span>'
        '</div>'
        f'<div class="wx-name">{C.esc(title)}</div>'
        '</div>'
        f'<span class="wx-tag {gcls}">{grade}</span>'
        '</div>'
    )
    verdict = ""
    if say or fit:
        verdict = (
            '<div class="wx-verdict">'
            + (f'<span class="wx-say">{C.esc(say)}</span>' if say else "")
            + (f'<span class="wx-fit">{C.esc(fit)}</span>' if fit else "")
            + '</div>'
        )
    body = (
        '<div class="wx-card">'
        + row + verdict
        + (f'<div class="wx-teams">{teams}</div>' if teams else "")
        + "</div>"
    )
    return C.panel("比赛天气", body)


def _ref_num(v) -> str:
    if v is None:
        return "—"
    return f"{v:g}" if isinstance(v, (int, float)) else C.esc(str(v))


def _referee_panel(m: Match) -> str:
    """主裁判执法：红彩给场均口径（含执法两队分项），直播吧给生涯累计。"""
    r = (m.extras or {}).get("referee")
    if not r:
        return ""
    name = C.esc(str(r.get("ref") or ""))
    en = str(r.get("name_en") or "").strip()
    card = f'<div class="ref-card"><b>{name}</b>'
    if en:
        card += f'<span>{C.esc(en)}</span>'
    card += "</div>"

    if r.get("src") == "红彩" and r.get("n") is not None:
        rows = [[f'近 {r.get("n")} 场',
                 f'主队 {r.get("h")}胜{r.get("d")}平{r.get("a")}负',
                 _ref_num(r.get("yellow")), _ref_num(r.get("red")), _ref_num(r.get("pen"))]]
        for team, key in ((m.home.name, "by_home"), (m.away.name, "by_away")):
            b = r.get(key) or {}
            if not b:
                continue
            rows.append([f'{C.esc(team)} 近 {b.get("n")} 场',
                         f'{b.get("w")}胜{b.get("d")}平{b.get("l")}负',
                         _ref_num(b.get("yellow")), _ref_num(b.get("red")),
                         _ref_num(b.get("pen"))])
        return C.panel("裁判执法", card + C.table(
            ["", "战绩", "黄牌", "红牌", "点球"], rows, cls="ref-t"))

    # 回退：直播吧赛前文章（累计口径）
    who = name
    if r.get("nation") or r.get("age"):
        who += "（" + C.esc(str(r.get("nation") or ""))
        if r.get("age"):
            who += f'，{r["age"]}岁'
        who += "）"
    rows = [["主裁判", who]]
    if r.get("h") is not None:
        n = r.get("n") or 20
        rows.append([f"近{n}场执法", f'主队 {r["h"]}胜{r["d"]}平{r["a"]}负'])
        rows.append(["出示", f'黄牌 {r.get("yellow", "—")} · 红牌 {r.get("red", "—")} · '
                             f'点球 {r.get("pen", "—")}'])
    for team, key in ((m.home.name, "by_home"), (m.away.name, "by_away")):
        b = r.get(key) or {}
        if not b:
            continue
        rows.append([f"执法{C.esc(team)}",
                     f'{b.get("n")} 场 {b.get("w")}胜{b.get("d")}平{b.get("l")}负'])
    return C.panel("裁判执法", C.table(["项目", "内容"], rows))


def _charts_panel(m: Match) -> str:
    """进球威胁度走势。六维战力已并入「核心数据对比」面板，这里只留走势曲线。"""
    if not (m.momentum and len(m.momentum.labels) >= 2):
        return ""
    args = (m.momentum.labels, m.momentum.home, m.momentum.away,
            m.home.name, m.away.name)
    wide = C.momentum_svg(*args, w=1000, h=230)
    narrow = C.momentum_svg(*args, w=560, h=200)
    return C.panel(
        "进球威胁度走势",
        f'<div class="chart-wide">{wide}</div><div class="chart-narrow">{narrow}</div>',
    )


def _intel_panel(m: Match) -> str:
    """赛前情报速览：基本信息一屏看全（对齐对方单场页首个区块的框架）。"""
    zh_conf = {"high": "高", "medium": "中", "low": "低", "none": "冷门"}.get(
        m.confidence, "未评级"
    )
    dn = m.extras.get("data_n") or {}
    rows = [
        ["赛事", m.competition or "—", "编号", m.code or "—"],
        ["比赛日", m.day, "开球时间", m.kickoff or "待定"],
        ["AI 置信度", zh_conf, "冷启动", "是（不进精选）" if m.is_cold_start else "否"],
        ["结论模型", "量化推演引擎", "数据样本", f"主 {dn.get('home', '—')} 场 / 客 {dn.get('away', '—')} 场"],
    ]
    # 半场胜平负概率（2026-10-22 起引擎输出 htft_half）。
    # table 对以 '<' 开头的单元格按原文输出（内部值均为受控数字/固定枚举）。
    hh = m.extras.get("htft_half") or {}
    if hh:
        rows.append([
            "半场概率",
            f'<b>主</b> {_pct(hh.get("home"))} / <b>平</b> {_pct(hh.get("draw"))}'
            f' / <b>客</b> {_pct(hh.get("away"))}',
            "半全场首选",
            next((f'<b>{C.esc(f.label)}</b> <span class="pct">{C.pct(f.prob)}</span>'
                  for f in m.forecasts_of("htft") if f.rank == 1), "—"),
        ])
    return C.panel("赛前情报速览", C.table(["项目", "内容", "项目", "内容"], rows, cls="duo"))


def _pct(v) -> str:
    """百分数展示（情报表用）：引擎给 39.4（百分数），无值出 —。走 pct 类红线口径。"""
    return f'<span class="pct">{v:g}%</span>' if isinstance(v, (int, float)) else "—"


_HC_STATS_A = (
    ("possession", "控球率", "%"),
    ("attack_eff", "进球效率", ""),
    ("shots", "射门次数", ""),
    ("defense_eff", "防守效率", ""),
    ("shots_against", "被射门次数", ""),
)
_HC_STATS_B = (
    ("corners", "角球", ""),
    ("freekicks", "任意球", ""),
    ("fouls", "犯规", ""),
    ("red", "红牌", ""),
    ("yellow", "黄牌", ""),
)

# 六维风格：键 → 轴名，顺序即雷达顺时针方向（顶部进球 → 左上身价）
_HC_STYLE_AXES = (
    ("attack", "进球"),
    ("possession", "控球"),
    ("discipline", "纪律"),
    ("defense", "防守"),
    ("duel", "对抗"),
    ("value", "身价"),
)


def _hc_num(v) -> float | None:
    """对比条的量值：数值直取；「55/2」这类复合文本取斜杠前的部分定条长。"""
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).split("/")[0])
    except (TypeError, ValueError):
        return None


def _hc_fmt(v, unit: str = "", nd: int = 0) -> str:
    """对比条两侧的数值展示。百分比走 pct 类（红线口径），无值出 —。"""
    if v in (None, ""):
        return "—"
    if isinstance(v, str):
        return C.esc(v)
    if unit == "%":
        return f'<span class="pct flat">{v:g}%</span>'
    txt = f"{v:.{nd}f}" if nd else f"{v:g}"
    return txt


def _hc_row(label: str, hv, av, *, unit: str = "", nd: int = 0) -> str:
    """一行数据对比：主队值 + 主队条 + 指标名 + 客队条 + 客队值。

    条长按双方相对占比分配，两条各自从中轴向两侧生长；一方为 0 时对侧占满。
    """
    h, a = _hc_num(hv), _hc_num(av)
    # 净胜球可能为负：条长按绝对值分配，符号仍由数值本身表达
    ha, aa = abs(h or 0), abs(a or 0)
    tot = ha + aa
    hw = round(ha / tot * 100) if tot > 0 else 0
    aw = round(aa / tot * 100) if tot > 0 else 0
    if tot > 0 and hw == 0:
        hw = 1
    if tot > 0 and aw == 0:
        aw = 1
    return (
        '<div class="hc-row">'
        f'<b class="hv">{_hc_fmt(hv, unit, nd)}</b>'
        f'<div class="hc-track h"><i style="width:{hw}%"></i></div>'
        f'<span class="hl">{C.esc(label)}</span>'
        f'<div class="hc-track a"><i style="width:{aw}%"></i></div>'
        f'<b class="av">{_hc_fmt(av, unit, nd)}</b>'
        '</div>'
    )


def _hc_teams(m: Match) -> str:
    """对比面板顶部的两队（队徽 + 队名），左主右客。"""
    def _one(team, side: str) -> str:
        cls = "tm a" if side == "away" else "tm"
        return (f'<span class="{cls}">{C.crest_img(team, cls="crest", pre="../")}'
                f'<span class="n">{C.esc(team.name)}</span></span>')

    return f'<div class="hc-teams">{_one(m.home, "home")}{_one(m.away, "away")}</div>'


def _hc_tabs(uid: str, tabs: list[tuple[str, str]]) -> str:
    """纯 CSS 标签页（radio + label）。只有一个面板时直接平铺，不做壳。"""
    tabs = [(lab, html) for lab, html in tabs if html]
    if not tabs:
        return ""
    if len(tabs) == 1:
        return tabs[0][1]
    head, body = "", ""
    for i, (label, html) in enumerate(tabs, 1):
        tid = f"{uid}-{i}"
        checked = " checked" if i == 1 else ""
        head += (f'<input type="radio" name="{uid}" id="{tid}"{checked}>'
                 f'<label for="{tid}">{C.esc(label)}</label>')
        body += f'<div class="hc-pane p{i}">{html}</div>'
    return f'<div class="hc-tabs">{head}{body}</div>'


def _hc_block(rows: list[str]) -> str:
    return f'<div class="hc-cmp">{"".join(rows)}</div>' if rows else ""


def _style_radar(m: Match) -> str:
    """六维攻防风格雷达 + 综合总分对比（红彩 styleCompare 口径）。"""
    st = (m.extras or {}).get("hc_style") or {}
    hs, as_ = st.get("home") or {}, st.get("away") or {}
    if not hs or not as_:
        return ""
    axes = [zh for _, zh in _HC_STYLE_AXES]
    hv = [float(hs.get(k) or 0) for k, _ in _HC_STYLE_AXES]
    av = [float(as_.get(k) or 0) for k, _ in _HC_STYLE_AXES]
    if not any(hv) and not any(av):
        return ""
    radar = C.radar_svg(hv, av, axes, m.home.name, m.away.name, size=520)
    total = ""
    if hs.get("overall") is not None and as_.get("overall") is not None:
        total = _hc_block([_hc_row("综合总分", hs["overall"], as_["overall"], nd=2)])
    return (
        '<h3 class="blk-h">攻防风格对比</h3>'
        '<p class="panel-hint">基于本赛季同赛事场均数据</p>'
        f'<div class="radar-wrap">{radar}</div>{total}'
    )


def _compare_panel(m: Match) -> str:
    """核心数据对比：红彩 10 项赛季场均 + 六维攻防风格雷达与综合总分。"""
    ex = m.extras or {}
    st = ex.get("hc_stats") or {}
    hs, as_ = st.get("home") or {}, st.get("away") or {}
    rows_a, rows_b = [], []
    if hs or as_:
        for key, label, unit in _HC_STATS_A:
            if key in hs or key in as_:
                rows_a.append(_hc_row(label, hs.get(key), as_.get(key), unit=unit))
        for key, label, unit in _HC_STATS_B:
            if key in hs or key in as_:
                rows_b.append(_hc_row(label, hs.get(key), as_.get(key), unit=unit))
    # 红彩没覆盖的场次退回模型侧的自有指标，避免整块空白
    if not rows_a:
        lam_h, lam_a = ex.get("lam_home"), ex.get("lam_away")
        if lam_h is not None and lam_a is not None:
            rows_a.append(_hc_row("期望进球", lam_h, lam_a, nd=2))
    radar = _style_radar(m)
    body = ""
    if rows_a or rows_b:
        body = (_hc_teams(m)
                + '<p class="panel-hint">基于本赛季同赛事场均数据</p>'
                + _hc_block(rows_a)
                + (_hc_block(rows_b) if rows_b else ""))
    if not body and not radar:
        return C.panel(
            "核心数据对比",
            '<p class="panel-empty">两队量化指标数据源尚未接入，框架已预留。</p>',
        )
    return C.panel("核心数据对比", body + radar)


_RANGE_ROWS = (
    (("pts", "rank"), "积分/排名"),
    (("w",), "胜"),
    (("d",), "平"),
    (("l",), "负"),
    (("gf",), "进球"),
    (("ga",), "失球"),
    (("gd",), "净胜球"),
)


def _range_block(hb: dict, ab: dict) -> str:
    """一组积分口径的对比条（赛季总 / 同主客共用）。"""
    rows = []
    for keys, label in _RANGE_ROWS:
        hv, av = [], []
        for src, store in ((hb, hv), (ab, av)):
            if len(keys) == 2:
                store.append(f'{src.get(keys[0])}/{src.get(keys[1])}'
                             if src.get(keys[0]) is not None else "")
            else:
                store.append(src.get(keys[0]))
        if hv[0] in (None, "") and av[0] in (None, ""):
            continue
        rows.append(_hc_row(label, hv[0], av[0]))
    return _hc_block(rows)


def _rank_panel(m: Match) -> str:
    """积分排名：赛季总 / 同主客两套口径，对比条呈现。"""
    rg = (m.extras or {}).get("hc_range") or {}
    tabs = [
        ("总", _range_block(rg.get("home_total") or {}, rg.get("away_total") or {})),
        ("同主客", _range_block(rg.get("home") or {}, rg.get("away") or {})),
    ]
    head = _hc_teams(m)
    body = _hc_tabs(f"rk-{m.match_id}", tabs)
    if not body:
        return ""
    return C.panel("积分排名", head + body)


# 近6 / 近12 / 同主客(主场近6) / 同赛事(同联赛6) 已在「近期战绩」四档里给过，
# 这里只留它没有的口径，同一组数字不在两处出现
_DISH_ROWS = (
    ("home12", "主场近12"),
    ("lg12", "同联赛12"),
    ("home_lg6", "主+联赛6"),
    ("home_lg12", "主+联赛12"),
)


def _seq_html(seq: str) -> str:
    """胜平负序列 → 小方块，红彩给的是 [3,1,0] 转出来的 WDL。"""
    zh = {"W": ("胜", "w"), "D": ("平", "d"), "L": ("负", "l")}
    items = "".join(f'<span class="sq {zh[c][1]}">{zh[c][0]}</span>'
                    for c in str(seq or "") if c in zh)
    return f'<span class="seq">{items}</span>' if items else ""


def _dish_sig(b: dict) -> tuple:
    """一组盘路数据的指纹（胜平负 + 进失），用于跨口径去重。"""
    if not b:
        return ()
    vals = tuple(b.get(k) for k in ("w", "d", "l", "gf", "ga"))
    return vals if any(v is not None for v in vals) else ()


def _dish_panel(m: Match) -> str:
    """盘路走势：近期战绩未覆盖的样本口径，各自的胜平负 / 赢盘率 / 进失 / 走势。"""
    dish = (m.extras or {}).get("hc_dish") or {}
    if not dish:
        return ""
    # 近期战绩四档已展示过的数字，这里按数值指纹跳过，避免同一组数据出现在两处
    shown = set()
    for side in ("home", "away"):
        d = dish.get(side) or {}
        for _, key in _FORM_TABS:
            sig = _dish_sig(d.get(key) or {})
            if sig:
                shown.add(sig)
    bodies = ""
    for side in ("home", "away"):
        d = dish.get(side) or {}
        if not d:
            continue
        team = m.home.name if side == "home" else m.away.name
        rows = ""
        for key, label in _DISH_ROWS:
            b = d.get(key)
            sig = _dish_sig(b or {})
            if not sig or sig in shown:
                continue
            shown.add(sig)
            rows += (
                f'<tr><td>{C.esc(label)}</td>'
                f'<td>{b.get("w")}胜{b.get("d")}平{b.get("l")}负</td>'
                f'<td>{_pct_or(b.get("win_rate"))}</td>'
                f'<td>{_pct_or(b.get("plate_rate"))}</td>'
                f'<td>{b.get("gf")}:{b.get("ga")}</td>'
                f'<td class="seq-cell">{_seq_html(str(b.get("seq") or ""))}</td></tr>'
            )
        if not rows:
            continue
        bodies += (f'<tbody><tr class="dish-hd"><td colspan="6">{C.esc(team)}</td></tr>'
                   f'{rows}</tbody>')
    if not bodies:
        return ""
    head = ('<thead><tr><th>样本</th><th>胜平负</th><th>胜率</th><th>赢盘率</th>'
            '<th>进/失</th><th>走势</th></tr></thead>')
    return C.panel(
        "盘路走势",
        f'<div class="tw"><table class="dish-t">{head}{bodies}</table></div>',
    )


def _bars_block(m: Match, kind: str) -> str:
    """一个时段口径的双柱图（kind=scored 进球 / conceded 丢球），橙=主队 蓝=客队。"""
    gd = (m.extras or {}).get("hc_goal_dist") or {}
    hs = (gd.get("home") or {}).get(kind) or []
    as_ = (gd.get("away") or {}).get(kind) or []
    if not hs and not as_:
        return ""
    n = max(len(hs), len(as_))
    bands: list[tuple[str, object, object]] = []
    vals: list[float] = []
    for i in range(n):
        a = hs[i] if i < len(hs) else {}
        b = as_[i] if i < len(as_) else {}
        lo = a.get("from", b.get("from", ""))
        hi = a.get("to", b.get("to", ""))
        bands.append((f"{lo}-{hi}", a.get("pct"), b.get("pct")))
        for v in (a.get("pct"), b.get("pct")):
            if isinstance(v, (int, float)):
                vals.append(float(v))
    maxv = max(vals) if vals else 0.0

    def bar(cls: str, v) -> str:
        p = float(v) if isinstance(v, (int, float)) else 0.0
        # 满分只到 86%，给柱顶的数值标签留出空间
        h = round(p / maxv * 86, 1) if maxv > 0 else 0.0
        text = f'<span class="pct flat">{p:g}%</span>' if isinstance(v, (int, float)) else "—"
        return (f'<div class="bh {cls}" style="--h:{h}%">'
                f'<b>{text}</b><i style="height:{h}%"></i></div>')

    cells = "".join(f'<div class="bg">{bar("h", hp)}{bar("a", ap)}</div>'
                    for _, hp, ap in bands)
    axis = "".join(f"<span>{C.esc(label)}′</span>" for label, _, _ in bands)
    legend = (f'<p class="panel-hint"><span class="lg h"></span>{C.esc(m.home.name)}'
              f'<span class="lg a"></span>{C.esc(m.away.name)}</p>')
    return legend + f'<div class="hc-bars">{cells}</div><div class="hc-axis">{axis}</div>'


def _goaldist_panel(m: Match) -> str:
    """进球时段分布（红彩各 15 分钟段占比，双柱并排）。"""
    body = _bars_block(m, "scored")
    return C.panel("进球时段分布", body) if body else ""


def _conceded_panel(m: Match) -> str:
    """丢球时段分布（与进球时段同结构，对照看防线在哪个时段松）。"""
    body = _bars_block(m, "conceded")
    return C.panel("丢球时段分布", body) if body else ""


def _analyse_panel(m: Match) -> str:
    """红彩赛前分析短句（每队 2-8 条，已去 HTML 标签）。"""
    ana = (m.extras or {}).get("hc_analyse") or {}
    if not ana:
        return ""
    blocks = ""
    for key, team in (("home", m.home.name), ("guest", m.away.name)):
        rows = ana.get(key) or []
        if not rows:
            continue
        lis = "".join(f"<li>{C.esc(x)}</li>" for x in rows)
        blocks += f'<div><h3>{C.esc(team)}</h3><ul>{lis}</ul></div>'
    if not blocks:
        return ""
    return C.panel("赛前分析", f'<div class="ana-grid">{blocks}</div>')


_DIRS = (("home", "主胜"), ("draw", "平局"), ("away", "客胜"))
_GOAL_BANDS = ((0, 1, "0–1 球"), (2, 3, "2–3 球"), (4, 99, "4 球以上"))


def _goal_bands(lh: float, la: float) -> list[tuple[str, float]]:
    """双方预期进球 → 总进球三档概率（两个独立计数的联合分布）。"""

    def pmf(k: int, mu: float) -> float:
        return math.exp(-mu) * mu ** k / math.factorial(k)

    joint: dict[int, float] = {}
    for i in range(13):
        for j in range(13):
            joint[i + j] = joint.get(i + j, 0.0) + pmf(i, lh) * pmf(j, la)
    tot = sum(joint.values()) or 1.0
    return [
        (lab, sum(v for k, v in joint.items() if lo <= k <= hi) / tot)
        for lo, hi, lab in _GOAL_BANDS
    ]


def _mkt_probs(m: Match) -> dict[str, float] | None:
    """市场三方向概率：与赔率面板同取值顺序（时序最新 → 全玩法胜平负 → 基础赔率）。"""
    cand: list[dict] = []
    tk = (m.extras or {}).get("odds_ticks") or []
    if tk:
        cand.append(tk[-1] or {})
    of = (m.extras or {}).get("odds_full") or {}
    if of.get("spf"):
        cand.append(of["spf"] or {})
    if m.odds:
        cand.append({"胜": m.odds.home, "平": m.odds.draw, "负": m.odds.away})
    for c in cand:
        h, d, a = _tick_num(c.get("胜")), _tick_num(c.get("平")), _tick_num(c.get("负"))
        if h and d and a:
            tot = 1 / h + 1 / d + 1 / a
            return {"home": 1 / h / tot, "draw": 1 / d / tot, "away": 1 / a / tot}
    return None


def _model_panel(m: Match) -> str:
    """模型视角：总进球分布 / 三方向最可能比分 / 模型与市场 / 冷门评估。

    四块都取自模型快照 extras，缺哪块就不画哪块：
      lam_*      双方预期进球 → 主客占比与三档总进球概率
      quad_top   三个方向各自最可能比分
      prob_*     模型 1X2 概率，与去水后的市场概率并排看分歧
      upset_*    市场首选翻车概率与档位
    """
    ex = m.extras or {}
    lh, la, lt = ex.get("lam_home"), ex.get("lam_away"), ex.get("lam_total")
    probs = {
        "home": ex.get("prob_home"),
        "draw": ex.get("prob_draw"),
        "away": ex.get("prob_away"),
    }
    quad = ex.get("quad_top") or {}
    parts: list[str] = []

    # ① 预期进球：合计数 + 主客占比条 + 三档总进球概率
    if isinstance(lh, (int, float)) and isinstance(la, (int, float)) and (lh + la) > 0:
        total = lt if isinstance(lt, (int, float)) else lh + la
        share = lh / (lh + la)
        bands = "".join(
            f'<div class="mv-band"><span class="mv-band-l">{lab}</span>'
            f'<span class="bar-track"><i class="bar-fill b{i}"'
            f' style="width:{v * 100:.1f}%"></i></span>'
            f'<b class="pct">{v * 100:.1f}%</b></div>'
            for i, (lab, v) in enumerate(_goal_bands(float(lh), float(la)))
        )
        parts.append(
            '<div class="mv-block">'
            f'<div class="mv-goal"><span class="mv-goal-n">{total:.2f}<em>球</em></span>'
            '<span class="mv-goal-l">预期总进球</span></div>'
            '<div class="mv-stack">'
            f'<i class="h" style="width:{share * 100:.1f}%"></i>'
            f'<i class="a" style="width:{(1 - share) * 100:.1f}%"></i></div>'
            '<div class="mv-legend">'
            f'<span><b>{C.esc(m.home.name)}</b> {lh:.2f}</span>'
            f'<span><b>{C.esc(m.away.name)}</b> {la:.2f}</span></div>'
            f'<div class="mv-bands">{bands}</div></div>'
        )

    # ② 三方向最可能比分：每格 = 方向 / 比分 / 该比分概率 / 该方向概率
    cells = []
    for key, lab in _DIRS:
        q = quad.get(key)
        if not (isinstance(q, dict) and q.get("score")):
            continue
        dp = probs.get(key)
        sub = (
            f'<span class="mv-q-d">方向 <span class="pct">{dp:.1f}%</span></span>'
            if isinstance(dp, (int, float)) else ""
        )
        cells.append(
            f'<div class="mv-q"><span class="mv-q-lab">{lab}</span>'
            f'<span class="mv-q-score">{C.esc(str(q["score"]).replace(":", "-"))}</span>'
            f'<span class="pct mv-q-p">{q.get("prob", 0):g}%</span>{sub}</div>'
        )
    if cells:
        parts.append(
            '<div class="mv-block"><h4>三方向最可能比分</h4>'
            f'<div class="mv-quad">{"".join(cells)}</div></div>'
        )

    # ③ 模型与市场：同一方向的模型概率与去水市场概率并排
    imp = _mkt_probs(m)
    if imp and all(isinstance(probs[k], (int, float)) for k, _ in _DIRS):
        cells = "".join(
            f'<div class="mv-mk-c"><span class="mv-mk-l">{lab}</span>'
            f'<span class="mv-mk-v"><span class="pct">{probs[key]:.1f}%</span>'
            f'<em>模型</em></span>'
            f'<span class="mv-mk-v m"><span class="pct">{imp[key] * 100:.1f}%</span>'
            f'<em>市场</em></span></div>'
            for key, lab in _DIRS
        )
        parts.append(
            '<div class="mv-block"><h4>模型与市场</h4>'
            f'<div class="mv-mkt3">{cells}</div></div>'
        )

    # ④ 冷门评估：三档刻度 + 指针（<40 低 / 40–52 中 / ≥52 高，轴到 80%）
    if isinstance(ex.get("upset_prob"), (int, float)):
        up = float(ex["upset_prob"])
        pos = min(max(up / 80 * 100, 0.0), 100.0)
        parts.append(
            '<div class="mv-block">'
            '<div class="mv-up-h"><span class="mv-t">冷门评估</span>'
            f'<b>{C.esc(str(ex.get("upset_level") or "—"))}</b>'
            f'<span class="pct">{up:g}%</span></div>'
            '<div class="mv-scale"><i class="s1"></i><i class="s2"></i><i class="s3"></i>'
            f'<em style="width:2px;left:{pos:.1f}%"></em></div>'
            '<div class="mv-scale-l"><span>低</span><span>中</span><span>高</span></div>'
            "</div>"
        )

    body = "".join(parts) or (
        '<p class="panel-empty">模型过程数据尚未接入，框架已预留。</p>'
    )
    return C.panel("模型视角", body)


def _main_pick_block(m: Match) -> str:
    """一句话主推 + 方向评级。缺 main_pick 就整块不出现。"""
    if not m.main_pick:
        return ""
    tag = ""
    top = (m.forecasts_of("direction") or [None])[0]
    if top:
        tag = C.grade_tag(top.prob, m.confidence)
    return C.main_pick_bar(
        m.main_pick,
        tag=tag,
        hit=m.result.direction_hit if (m.result and m.result.full_score) else None,
    )


def _handicap_panel(m: Match) -> str:
    """让球结论。盘口来自 Odds，结论来自 Handicap，两者缺一就不画。"""
    h = m.handicap
    if not h or not h.pick:
        return ""
    spread = ""
    if h.spread is not None:
        # 负值 = 主队让球，正值 = 主队受让；直接写「主让 1」比「-1」好读
        if h.spread < 0:
            spread = f"主让 {abs(h.spread):g}"
        elif h.spread > 0:
            spread = f"主受 {h.spread:g}"
        else:
            spread = "平手"
    cells = []
    if spread:
        cells.append(("让球", spread))
    cells.append(("结论", f'<strong>{C.esc(h.pick)}</strong>'))
    if h.prob is not None:
        cells.append(("概率", C.prob_tag(h.prob)))
        cells.append(("评级", C.grade_tag(h.prob, m.confidence)))
    if h.hit is not None:
        cells.append(("结果", "命中" if h.hit else "未中"))
    body = C.insight_grid(cells)
    return C.panel("让球", body) if body else ""


def _risk_panel(m: Match) -> str:
    r = m.risk
    if not r:
        return ""
    body = C.risk_note(r.level, r.note, r.factors)
    if not body:
        return ""
    if r.hit is not None:
        body += f'<p class="panel-hint">赛后核验：{"风险已兑现" if r.hit else "风险未兑现"}</p>'
    return C.panel("风险", body)


def _reference_panel(m: Match) -> str:
    """第三方对照。只在有对照数据时出现，且强制署名。"""
    ref = m.reference
    if not ref or not ref.items:
        return ""
    ours = {k: (v.label if v else "—") for k, v in m.headline.items()}
    titles = {"direction": "方向", "score": "比分", "goals": "进球", "htft": "半全场"}
    rows = []
    for it in ref.items:
        if it.kind not in titles:
            continue
        mark = ""
        if it.hit is True:
            mark = ' <span class="hit hit-y">中</span>'
        elif it.hit is False:
            mark = ' <span class="hit hit-n">未中</span>'
        rows.append((titles[it.kind], C.esc(ours.get(it.kind, "—")), C.esc(it.label) + mark))
    body = C.reference_table(rows, source=ref.source, url=ref.url, license_=ref.license)
    return C.panel("外部对照", body) if body else ""


def _settled_panel(m: Match) -> str:
    """赛后结算：只出赛果与四维命中，无指纹、无生成时间、无来源链接。

    「留档核验」整块已移除 —— 哈希指纹属于内部自证，不进公开页。
    """
    r = m.result
    if not (r and r.full_score):
        return ""
    marks = []
    for lab, v in (("方向", r.direction_hit), ("比分", r.score_hit),
                   ("进球", r.goals_hit), ("半全", r.htft_hit)):
        if v is None:
            continue
        cls = "hit-y" if v else "hit-n"
        marks.append(f'{C.esc(lab)} <span class="hit {cls}">{"中" if v else "未中"}</span>')
    body = (
        f'<p class="sub" style="margin:0">半场 {C.esc(r.half_score or "—")} · 全场 '
        f"<strong>{C.esc(r.full_score)}</strong></p>"
        + (f'<p class="panel-hint" style="margin-top:6px">{"　".join(marks)}</p>' if marks else "")
    )
    return C.panel("赛后结算", body)



def render_match(cfg: Config, m: Match) -> str:
    base = cfg.base_url.rstrip("/")
    url = f"{base}/matches/{m.match_id}.html"
    title = f"{m.home.name} vs {m.away.name} · {m.competition}"
    desc = f"{m.day} {m.competition} {m.code} {m.home.name} 对阵 {m.away.name} 的赛前量化数据与结论"
    settled = None
    if m.result and m.result.full_score:
        settled = m.result.direction_hit

    head_bits = [m.round or "", m.kickoff, m.venue]
    meta = " · ".join([b for b in head_bits if b])
    cold = ' <span class="mini">样本不足 · 不进精选</span>' if m.is_cold_start else ""
    sample = ' <span class="mini">示例数据</span>' if m.extras.get("sample") else ""

    teams_row = f'<h1 class="sr-only">{C.esc(m.home.name)} vs {C.esc(m.away.name)}</h1>' + _mc_teams(m, pre="../")
    header = _mc_header(m, pre="../")
    picks = _picks(m)
    body_parts = [
        '<div class="card card-match">',
        header,
        '<div class="mc-body">',
        teams_row,
        f'<p class="sub" style="text-align:center;margin:0">{C.esc(meta)}{cold}{sample}</p>',
        "</div>",
        "</div>",
        # 顺序按「读者决策链」排：结论 → 基本面 → 人员 → 市场与推演 → 环境。
        # 同一层内由整体到局部；数据表在前、文字情报在后，避免长文打断表格节奏。
        # L1 结论层：看好谁、有多确定
        _main_pick_block(m),    # 一句话主推（有才出现）
        C.panel("综合赛果推演", picks) if picks else "",   # 四宫格：方向/比分/进球/半全场
        _intel_panel(m),        # 赛前情报速览：基本信息一屏
        # L2 基本面层：谁强谁弱
        _compare_panel(m),      # 核心数据对比（10 项场均 + 六维攻防风格雷达 + 综合总分）
        _rank_panel(m),         # 积分排名（赛季总 / 同主客）
        _h2h_panel(m),          # 历史交锋（胜平负大数字 + 方块 + 对比条）
        _form_panel(m),         # 近期战绩（四档样本对比条）
        _goaldist_panel(m),     # 进球时段分布（双柱，紧贴战绩）
        _conceded_panel(m),     # 丢球时段分布（双柱）
        # L3 人员层：谁能上、状态如何
        _injury_panel(m),       # 伤停与缺阵
        _squad_panel(m),        # 球员情报（核心球员评分 + 负荷）
        _mood_panel(m),         # 赛前军情（7M 联赛稿）
        _analyse_panel(m),      # 赛前分析（红彩短句）
        # L4 市场与推演层：市场怎么给、模型怎么算
        _odds_panel(m),         # 赔率数据（含时序变化）
        _handicap_panel(m),     # 让步可信度分析
        _dish_panel(m),         # 盘路走势（红彩 8 维度含赢盘率）
        _model_panel(m),        # 模型视角
        _charts_panel(m),       # 进球威胁度走势（有数据才画）
        _situation_panel(m),    # 形势分析（有整榜才画）
        # L5 环境与附注层
        _weather_panel(m),      # 比赛地天气
        _referee_panel(m),      # 主裁判执法数据
        _reference_panel(m),    # 外部对照（有才出现）
        _settled_panel(m),      # 赛后结算（有赛果才出现）
    ]

    jsonld = _match_jsonld(cfg, m, url, title, desc)
    return L.page(
        cfg,
        title=title,
        description=desc,
        body="".join(body_parts),
        canonical=url,
        jsonld=jsonld,
        depth=1,
    )


# ---------------------------------------------------------------- 今日列表


# ---------------------------------------------------------------- 与 qiuxiaoce 同构的卡片部件


def _mc_header(m: Match, pre: str = "") -> str:
    """日期 / 联赛 / 编号 / 时间 + AI置信度 + 命中印章。

    结构与 class 名对齐 qiuxiaoce 的 `.mc-header`。印章只在有赛果时出现。
    """
    date_txt = ""
    if len(m.match_id) >= 10:
        date_txt = f"{int(m.match_id[5:7])}/{int(m.match_id[8:10])}"
    time_txt = m.kickoff[-5:] if m.kickoff else ""
    conf_cls = {"high": "high", "medium": "medium", "low": "low", "none": "cold"}.get(
        m.confidence, ""
    )
    conf_lab = {"high": "高", "medium": "中", "low": "低", "none": "冷门"}.get(
        m.confidence, "未评级"
    )
    # 已结算即出章：命中红✔，未中黑✘
    stamp = ""
    if m.result and m.result.direction_hit is not None:
        stamp = (
            '<div class="prediction-stamp stamp-red">✔</div>'
            if m.result.direction_hit
            else '<div class="prediction-stamp stamp-black">✘</div>'
        )
    return (
        '<div class="mc-header"><div class="mc-meta">'
        f'<span class="date">{C.esc(date_txt)}</span>'
        f'<span class="league lg-link" data-goto="{pre}{_lg_href(m.competition)}">{C.esc(m.competition)}</span>'
        + (f'<span class="num">{C.esc(m.code)}</span>' if m.code else "")
        + f'<span class="time">{C.esc(time_txt)}</span>'
        '</div><div class="mc-status">'
        f'<span class="mc-conf {conf_cls}">AI置信度:{C.esc(conf_lab)}</span>{stamp}'
        "</div></div>"
    )


def _lg_href(league: str) -> str:
    """联赛名 → 联赛页相对路径（站点根下 leagues/{联赛名}.html，页深前缀由调用方补）。"""
    return f"leagues/{C.esc(league)}.html"


def _tm_href(team: str) -> str:
    """球队名 → 球队页相对路径（站点根下 teams/{队名}.html）。"""
    return f"teams/{C.esc(team)}.html"


def _mc_teams(m: Match, pre: str = "") -> str:
    """队徽 + 大比分（括号内半场）。未结算时中间出 VS。

    口径对齐球小策：未开赛上部为 VS、下部半场比分位出 (0-0) 占位；
    已完赛上部全场比分、下部半场比分（无半场比分时下部留空）。
    球队名/队徽用 span+data-goto 而非 <a>：列表卡片与单场页头部都处在
    整卡 <a> 内部，HTML 不允许嵌套 a，点击跳转交给全局事件委托。
    """
    if m.result and m.result.full_score:
        top = f'<div class="main">{C.esc(m.result.full_score)}</div>'
        sub = C.esc(m.result.half_score) if m.result.half_score else ""
    else:
        top = '<div class="vs">VS</div>'
        sub = "0-0"
    score = (
        f'<div class="mc-score">{top}'
        + (f'<div class="sub">({sub})</div>' if sub else "")
        + "</div>"
    )

    def cell(t) -> str:
        return (
            f'<div class="mc-team"><span class="team-link" data-goto="{pre}{_tm_href(t.name)}">'
            f'{C.crest_img(t, pre=pre)}<span>{C.esc(t.name)}</span></span></div>'
        )

    return f'<div class="mc-teams">{cell(m.home)}{score}{cell(m.away)}</div>'


def _actual_htft(m: Match) -> str:
    """已结算场次的「实际半全场」（halfScore+fullScore 推导，主/客/平组合）。

    这是实际赛果而非预测——历史日期没有 htft 预测存档，但赛果本身含半场比分，
    可如实展示。未结算 / 缺半场比分 / 比分格式异常时返回空。
    """
    r = m.result
    if not r or not r.half_score or not r.full_score:
        return ""
    try:
        fh, fa = (int(x) for x in r.half_score.split("-"))
        sh, sa = (int(x) for x in r.full_score.split("-"))
    except ValueError:
        return ""

    def side(a: int, b: int) -> str:
        return "主" if a > b else ("客" if a < b else "平")

    return f"{side(fh, fa)}/{side(sh, sa)}"


def _mc_tags(m: Match) -> str:
    """四个维度的图标标签，命中项加 .hit 提亮。

    图标统一走 L.ICON_* 单色线性 SVG（全站一套风格，不用彩色 emoji）。
    已结算的场次在每个标签上直接应用赛果状态：命中 ✓（红提亮）/ 未中 ✗（灰），
    让历史日期页一眼看出每条结论的命中情况。
    半全场：有预测结论就展示预测并标 ✓/✗；无预测但已结算的（历史日期），
    展示「实际半全场」——由半场/全场比分推导，属赛果数据而非预测。
    """
    icon = {
        "direction": L.ICON_TARGET, "score": L.ICON_HASH,
        "goals": L.ICON_SPORTS, "htft": L.ICON_TREND,
    }
    zh = {"direction": "方向", "score": "比分", "goals": "进球", "htft": "半全场"}
    hit_of = {
        "direction": "direction_hit", "score": "score_hit",
        "goals": "goals_hit", "htft": "htft_hit",
    }
    tags = []
    for kind in ("direction", "score", "goals", "htft"):
        f = m.headline.get(kind)
        if not f:
            if kind == "htft":
                act = _actual_htft(m)
                if act:
                    tags.append(
                        f'<div class="mc-tag" title="半全场（实际赛果）">'
                        f"{L.ICON_TREND} {act}</div>"
                    )
                else:
                    tags.append(
                        '<div class="mc-tag mc-tag-ph">半全场 · 待接入</div>'
                    )
            continue
        cls = ""
        state = ""
        if m.result:
            hv = getattr(m.result, hit_of[kind], None)
            if hv is True:
                cls = " hit"
                state = f'<span class="tag-state">{L.ICON_CHECK}</span>'
            elif hv is False:
                cls = " miss"
                state = f'<span class="tag-state">{L.ICON_CROSS}</span>'
        tags.append(
            f'<div class="mc-tag{cls}" title="{zh[kind]}">'
            f"{icon[kind]} {C.esc(f.label)}{state}</div>"
        )
    return f'<div class="mc-tags">{"".join(tags)}</div>' if tags else ""


def _card(cfg: Config, m: Match, *, pre: str = "", lg: str = "") -> str:
    """首页/归档列表卡片。整卡结构与 class 名对齐 qiuxiaoce 的 `.match-card`。

    `lg` 是该场联赛在当日联赛列表里的下标，写进 `data-lg` 供纯 CSS 筛选使用。
    """
    url = f"{pre}matches/{m.match_id}.html"
    footer = ""
    if m.main_pick:
        footer = (
            '<div class="mc-footer"><div class="mc-footer-left">'
            '<span class="mc-highlight-icon">💡</span>'
            f'<span class="mc-highlight-text">{C.esc(m.main_pick)}</span>'
            "</div></div>"
        )
    attr = f' data-lg="{C.esc(lg)}"' if lg else ""
    return (
        f'<a class="match-card" href="{url}"{attr}>'
        + _mc_header(m, pre=pre)
        + '<div class="mc-body">'
        + _mc_teams(m, pre=pre)
        + _mc_tags(m)
        + footer
        + "</div></a>"
    )


def compute_ranking(days: list[Day], top: int = 10) -> list[tuple[str, int, int]]:
    """赛事命中榜：按联赛统计方向命中率，返回 [(联赛, 命中, 已结算场次), ...]。

    口径固定为「方向命中」，与卡片上的 🧭 标签同一来源；只统计已结算场次，
    未回填赛果的联赛不进榜（不做 0/0 的假 100%）。样本量并列时场次多的在前，
    避免 1 场 1 中压过 20 场 15 中。
    """
    agg: dict[str, list[int]] = {}
    for d in days:
        for m in d.matches:
            if not m.competition or not m.result:
                continue
            if m.result.direction_hit is None:
                continue
            row = agg.setdefault(m.competition, [0, 0])
            row[1] += 1
            if m.result.direction_hit:
                row[0] += 1
    rows = [(lg, hit, n) for lg, (hit, n) in agg.items() if n > 0]
    rows.sort(key=lambda x: (-(x[1] / x[2]), -x[2], x[0]))
    return rows[:top]


def compute_team_ranking(days: list[Day], top: int = 10) -> list[tuple[str, int, int]]:
    """球队命中榜：口径同上，但按参赛队聚合（一支队的已结算场次）。"""
    agg: dict[str, list[int]] = {}
    for d in days:
        for m in d.matches:
            if not m.result or m.result.direction_hit is None:
                continue
            for t in (m.home.name, m.away.name):
                row = agg.setdefault(t, [0, 0])
                row[1] += 1
                if m.result.direction_hit:
                    row[0] += 1
    rows = [(t, hit, n) for t, (hit, n) in agg.items() if n > 0]
    rows.sort(key=lambda x: (-(x[1] / x[2]), -x[2], x[0]))
    return rows[:top]


def _ranking_card(rows: list[tuple[str, int, int]], pre: str = "",
                  kind: str = "league") -> str:
    """右侧 Top10 卡：结构逐字对齐 qiuxiaoce 的 .ranking-card。

    rank-index + rank-logo（徽章，缺映射退化首字圆）+ rank-name +
    rank-bar（绿色进度条）+ rank-acc（1 位小数）。kind: league=🏆赛事 / team=🛡️球队。
    """
    if not rows:
        inner = '<div class="ranking-empty">暂无可统计的已结算赛事。</div>'
    else:
        items = []
        for i, (name, hit, n) in enumerate(rows, 1):
            acc = hit / n * 100
            if kind == "team":
                logo, alt = logos.crest_url(name), "队徽"
                goto = f"{pre}teams/{C.esc(name)}.html"
            else:
                logo, alt = logos.league_crest_url(name), "徽章"
                goto = f"{pre}leagues/{C.esc(name)}.html"
            img = (
                f'<img src="{pre}{C.esc(logo)}" class="rank-logo" alt="{C.esc(name)}{alt}" loading="lazy">'
                if logo
                else f'<span class="rank-logo rank-logo-ph" aria-hidden="true">{C.esc(name[:1])}</span>'
            )
            items.append(
                f'<a class="ranking-item" href="{goto}">'
                f'<div class="rank-index">{i}</div>{img}'
                f'<span class="rank-name lg-link">{C.esc(name)}</span>'
                f'<div class="rank-bar-wrap">'
                f'<div class="rank-bar" style="width:{acc:.1f}%"></div></div>'
                f'<span class="rank-acc pct">{acc:.1f}%</span></a>'
            )
        inner = f'<div class="ranking-list">{"".join(items)}</div>'
    head = f"{L.ICON_SHIELD} 球队Top 10" if kind == "team" else f"{L.ICON_TROPHY} 赛事Top 10"
    return (
        f'<div id="{"team-ranking-card" if kind == "team" else "league-ranking-card"}" class="ranking-card">'
        f'<div class="card-header">{head}</div>'
        f"{inner}</div>"
    )


def _date_input(dates: list[str], cur: str, mode: str, pre: str = "") -> str:
    """原生日历选择控件（input[type=date]，点开即日历面板）。

    dates 为可选日期（YYYY-MM-DD）；选中无数据的日期时由全局 JS 吸附到
    最近的有数据日期。mode 决定 change 行为：jump=跳日期页 / ai=切 AI 卡
    radio / odds=重渲染赔率面板 / bets=仅存值待「添加场次」读取。
    """
    import json as _json

    return (
        '<input type="date" class="date-cal" '
        f'value="{cur}" min="{min(dates)}" max="{max(dates)}" '
        f'data-mode="{mode}" data-pre="{pre}" '
        f"data-dates='{_json.dumps(dates, separators=(',', ':'))}'>"
    )


def build_ai_digest(days: list[Day], top_n_dates: int = 6) -> list[tuple]:
    """右栏「AI 预测」卡数据：最近若干交易日的报告预测首选（方向/比分/进球/半全场）。

    每场取各维 rank==1 的首选结论 + 概率，与左侧卡片标签同一数据源（jinbet 报告）；
    某维缺失就少一颗 chip，不硬凑。返回 [(date, 场数, [item]), ...]，最新日期在前，
    item = {id, code, lg, home, away, picks: [(kind, label, prob)]}，lg 供卡内赛事筛选。
    """
    ds = sorted(days, key=lambda d: d.date)[-top_n_dates:]
    out = []
    for d in reversed(ds):
        items = []
        for m in sort_matches(d.matches):
            picks = []
            for kind in ("direction", "score", "goals", "htft"):
                fs = m.forecasts_of(kind)
                if fs:
                    picks.append((kind, fs[0].label, fs[0].prob))
            items.append({
                "id": m.match_id, "code": m.code, "lg": m.competition or "",
                "home": m.home.name, "away": m.away.name, "picks": picks,
            })
        out.append((d.date, len(items), items))
    return out


def _ai_card(digest: list[tuple], pre: str = "") -> str:
    """右栏「AI 预测」卡：筛选与左侧赛程完全同构，独立成条。

    结构 = 卡头标题 + 筛选条（‹ 日期 › + 「筛选」按钮，与左侧同款）+
    收起式面板（时间行 = 同款按月分组下拉；赛事行 = 同款芯片）+ 场次列表。
    隐藏 radio 只是状态载体：下拉/箭头经全局 JS 改其选中态，内容显隐仍走
    纯 CSS（body:has）规则。概率一律走 C.prob_tag（pct 红线口径）。
    """
    if not digest:
        return ""
    lg_idx: dict[str, str] = {}
    for _, _, items in digest:
        for it in items:
            if it["lg"] and it["lg"] not in lg_idx:
                lg_idx[it["lg"]] = str(len(lg_idx))

    radios, date_spans, bodies, rules = [], [], [], []
    dates_all: list[str] = []
    first = True
    for i, (date, n, items) in enumerate(digest):
        if not items:
            continue
        lab = f"{int(date[5:7])}月{int(date[8:10])}日 ({n}场)"
        checked = " checked" if first else ""
        first = False
        dates_all.append(date)
        radios.append(
            f'<input type="radio" name="aid" id="aid-{i}" class="fp-radio"{checked}>'
        )
        rules.append(f'body:has(#aid-{i}:checked) .ai-body-{i}{{display:block}}')
        # 筛选条日期随 radio 联动显隐（纯 CSS）
        date_spans.append(f'<span class="ai-date ai-date-{i}">{C.esc(lab)}</span>')
        rules.append(
            f'body:has(#aid-{i}:checked) .ai-date-{i}{{display:inline}}'
        )
        rows = []
        for it in items:
            chips = "".join(
                f'<span class="ai-chip">{icon} {C.esc(label)} {C.prob_tag(p)}</span>'
                for icon, (kind, label, p) in zip(
                    (L.ICON_TARGET, L.ICON_HASH, L.ICON_SPORTS, L.ICON_TREND),
                    it["picks"], strict=False,
                )
            )
            code = f'<span class="ai-m-code">{C.esc(it["code"])}</span>' if it["code"] else ""
            lg_attr = f' data-lg="{lg_idx[it["lg"]]}"' if it["lg"] in lg_idx else ""
            rows.append(
                f'<a class="ai-m" href="{pre}matches/{it["id"]}.html"{lg_attr}>'
                f'<div class="ai-m-head">{code}'
                f'<span class="ai-m-vs">{C.esc(it["home"])} vs {C.esc(it["away"])}</span></div>'
                f'<div class="ai-m-picks">{chips}</div></a>'
            )
        bodies.append(f'<div class="ai-body ai-body-{i}">{"".join(rows)}</div>')

    # 赛事行：全部（默认）+ 各联赛；选中某联赛时其余场次隐藏
    lg_opts = [
        '<input type="radio" name="ail" id="ail-all" class="fp-radio" checked>'
        '<label class="fp-opt" for="ail-all">全部</label>'
    ]
    for name, idx in lg_idx.items():
        lg_opts.append(
            f'<input type="radio" name="ail" id="ail-{idx}" class="fp-radio">'
            f'<label class="fp-opt" for="ail-{idx}">{C.esc(name)}</label>'
        )
        rules.append(
            f'body:has(#ail-{idx}:checked) #ai-pred-card '
            f'.ai-m:not([data-lg="{idx}"]){{display:none}}'
        )
    # 面板展开：#afp-toggle 与左侧 #fp-toggle 同机制但独立 id，互不影响
    rules.insert(0, "body:has(#afp-toggle:checked) #ai-filter-panel{display:block}")
    # 日期联动 span 在筛选条（.v4-date）里：默认全隐，选中项由 body:has 显示。
    # 注意筛选条已移出卡片，选择器必须是 .ai-bar 而非 .ai-pred-card
    rules.insert(0, ".ai-bar .ai-date{display:none}")

    # 筛选条：与左侧同款且完全独立在卡片外（‹ 更早一天 · 日期 · 更晚一天 › +
    # 筛选按钮）。列表最新在前：‹ = selectedIndex+1，› = selectedIndex-1（JS 处理）。
    bar = (
        '<div class="v4-filter-bar ai-bar">'
        '<div class="v4-date-nav">'
        f'<a class="v4-day-arrow" href="#" data-aid-step="1" aria-label="前一天">{L.ICON_CHEV_L}</a>'
        f'<div class="v4-date">{L.ICON_CALENDAR} {"".join(date_spans)}</div>'
        f'<a class="v4-day-arrow" href="#" data-aid-step="-1" aria-label="后一天">{L.ICON_CHEV_R}</a>'
        "</div>"
        '<label class="v4-filter-btn" for="afp-toggle">'
        f'<span>{L.ICON_FILTER} 筛选</span></label>'
        "</div>"
    )
    panel = (
        '<div id="ai-filter-panel">'
        '<div class="fp-row"><div class="fp-label">时间:</div>'
        f"{_date_input(dates_all, dates_all[0], 'ai')}"
        "</div>"
        '<div class="fp-row"><div class="fp-label">赛事:</div>'
        f'<div class="fp-options">{"".join(lg_opts)}</div></div>'
        "</div>"
    )
    return (
        "<style>" + "".join(rules) + "</style>"
        # 筛选条完全独立在卡片外：与左侧筛选条同级、同款白条
        f"{bar}"
        '<div id="ai-pred-card" class="ranking-card ai-pred-card">'
        f'{"".join(radios)}'
        f'<input type="checkbox" id="afp-toggle" class="fp-toggle">'
        f'<div class="card-header">{L.ICON_CPU} AI 预测</div>'
        f"{panel}"
        f'{"".join(bodies)}'
        "</div>"
    )


def render_day(cfg: Config, day: Day, *, is_today: bool = False, rel: str = "",
               ranking: list[tuple[str, int, int]] | None = None,
               team_ranking: list[tuple[str, int, int]] | None = None,
               dates: list[str] | None = None,
               ai_digest: list[tuple] | None = None) -> str:
    base = cfg.base_url.rstrip("/")
    ms = sort_matches(day.matches)
    if is_today:
        h1 = f"{day.date} 赛事量化分析"
        rel_url = f"{base}/"
    else:
        h1 = f"{day.date} 赛事量化归档"
        rel_url = f"{base}/{rel.lstrip('/')}"
    leagues = sorted({m.competition for m in ms if m.competition})
    desc = (
        f"{day.date} 共 {len(ms)} 场赛事的结构化量化数据与结论，"
        f"含 {C.esc('、'.join(leagues))}。"
    )
    lg_idx = {lg: str(i) for i, lg in enumerate(leagues)}
    cards = "".join(
        _card(cfg, m, pre="" if is_today else "../", lg=lg_idx.get(m.competition, ""))
        for m in ms
    ) or "<p>当日无赛事数据。</p>"

    # 筛选区：对齐 qiuxiaoce——主张条 + 「🔍 筛选」按钮 + 展开式两行面板
    # （类型 / 赛事）。纯 CSS：checkbox 控制面板展开，radio 控制选中态。
    # 类型行按真实数据出项（当前源全为竞彩；北单/其他类型无数据不放假选项）。
    has_jc = any(m.code for m in ms)
    type_opts = [
        '<input type="radio" name="ft" id="ft-all" class="fp-radio" checked>'
        '<label class="fp-opt" for="ft-all">全部</label>'
    ]
    if has_jc:
        type_opts.append(
            '<input type="radio" name="ft" id="ft-jc" class="fp-radio">'
            '<label class="fp-opt" for="ft-jc">竞彩</label>'
        )
    # 竞彩选中 = 全显示（数据全为竞彩），无需额外规则。
    date_lab = f"{int(day.date[5:7])}月{int(day.date[8:10])}日"
    league_row = ""
    filter_css = ""
    if len(leagues) > 1:
        opts = [
            '<input type="radio" name="lf" id="lf-all" class="fp-radio" checked>'
            '<label class="fp-opt" for="lf-all">全部</label>'
        ]
        rules = []
        for i, lg in enumerate(leagues):
            opts.append(
                f'<input type="radio" name="lf" id="lf-{i}" class="fp-radio">'
                f'<label class="fp-opt" for="lf-{i}">{C.esc(lg)}</label>'
            )
            # radio 在面板深处，不是 .cards 的兄弟，不能用 `~`；
            # 用 body:has() 从根上匹配，规则不受 DOM 层级限制。
            rules.append(
                f'body:has(#lf-{i}:checked) .cards .match-card:not([data-lg="{i}"])'
                "{display:none}"
            )
        league_row = (
            '<div class="fp-row"><div class="fp-label">赛事:</div>'
            f'<div class="fp-options">{"".join(opts)}</div></div>'
        )
        filter_css = "<style>" + "".join(rules) + "</style>"
    type_row = (
        '<div class="fp-row"><div class="fp-label">类型:</div>'
        f'<div class="fp-options">{"".join(type_opts)}</div></div>'
        if has_jc
        else ""
    )
    # 时间行：跨日期切换赛程（导航，不是本页过滤）。不用日期条——日期堆到
    # 成百上千时全量展开不可用；改按月分组的原生下拉（数量无上限、不占版面），
    # 配合筛选条上的 ‹ › 箭头做前后翻日。
    time_row = ""
    arrows = ""
    if dates:
        pre_d = "" if is_today else "../"
        idx = dates.index(day.date) if day.date in dates else -1
        prev_d = dates[idx + 1] if 0 <= idx < len(dates) - 1 else None  # 更早一天
        next_d = dates[idx - 1] if idx > 0 else None  # 更晚一天
        def arrow(d, label, icon):
            if d:
                return (f'<a class="v4-day-arrow" href="{pre_d}days/{d}.html" '
                        f'aria-label="{label}">{icon}</a>')
            return f'<span class="v4-day-arrow off" aria-hidden="true">{icon}</span>'

        arrows = (
            f'{arrow(prev_d, "前一天", L.ICON_CHEV_L)}'
            f'<div class="v4-date">{L.ICON_CALENDAR} {date_lab} ({len(ms)}场)</div>'
            f'{arrow(next_d, "后一天", L.ICON_CHEV_R)}'
        )
        time_row = (
            '<div class="fp-row"><div class="fp-label">时间:</div>'
            f"{_date_input(dates, day.date, 'jump', pre=pre_d)}"
            "</div>"
        )
    panel = (
        f'{filter_css}<input type="checkbox" id="fp-toggle" class="fp-toggle">'
        '<div id="filter-panel" class="filter-panel">'
        f"{time_row}{type_row}{league_row}"
        "</div>"
    )
    main_col = (
        '<div class="v4-main-col">'
        '<div class="v4-filter-bar">'
        f'<div class="v4-date-nav">{arrows or f"<div class=\"v4-date\">{L.ICON_CALENDAR} {date_lab} ({len(ms)}场)</div>"}</div>'
        '<label class="v4-filter-btn" for="fp-toggle">'
        f'<span>{L.ICON_FILTER} 筛选</span></label>'
        "</div>"
        f"{panel}"
        f'<div class="cards">{cards}</div>'
        "</div>"
    )
    body = (
        f'<h1 class="sr-only">{C.esc(h1)}</h1>'
        f'<div class="v4-layout">{main_col}'
        '<aside class="right-sidebar-new">'
        f'{_ai_card(ai_digest or [], pre="../" if not is_today else "")}'
        f'{_ranking_card(ranking or [], pre="../" if not is_today else "")}'
        f'{_ranking_card(team_ranking or [], pre="../" if not is_today else "", kind="team")}'
        "</aside>"
        "</div>"
    )
    jsonld = [
        _graph(cfg, {
            "@type": "CollectionPage",
            "@id": rel_url,
            "url": rel_url,
            "name": h1,
            "description": desc,
            "datePublished": day.date,
            "mainEntity": {
                "@type": "ItemList",
                "numberOfItems": len(ms),
                "itemListElement": [
                    {
                        "@type": "ListItem",
                        "position": i + 1,
                        "url": f"{base}/matches/{m.match_id}.html",
                        "name": m.title,
                    }
                    for i, m in enumerate(ms)
                ],
            },
        })
    ]
    return L.page(
        cfg, title=h1, description=desc, body=body, canonical=rel_url,
        jsonld=jsonld,
        depth=0 if is_today else 1,
        head=f"{cfg.site_name} · {cfg.site_tagline}" if is_today else None,
    )


def render_archive_index(cfg: Config, days: list[str],
                         leagues: list[tuple[str, int, dict]] | None = None,
                         teams: list[tuple[str, int, int, int]] | None = None) -> str:
    """历史归档页：交易日 / 联赛 / 球队 三视图（纯 CSS radio 切换）。

    leagues 元素为 (名称, 已收录场数, {维度: (命中数, 有存档场次)})；
    teams 元素为 (名称, 已收录场数, 命中场数, 已结算场数)。
    """
    base = cfg.base_url.rstrip("/")
    ds = sorted(days, reverse=True)
    date_items = "".join(
        f'<a class="arch-day" href="{d}.html">'
        f'<span class="arch-date">{C.esc(d)}</span><span class="arch-go">查看 →</span></a>'
        for d in ds
    )

    def _grid(items: list[tuple[str, int, int, int]], kind: str) -> str:
        cells = []
        for name, n, hit, total in items:
            acc = (hit / total * 100) if total else 0.0
            bar = (
                f'<div class="rank-bar-wrap"><div class="rank-bar" style="width:{acc:.1f}%"></div></div>'
                if total
                else '<div class="rank-bar-wrap"></div>'
            )
            acc_txt = f'<span class="rank-acc pct">{acc:.1f}%</span>' if total else '<span class="mini">待回填</span>'
            cells.append(
                f'<a class="arch-cell" href="../{kind}/{C.esc(name)}.html">'
                f'<span class="arch-name">{C.esc(name)}</span>'
                f'<span class="arch-n">{n} 场</span>'
                f'{bar}{acc_txt}</a>'
            )
        return f'<div class="arch-grid">{"".join(cells)}</div>'

    dim_labels = (("direction", "方向"), ("score", "比分"),
                  ("goals", "进球"), ("htft", "半全场"))

    def _lg_grid(items: list[tuple[str, int, dict]]) -> str:
        cells = []
        for name, n, dims in items:
            parts = []
            for key, label in dim_labels:
                hit, sample = (dims or {}).get(key, (0, 0))
                if sample:
                    val = f'<b class="pct flat">{hit / sample * 100:.1f}%</b>'
                    note = f'<em>{sample} 场</em>' if key == "htft" else ""
                else:
                    val = '<b class="pct flat na">—</b>'
                    note = ""
                parts.append(
                    f'<span class="arch-dim"><i>{label}</i>{val}{note}</span>')
            dims_html = "".join(parts)
            crest = logos.league_crest_url(name)
            badge = (
                f'<img class="arch-crest" src="../{C.esc(crest)}" alt="{C.esc(name)}徽章" decoding="async">'
                if crest
                else '<span class="arch-crest arch-crest-ph" aria-hidden="true">'
                     f'{C.esc(name[:1])}</span>'
            )
            cells.append(
                f'<a class="arch-cell arch-lg" href="../leagues/{C.esc(name)}.html">'
                f'<span class="arch-head">{badge}'
                f'<span class="arch-name">{C.esc(name)}</span></span>'
                f'<span class="arch-n">已收录 {n} 场</span>'
                f'<span class="arch-dims">{dims_html}</span></a>'
            )
        return f'<div class="arch-grid arch-lg-grid">{"".join(cells)}</div>'

    lg_view = _lg_grid(leagues or []) or '<p class="sub">暂无联赛数据。</p>'
    tm_view = _grid(teams or [], "teams") or '<p class="sub">暂无球队数据。</p>'
    body = (
        "<h1>历史归档</h1>"
        f'<p class="sub">共 {len(ds)} 个交易日，逐日归档；'
        "也可按联赛 / 球队维度浏览。</p>"
        '<div class="arch-tabs">'
        '<input type="radio" name="arch" id="at-date" class="fp-radio" checked>'
        '<label class="fp-opt" for="at-date">📅 按交易日</label>'
        '<input type="radio" name="arch" id="at-lg" class="fp-radio">'
        '<label class="fp-opt" for="at-lg">按联赛</label>'
        '<input type="radio" name="arch" id="at-tm" class="fp-radio">'
        '<label class="fp-opt" for="at-tm">按球队</label>'
        '<div class="arch-view av-date">'
        f'<div class="arch-days">{date_items}</div>'
        "</div>"
        f'<div class="arch-view av-lg">{lg_view}</div>'
        f'<div class="arch-view av-tm">{tm_view}</div>'
        "</div>"
    )
    return L.page(
        cfg, title="历史归档", description="按日期、联赛、球队归档的全部赛事分析",
        body=body, canonical=f"{base}/days/", depth=1,
    )


# ---------------------------------------------------------------- Schema.org


def _graph(cfg: Config, node: dict[str, Any]) -> dict[str, Any]:
    return {"@context": "https://schema.org", **node}


def _match_jsonld(cfg: Config, m: Match, url: str, title: str, desc: str) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = [
        _graph(cfg, {
            "@type": ["Article", "AnalysisNewsArticle"],
            "@id": url,
            "url": url,
            "headline": title,
            "description": desc,
            "datePublished": (m.generated_at or m.kickoff or m.day)[:19],
            "dateModified": (m.generated_at or m.kickoff or m.day)[:19],
            "author": {"@type": "Organization", "name": cfg.author, "url": cfg.base_url},
            "publisher": {"@type": "Organization", "name": cfg.author, "url": cfg.base_url},
            "inLanguage": cfg.language,
        })
    ]
    blocks.append(
        _graph(cfg, {
            "@type": "SportsEvent",
            "name": f"{m.home.name} vs {m.away.name}",
            "startDate": m.kickoff,
            "location": {"@type": "Place", "name": m.venue or "—"},
            "competition": m.competition,
            "homeTeam": {"@type": "SportsTeam", "name": m.home.name},
            "awayTeam": {"@type": "SportsTeam", "name": m.away.name},
        })
    )
    return blocks


# ---------------------------------------------------------------- 独立页面
# 页头四按钮（📊数据 / 🧩功能 / 👤我的 / 🔍搜索）的真实落地页。
# 对齐 qiuxiaoce：每个导航项都有页面，不出现"点了跳首页"的死按钮。


def render_stats(cfg: Config, days: list[Day]) -> str:
    """📊数据统计：结构与球小策 /shu-ju-tong-ji/ 对齐。

    区块：口径说明 → 三大总览卡 → 四维明细卡 → 近10天走势 + 球队表现查询
    → 联赛/杯赛准确率排名 → 球队准确率 Top 30。
    全部数字实时从已发布数据计算，不造假；准确率主口径=方向命中。
    """
    import json as _json

    base = cfg.base_url.rstrip("/")
    ordered = sorted(days, key=lambda d: d.date)
    n_matches = sum(len(d.matches) for d in ordered)
    settled = [m for d in ordered for m in d.matches if m.result and m.result.full_score]
    hit = sum(1 for m in settled if m.result.direction_hit)
    acc = (hit / len(settled) * 100) if settled else 0.0

    # ---- 四维明细（仅统计有该维预测结论的已结算场次）----
    def _dim(name: str) -> tuple[int, int]:
        s = [m for m in settled if getattr(m.result, f"{name}_hit") is not None]
        h = sum(1 for m in s if getattr(m.result, f"{name}_hit"))
        return h, len(s)

    dims = [("direction", "方向"), ("score", "比分"), ("goals", "进球"), ("htft", "半全场")]
    dim_cards = ""
    for name, zh in dims:
        h, n = _dim(name)
        acc_txt = f'<span class="pct">{h / n * 100:.1f}%</span>' if n else "—"
        dim_cards += (
            f'<div class="dim-card"><div class="dim-name">{zh}</div>'
            f'<div class="dim-acc">{acc_txt}</div>'
            f'<div class="dim-n">命中 {h} / {n} 场</div></div>'
        )

    # ---- 近 10 个有结算样本的交易日走势（方向命中率）----
    trend = []
    for d in reversed(ordered):
        s = [m for m in d.matches if m.result and m.result.direction_hit is not None]
        if not s:
            continue
        h = sum(1 for m in s if m.result.direction_hit)
        trend.append((d.date[5:], h, len(s), h / len(s) * 100))
        if len(trend) >= 10:
            break
    trend.reverse()
    bars = "".join(
        f'<div class="t-col"><div class="t-val pct">{a:.0f}%</div>'
        f'<div class="t-area"><div class="t-bar" style="height:{max(a, 4):.0f}%"></div></div>'
        f'<div class="t-lbl">{C.esc(lab)}</div>'
        f'<div class="t-sub">{h}/{n}</div></div>'
        for lab, h, n, a in trend
    )
    trend_box = (
        '<div class="stats-box"><h3>📈 近10个交易日准确率走势</h3>'
        + (
            f'<div class="trend">{bars}</div>'
            if bars
            else '<p class="panel-empty">暂无已结算样本。</p>'
        )
        + "</div>"
    )

    # ---- 球队表现查询（内嵌全量球队汇总，前端过滤）----
    team_agg: dict[str, dict] = {}
    for m in settled:
        if m.result.direction_hit is None:
            continue
        rec = m.result.direction_hit
        for t, opp in ((m.home.name, m.away.name), (m.away.name, m.home.name)):
            a = team_agg.setdefault(t, {"n": 0, "h": 0, "recent": []})
            a["n"] += 1
            a["h"] += 1 if rec else 0
            if len(a["recent"]) < 5:
                a["recent"].append([m.day, opp, m.result.full_score,
                                    "胜" if rec else "未中"])
    teams_js = _json.dumps(
        [[k, v["n"], v["h"], v["recent"]] for k, v in sorted(team_agg.items())],
        ensure_ascii=False, separators=(",", ":"),
    )
    search_box = (
        '<div class="stats-box"><h3>🔍 球队表现查询</h3>'
        '<input class="search-input" id="team-q" type="text" placeholder="输入球队名，如：皇马、拜仁、利物浦" style="width:100%">'
        '<div id="team-out" class="team-out"><p class="sub">输入球队名查看该队的已结算场次与方向命中明细。</p></div>'
        "<script>\n(function () {\n"
        f"  var DATA = {teams_js};\n"
        """  var out = document.getElementById("team-out");
  document.getElementById("team-q").addEventListener("input", function () {
    var q = this.value.trim();
    if (!q) { out.innerHTML = '<p class="sub">输入球队名查看该队的已结算场次与方向命中明细。</p>'; return; }
    var rows = DATA.filter(function (r) { return r[0].indexOf(q) !== -1; }).slice(0, 8);
    if (!rows.length) { out.innerHTML = '<p class="sub">未找到该球队（仅统计已收录且已结算的场次）。</p>'; return; }
    var html = "";
    rows.forEach(function (r) {
      var acc = r[2] / r[1] * 100;
      html += '<div class="team-stat"><div class="ts-head"><b>' + r[0] + '</b>'
        + '<span>已结算 ' + r[1] + ' 场 · 方向命中 <span class="pct">' + acc.toFixed(1) + '%</span></span></div><table class="history-table"><tr><th>日期</th><th>对手</th><th>比分</th><th>方向</th></tr>';
      r[3].forEach(function (g) {
        html += '<tr><td>' + g[0] + '</td><td>' + g[1] + '</td><td>' + g[2] + '</td><td>' + g[3] + '</td></tr>';
      });
      html += '</table></div>';
    });
    out.innerHTML = html;
  });
})();
</script></div>"""
    )

    # ---- 联赛/杯赛排名（带四维）----
    lg_agg: dict[str, dict] = {}
    for m in settled:
        if not m.competition or m.result.direction_hit is None:
            continue
        a = lg_agg.setdefault(m.competition, {"n": 0, "h": 0})
        for name, _ in dims:
            v = getattr(m.result, f"{name}_hit")
            if v is not None:
                d = a.setdefault(name, [0, 0])
                d[1] += 1
                d[0] += 1 if v else 0
        a["n"] += 1
        a["h"] += 1 if m.result.direction_hit else 0
    lg_rows_list = sorted(
        lg_agg.items(), key=lambda kv: (-(kv[1]["h"] / kv[1]["n"]), -kv[1]["n"], kv[0])
    )

    def _rank_badge(name: str, src: str) -> str:
        """排名表名称前的徽章：有素材用真图，没有的用首字圆徽。"""
        if src:
            return (f'<img class="rank-crest" src="{C.esc(src)}" alt="" '
                    'loading="lazy" decoding="async">')
        ch = (name or "").strip()[:1] or "·"
        return (f'<span class="rank-crest rank-crest-ph" aria-hidden="true">'
                f'{C.esc(ch)}</span>')

    def _rank_name(name: str, src: str) -> str:
        return (f'<span class="rank-name" title="{C.esc(name)}">'
                f'{_rank_badge(name, src)}'
                f'<span>{C.esc(name)}</span></span>')

    def _pc(pair) -> str:
        h, n = pair
        return f'<span class="pct">{h / n * 100:.0f}%</span>' if n else "—"

    lg_rows = [
        [_rank_name(lg, logos.league_crest_url(lg)), str(a["n"]), f'<span class="pct">{a["h"] / a["n"] * 100:.1f}%</span>',
         _pc(a.get("direction", [0, 0])), _pc(a.get("score", [0, 0])),
         _pc(a.get("goals", [0, 0])), _pc(a.get("htft", [0, 0]))]
        for lg, a in lg_rows_list
    ]
    league_box = (
        '<div class="stats-box"><h3>🏆 各联赛、杯赛准确率排名</h3>'
        + (
            C.table(["赛事", "场次", "准确率", "方向", "比分", "进球", "半全场"], lg_rows, cls="history-table")
            if lg_rows
            else '<p class="panel-empty">暂无已结算赛事，赛后自动回填。</p>'
        )
        + "</div>"
    )

    # ---- 球队 Top 30 ----
    top_teams = compute_team_ranking(ordered, top=30)
    t_rows = [
        [str(i), _rank_name(name, logos.crest_url(name)), str(n),
         f'<span class="pct">{h / n * 100:.1f}%</span>']
        for i, (name, h, n) in enumerate(top_teams, 1)
    ]
    team_box = (
        '<div class="stats-box"><h3>🛡️ 球队准确率排名 (Top 30)</h3>'
        + (
            C.table(["#", "球队", "已结算", "准确率"], t_rows, cls="history-table")
            if t_rows
            else '<p class="panel-empty">暂无已结算样本。</p>'
        )
        + "</div>"
    )

    # ---- 洞察总结：每日命中率线图 + 维度横条 + 结论 chips（居中） ----
    day_acc = []
    for d in ordered:
        dd = [m for m in d.matches if m.result and m.result.full_score]
        if dd:
            day_acc.append((d.date[5:], sum(1 for m in dd if m.result.direction_hit) / len(dd) * 100, len(dd)))
    dim_ok = [(zh, _dim(name)[0] / _dim(name)[1] * 100, _dim(name)[1])
              for name, zh in dims if _dim(name)[1] >= 5]
    by_lg_acc: dict[str, tuple[int, int]] = {}
    for m in settled:
        if m.competition:
            h2, n2 = by_lg_acc.get(m.competition, (0, 0))
            by_lg_acc[m.competition] = (h2 + (1 if m.result.direction_hit else 0), n2 + 1)
    lg_ok = [(k, v[0] / v[1] * 100, v[1]) for k, v in by_lg_acc.items() if v[1] >= 5]

    viz: list[str] = []
    if len(day_acc) >= 2:
        xs = [x[0] for x in day_acc]
        ys = [x[1] for x in day_acc]
        ns = [x[2] for x in day_acc]
        kw = dict(baseline=33.3, baseline_label="随机基线 33.3",
                  average=acc, counts=ns)
        trend = (
            C.line_svg(xs, ys, w=1120, h=240, cls="itrend-desk", **kw)
            + C.line_svg(xs, ys, w=620, h=200, cls="itrend-mob", **kw)
        )
        if trend:
            legend = (
                '<div class="itrend-legend">'
                '<span><i class="lg-bar"></i>当日场次</span>'
                '<span><i class="lg-avg"></i>整体均值 <b class="pct">'
                f'{acc:.1f}%</b></span>'
                '<span><i class="lg-base"></i>随机基线</span>'
                "</div>"
            )
            viz.append('<div class="insight-block"><h4>每日命中率走势</h4>'
                       + legend + trend + "</div>")
    if dim_ok:
        bars = "".join(
            f'<div class="hbar-row"><span class="hbar-label">{C.esc(zh)}</span>'
            f'<span class="hbar-track"><span class="hbar-fill" style="width:{p:.1f}%"></span></span>'
            f'<span class="hbar-num"><span class="pct">{p:.1f}%</span></span>'
            f'<span class="hbar-n">{n} 场</span></div>'
            for zh, p, n in dim_ok
        )
        viz.append('<div class="insight-block"><h4>单项维度准确率</h4>' + bars + "</div>")
    chips: list[str] = []
    if settled:
        chips.append(
            f'🎯 已结算 <b>{len(settled)}</b> 场 · 命中 <b>{hit}</b> 场 · '
            f'整体 <span class="pct"><b>{acc:.1f}%</b></span>'
        )
    if lg_ok:
        blg = max(lg_ok, key=lambda x: x[1])
        chips.append(f'🏆 表现最佳赛事：「{C.esc(blg[0])}」<span class="pct"><b>{blg[1]:.1f}%</b></span>（{blg[2]} 场）')
    insight_box = ""
    if viz or chips:
        chip_html = (
            '<div class="insight-chips">' + "".join(f'<span class="insight-chip">{x}</span>' for x in chips) + "</div>"
            if chips else ""
        )
        insight_box = (
            '<div class="stats-box insight-box"><h3>🧾 洞察总结</h3>'
            '<div class="insight-viz">' + "".join(viz) + chip_html + "</div></div>"
        )

    body = (
        f"<h1 class='page-h1'>{L.ICON_DATA} 数据统计</h1>"
        '<div class="stats-grid stats-main">'
        f'<div class="stat-card"><div class="pct stat-num">{n_matches}</div><div class="stat-lbl">📊 总预测场次</div></div>'
        f'<div class="stat-card"><div class="pct stat-num">{acc:.1f}%</div><div class="stat-lbl">🎯 整体准确率</div></div>'
        f'<div class="stat-card"><div class="pct stat-num">{hit}</div><div class="stat-lbl">✅ 命中场次</div></div>'
        "</div>"
        + insight_box
        + '<div class="stats-box"><h3>🔍 单项维度准确率</h3>'
        f'<div class="dim-grid">{dim_cards}</div></div>'
        f'<div class="stats-duo">{trend_box}{search_box}</div>'
        f'<div class="stats-duo">{league_box}{team_box}</div>'
    )
    return L.page(
        cfg, title="数据统计", description="站点赛事统计：总场次、四维准确率、近10天走势、联赛与球队排名",
        body=body, canonical=f"{base}/data.html", depth=0,
    )


# ---------------------------------------------------------------- 每日赛事前瞻（独立模块 preview/，纯列表）


def _pv_sort_key(m: Match):
    """按编号里的数字排序（周四002 → 2），无编号的排最后。"""
    import re as _re

    mm = _re.search(r"(\d+)", m.code or "")
    return (int(mm.group(1)) if mm else 999, m.kickoff or "")


def _pv_wd(date: str) -> str:
    try:
        from datetime import date as _date

        y, mo, dy = (int(x) for x in date.split("-"))
        return "周" + "一二三四五六日"[_date(y, mo, dy).weekday()]
    except Exception:
        return ""


def render_preview_index(cfg: Config, ordered: list[Day]) -> str:
    """📅 每日赛事前瞻（独立模块 preview/）：**列表页**。

    只做 AI 报告入口列表：每日一条（日期 / 星期 / 场次 / 覆盖联赛）。
    报告页暂用原项目（jinbet predictions）的已发布链接，后续可切换为
    站内 preview/YYYY-MM-DD.html（render_preview_day 已备好未接线）。
    列表页本身不复刻报告内容。
    """
    base = cfg.base_url.rstrip("/")
    ext = "https://jinbigbig.github.io/jinbet/predictions"
    days = [d for d in reversed(ordered) if d.matches]

    # 按年→月分组，<details> 原生展开收起；最新年/月默认展开
    def card(d: Day) -> str:
        lgs: list[str] = []
        for m in d.matches:
            if m.competition and m.competition not in lgs:
                lgs.append(m.competition)
        lg_txt = "、".join(lgs[:3]) + ("等" if len(lgs) > 3 else "")
        return (
            f'<a class="pv-day" href="{ext}/{d.date}/" target="_blank" rel="noopener">'
            f'<span class="pv-d">{d.date}</span><span class="pv-w">{_pv_wd(d.date)}</span>'
            f'<span class="pv-n">共 {len(d.matches)} 场</span>'
            f'<span class="pv-lg">{C.esc(lg_txt)}</span>'
            f'<span class="pv-go">打开 AI 报告 ↗</span></a>'
        )

    years: dict[str, dict[str, list[Day]]] = {}
    for d in days:
        y, mo = d.date[:4], d.date[5:7]
        years.setdefault(y, {}).setdefault(mo, []).append(d)
    top_year = next(iter(years))
    top_month = next(iter(years[top_year]))
    year_blocks = []
    for y, months in years.items():
        month_blocks = []
        for mo, mds in months.items():
            open_m = ' open' if (y == top_year and mo == top_month) else ''
            month_blocks.append(
                f'<details class="pv-month"{open_m}>'
                f'<summary>{int(mo)} 月 <i>{len(mds)} 天报告</i></summary>'
                f'<div class="pv-grid">{"".join(card(d) for d in mds)}</div>'
                f"</details>"
            )
        open_y = ' open' if y == top_year else ''
        year_blocks.append(
            f'<details class="pv-year"{open_y}>'
            f'<summary>{y} 年 <i>{sum(len(v) for v in months.values())} 天报告</i></summary>'
            + "".join(month_blocks)
            + "</details>"
        )
    body = (
        f"<h1 class='page-h1'>{L.ICON_ARCHIVE} 每日赛事前瞻</h1>"
        '<p class="pv-lead">每日 AI 报告列表。</p>'
        '<div class="pv-tree">' + "".join(year_blocks) + "</div>"
    )
    return L.page(
        cfg, title="每日赛事前瞻",
        description="每日赛事前瞻列表：AI 报告逐日归档，方向、比分、总进球首选与信心分层",
        body=body, canonical=f"{base}/preview/", depth=1,
    )


def render_preview_day(cfg: Config, d: Day, prev: Day | None = None) -> str:
    """📅 单日 AI 报告页（preview/YYYY-MM-DD.html，独立静态页存进项目）。

    打开方式与 jinbet predictions 一致：列表页点开日期 → 当日报告成页留档。
    内容：当日总览表（按编号排序）+ 重点场次主推 + 前日回顾 + 免责声明；
    前瞻只含赛前可得信息（forecasts / main_pick / confidence），回顾用已回填赛果。
    """
    base = cfg.base_url.rstrip("/")
    ms = sorted(d.matches, key=_pv_sort_key)
    n = len(ms)
    lgs = sorted({m.competition for m in ms if m.competition})

    def fc(m: Match, kind: str) -> str:
        fs = m.forecasts_of(kind)
        if not fs:
            return "—"
        return f'{C.esc(fs[0].label)} <i><span class="pct">{fs[0].prob * 100:.0f}%</span></i>'

    rows = []
    for m in ms:
        rows.append(
            "<tr>"
            f"<td><b>{C.esc(m.code)}</b><span class='pv-lg2'>{C.esc(m.competition)}</span></td>"
            f"<td class='pv-tm'>{C.esc((m.kickoff or '')[-5:] or '—')}</td>"
            f"<td><a class='team-link' href='../matches/{m.match_id}.html'>"
            f"<b>{C.esc(m.home.name)}</b> vs <b>{C.esc(m.away.name)}</b></a></td>"
            f"<td>{fc(m, 'direction')}</td><td>{fc(m, 'score')}</td><td>{fc(m, 'goals')}</td>"
            f"<td><span class='pv-conf pv-c-{m.confidence}'>{C.esc(m.confidence_label)}</span></td>"
            "</tr>"
        )
    overview = (
        '<div class="bets-twrap"><table class="bets-table pv-table"><thead><tr>'
        "<th>编号 · 联赛</th><th>开赛</th><th>对阵</th><th>方向首选</th>"
        "<th>比分首选</th><th>总进球</th><th>信心</th>"
        "</tr></thead><tbody>" + "".join(rows) + "</tbody></table></div>"
    )

    hot = [m for m in ms if m.main_pick or m.confidence == "high"]
    hot_cards = ""
    for m in hot:
        hl = m.headline
        titles = {"direction": "方向", "score": "比分", "goals": "进球", "htft": "半全场"}
        chips = "".join(
            f'<span class="pv-chip"><b>{t}</b>{C.esc(hl[k].label)} <i><span class="pct">{hl[k].prob * 100:.0f}%</span></i></span>'
            for k, t in titles.items() if hl.get(k)
        )
        hot_cards += (
            '<div class="pv-hot">'
            f'<div class="pv-hot-h"><span class="nb-code">{C.esc(m.code)}</span>'
            f'<span class="pv-hot-vs"><b>{C.esc(m.home.name)}</b> <i>VS</i> <b>{C.esc(m.away.name)}</b></span>'
            f'<span class="pv-conf pv-c-{m.confidence}">{C.esc(m.confidence_label)}</span>'
            f'<a class="pv-more" href="../matches/{m.match_id}.html">完整分析 →</a></div>'
            + (f'<p class="pv-pick">{C.esc(m.main_pick)}</p>' if m.main_pick else "")
            + (f'<div class="pv-chips">{chips}</div>' if chips else "")
            + "</div>"
        )

    # ---- 赛前环境：伤停 / 天气 / 裁判（当日快照，import 按 date 防错配）----
    env_cards = ""
    for m in ms:
        ex = m.extras or {}
        lines: list[str] = []
        w = ex.get("weather")
        if w:
            grade = {"ok": "✅ 适宜", "watch": "⚠️ 需留意", "bad": "🌧 恶劣"}.get(w.get("grade"), "")
            lines.append(
                f'🌤 天气 · {C.esc(w.get("city", ""))} {w.get("t_min")}~{w.get("t_max")}℃ · '
                f'降雨 <span class="pct">{w.get("pop")}%</span> · 风速 {w.get("wind")}km/h {grade}')
        r = ex.get("referee")
        if r:
            stat = ""
            if r.get("h") is not None:
                stat = (f'近20场主队 {r["h"]}胜{r["d"]}平{r["a"]}负 · '
                        f'黄牌 {r.get("yellow", "?")} · 红牌 {r.get("red", "?")} · 点球 {r.get("pen", "?")}')
            lines.append(
                f'🟨 裁判 · {C.esc(r["ref"])}（{C.esc(r.get("nation") or "")}'
                + (f'{r["age"]}岁' if r.get("age") else "") + f'）{stat}')
        inj = ex.get("injuries")
        if inj:
            def _names(side: dict | None) -> str:
                if not side:
                    return ""
                ppl = [f'{p.get("name", "")}（{p.get("reason", "")}）'.replace("（）", "")
                       for p in (side.get("out") or []) + (side.get("doubtful") or [])]
                return "、".join(ppl)
            hn, an = _names(inj.get("home")), _names(inj.get("away"))
            if hn or an:
                parts = []
                if hn:
                    parts.append(f'{C.esc(m.home.name)}：{C.esc(hn)}')
                if an:
                    parts.append(f'{C.esc(m.away.name)}：{C.esc(an)}')
                lines.append("🏥 伤停 · " + "；".join(parts))
        if lines:
            env_cards += (
                '<div class="pv-env">'
                f'<div class="pv-env-h"><span class="nb-code">{C.esc(m.code)}</span>'
                f'<span class="pv-env-vs"><b>{C.esc(m.home.name)}</b> <i>VS</i> <b>{C.esc(m.away.name)}</b></span></div>'
                + "".join(f'<div class="pv-env-row">{x}</div>' for x in lines)
                + "</div>"
            )
    env_box = ""
    if env_cards:
        env_box = (
            '<h2 class="pv-h2">🧭 赛前环境（伤停 / 天气 / 裁判）</h2>'
            f'<div class="pv-envs">{env_cards}</div>'
        )

    review = ""
    if prev:
        pms = sorted(prev.matches, key=_pv_sort_key)

        def mk(x: bool | None) -> str:
            if x is None:
                return ""
            return ' <b class="hit-y">✓</b>' if x else ' <b class="hit-n">✗</b>'

        rrows = []
        for m in pms:
            r = m.result
            if not (r and r.full_score):
                continue
            d1 = m.forecasts_of("direction")
            s1 = m.forecasts_of("score")
            rrows.append(
                "<tr>"
                f"<td><b>{C.esc(m.code)}</b><span class='pv-lg2'>{C.esc(m.competition)}</span></td>"
                f"<td>{C.esc(m.home.name)} vs {C.esc(m.away.name)}</td>"
                f"<td>{C.esc(d1[0].label) if d1 else '—'}{mk(r.direction_hit)}</td>"
                f"<td>{C.esc(s1[0].label) if s1 else '—'}{mk(r.score_hit)}</td>"
                f"<td class='pv-act'>{C.esc(r.full_score)}</td>"
                "</tr>"
            )
        if rrows:
            done = sum(1 for m in pms if m.result and m.result.full_score)
            hit = sum(1 for m in pms if m.result and m.result.direction_hit)
            review = (
                f'<h2 class="pv-h2">📅 前日回顾（{prev.date} 落地 {done} 场 · 方向命中 {hit}）</h2>'
                '<div class="bets-twrap"><table class="bets-table pv-table"><thead><tr>'
                "<th>编号 · 联赛</th><th>对阵</th><th>方向首选</th><th>比分首选</th><th>实际</th>"
                "</tr></thead><tbody>" + "".join(rrows) + "</tbody></table></div>"
            )

    body = (
        f"<h1 class='page-h1'>{L.ICON_ARCHIVE} {d.date} 赛事前瞻报告</h1>"
        '<a class="pv-back" href="index.html">← 返回前瞻列表</a>'
        '<div class="pv-head">'
        f'<span class="pv-w">{_pv_wd(d.date)}</span>'
        f"<span>{n} 场比赛 · {len(lgs)} 项赛事（{'、'.join(lgs[:4])}{'等' if len(lgs) > 4 else ''}）</span>"
        "<span>首选概率为站内模型输出，仅供分析参考</span>"
        "</div>"
        f'<h2 class="pv-h2">🎯 当日前瞻总览（{n} 场，按编号排序）</h2>'
        + overview
        + env_box
        + (f'<h2 class="pv-h2">📌 重点场次（{len(hot)} 场）</h2>' + hot_cards if hot_cards else "")
        + review
        + '<div class="disclaimer">本报告由站内模型自动生成，仅供数据分析参考，不构成投注建议。理性购彩，量力而行。</div>'
    )
    return L.page(
        cfg, title=f"{d.date} 赛事前瞻报告",
        description=f"{d.date} 竞彩赛事前瞻报告：{n} 场比赛方向、比分、总进球首选与信心分层，附前日复盘",
        body=body, canonical=f"{base}/preview/{d.date}.html", depth=1,
    )


def _ml_crest(name: str, tid: str = "", pre: str = "") -> str:
    """行内小队徽：赛程带的编号优先，再退站内已注入路径 / 队名映射。"""
    src = logos.crest_by_id(tid) if tid else ""
    src = src or pre or logos.crest_url(name)
    if src:
        return (f'<img class="ml-crest" src="{C.esc(src)}" alt="" '
                'loading="lazy" decoding="async" width="20" height="20">')
    return '<span class="ml-crest ml-crest-ph" aria-hidden="true"></span>'


def _ml_code(code: str) -> str:
    """竞彩完整编号，只有竞彩场次才有。"""
    return f'<em class="ml-code">{C.esc(code)}</em>' if code else ""


def _ml_form(board: dict | None, name: str) -> str:
    """队名旁五个点：该队近 5 场胜平负。榜里没有这队就不画。"""
    if not board or not name:
        return ""
    b = board.get(name)
    if b is None:
        b = next((v for k, v in board.items()
                  if len(k) >= 2 and len(name) >= 2 and (k in name or name in k)), None)
    if not b:
        return ""
    bits = [r.get("res") for r in (b.get("recent") or [])][-5:]
    if not bits:
        return ""
    dots = "".join(f'<i class="{C.esc(str(x))}"></i>' for x in bits)
    return f'<em class="mlf">{dots}</em>'


def _ml_row(m: Match, board: dict | None = None, t: str | None = None) -> str:
    """比赛列表的一行：已结算带比分与命中，未结算带方向与比分预测。"""
    crest_h = _ml_crest(m.home.name, pre=getattr(m.home, "logo", "") or "")
    crest_a = _ml_crest(m.away.name, pre=getattr(m.away, "logo", "") or "")
    time_txt = t if t is not None else ((m.kickoff or "")[-5:] or "—")
    fs = m.forecasts_of("direction") or []
    sc = m.forecasts_of("score") or []
    chips = "".join(
        f"<em>{C.esc(f[0].label)}</em>" for f in (fs, sc) if f
    )
    done = bool(m.result and m.result.full_score)
    if done:
        hit = m.result.direction_hit
        cls = "win" if hit else ("lose" if hit is False else "")
        stat = f'<span class="ml-st {cls}">{C.esc(m.result.full_score)}'
        stat += " 中" if hit else (" 未中" if hit is False else "")
        stat += "</span>"
    else:
        stat = '<span class="ml-st">待开赛</span>'
    return (
        f'<a class="mline" data-jc="1" href="matches/{m.match_id}.html">'
        f'<span class="ml-t">{C.esc(time_txt)}'
        f'{_ml_code(m.code or "")}</span>'
        f'<span class="ml-lg">{C.esc(m.competition or "")}</span>'
        '<span class="ml-teams">'
        f'<span class="ml-h">{_ml_form(board, m.home.name)}'
        f'<span class="ml-nm" title="{C.esc(m.home.name)}">{C.esc(m.home.name)}</span>'
        f'{crest_h}</span>'
        '<span class="ml-v">VS</span>'
        f'<span class="ml-a">{crest_a}'
        f'<span class="ml-nm" title="{C.esc(m.away.name)}">{C.esc(m.away.name)}</span>'
        f'{_ml_form(board, m.away.name)}</span>'
        "</span>"
        f'<span class="ml-pick">{chips}</span>'
        f"{stat}</a>"
    )


def _same_fx(a: str, b: str) -> bool:
    """赛程库与站内队名对不上时的兜底：简称 / 全称 / 译名双向包含。"""
    clean = lambda s: re.sub(r"[\s\u3000·\-()（）队]", "", s or "")
    a, b = clean(a), clean(b)
    return bool(a and b and (a == b or (len(a) >= 2 and len(b) >= 2
                                        and (a in b or b in a))))


def _ml_pending(r: dict, board: dict | None = None) -> str:
    """只有赛程的行：竞彩场次标待分析，其它联赛标仅赛程。"""
    jc = 1 if r.get("jc") else 0
    if jc:
        stat = '<span class="ml-st">待分析</span>'
    else:
        s = str(r.get("st") or "").strip()
        label = s if any(w in s for w in ("延期", "取消", "完场", "完赛")) else "仅赛程"
        stat = f'<span class="ml-st">{C.esc(label)}</span>'
    crest_h = _ml_crest(r.get("home") or "", str(r.get("hid") or ""))
    crest_a = _ml_crest(r.get("away") or "", str(r.get("aid") or ""))
    return (
        f'<div class="mline off" data-jc="{jc}">'
        f'<span class="ml-t">{C.esc(r.get("time") or "—")}'
        f'{_ml_code(str(r.get("code") or ""))}</span>'
        f'<span class="ml-lg">{C.esc(r.get("league") or "")}</span>'
        '<span class="ml-teams">'
        f'<span class="ml-h">{_ml_form(board, r.get("home") or "")}'
        f'<span class="ml-nm" title="{C.esc(r.get("home") or "")}">{C.esc(r.get("home") or "")}</span>'
        f'{crest_h}</span>'
        '<span class="ml-v">VS</span>'
        f'<span class="ml-a">{crest_a}'
        f'<span class="ml-nm" title="{C.esc(r.get("away") or "")}">{C.esc(r.get("away") or "")}</span>'
        f'{_ml_form(board, r.get("away") or "")}</span>'
        "</span>"
        '<span class="ml-pick"></span>'
        f"{stat}</div>"
    )


def _ml_time_of(m: Match, fx: list[dict]) -> str:
    """站内场次缺开赛时间时，从赛程库同编号 / 同主客队的场次借时间。"""
    t = (m.kickoff or "").strip()[-5:]
    if ":" in t:
        return t
    code = (m.code or "").strip()
    r = next((x for x in fx if code
              and str(x.get("code") or "").strip() == code), None)
    if r is None:
        r = next((x for x in fx
                  if _same_fx(x.get("home") or "", m.home.name)
                  and _same_fx(x.get("away") or "", m.away.name)), None)
    t = (str(r.get("time") or "").strip() if r else "")[:5]
    return t if ":" in t else "—"


def _ml_sort_key(t: str, code: str, kind: int) -> tuple:
    """竞彩营业日内排序：凌晨场属次日，排在当夜之后；无时间场次垫底。"""
    if not t or t == "—" or ":" not in t:
        return (2, "99:99", code == "", code, kind)
    h = int(t[:2]) if t[:2].isdigit() else 0
    if h < 9:
        return (1, f"{h + 24:02d}:{t[3:]}", code == "", code, kind)
    return (0, t, code == "", code, kind)


_ML_JUMP_JS = """<script>
(function(){
  var j=document.querySelector('.ml-jump'), t=document.querySelector('.ml-jump-a.today');
  if(j && t && j.scrollWidth > j.clientWidth){
    j.scrollLeft = t.offsetLeft - j.clientWidth/2 + t.offsetWidth/2;
  }
  function eagerize(root){
    var h = innerHeight + 300;
    root.querySelectorAll('.mline').forEach(function(r){
      var sec = r.closest('.ml-sec');
      if(sec && getComputedStyle(sec).display === 'none') return;
      if(getComputedStyle(r).display === 'none') return;
      var b = r.getBoundingClientRect();
      if(b.top < h && b.bottom > -300){
        r.querySelectorAll('img.ml-crest').forEach(function(i){ i.loading='eager'; });
      }
    });
  }
  eagerize(document);
  document.querySelectorAll('.ml-jump-a').forEach(function(a){
    a.addEventListener('click', function(){
      var day = a.getAttribute('for').slice(4);
      var sec = document.querySelector('.ml-sec[data-day="' + day + '"]');
      if(sec) setTimeout(function(){ eagerize(sec); }, 0);
    });
  });
})();
</script>"""


def render_matches(cfg: Config, days: list[Day],
                   fixtures: dict[str, list[dict]] | None = None,
                   board: dict | None = None) -> str:
    """比赛列表：按日平铺，一行一场，顶部切换竞彩 / 全部赛程。

    行态：已结算（比分 + 是否命中）、待开赛（方向与比分预测）、
    待分析（只有竞彩赛程）、仅赛程（竞彩未开售的场次）。
    站内已分析场次与赛程库按编号 + 主客队名去重，避免同一场出现两行。
    """
    base = cfg.base_url.rstrip("/")
    fixtures = fixtures or {}
    by_date = {d.date: d.matches for d in days}
    recent = sorted(by_date, reverse=True)[:4]
    dates = sorted({*recent, *fixtures}, reverse=True)[:12]
    head = f"<h1 class='page-h1'>{L.ICON_SPORTS} 比赛列表</h1>"
    if not dates:
        return L.page(
            cfg, title="比赛列表", description="按日浏览全部赛程与预测",
            body=head + '<p class="sub">暂无数据。</p>',
            canonical=f"{base}/matches.html", depth=0,
        )

    today = min(fixtures) if fixtures else (max(by_date) if by_date else "")
    counts: dict[str, int] = {}
    jc_counts: dict[str, int] = {}
    sections = []
    for d in dates:
        fx = fixtures.get(d) or []
        ms = list(by_date.get(d) or [])
        used_codes = {m.code for m in ms if m.code}
        pairs = [(m.home.name, m.away.name) for m in ms]
        pend = [r for r in fx
                if r.get("code") not in used_codes
                and not any(_same_fx(r.get("home") or "", h)
                            and _same_fx(r.get("away") or "", a) for h, a in pairs)]
        n = len(ms) + len(pend)
        jn = len(ms) + sum(1 for r in pend if r.get("jc"))
        counts[d] = n
        jc_counts[d] = jn
        tag = ""
        if d > today:
            tag = '<span class="mini">未开赛</span>'
        elif d == today:
            tag = '<span class="mini">今日</span>'
        items = []
        for m in ms:
            t = _ml_time_of(m, fx)
            items.append((_ml_sort_key(t, str(m.code or ""), 0),
                          _ml_row(m, board, t)))
        for r in pend:
            t = (str(r.get("time") or "").strip() or "—")[:5]
            items.append((_ml_sort_key(t, str(r.get("code") or ""), 1),
                          _ml_pending(r, board)))
        items.sort(key=lambda x: x[0])
        rows = "".join(html for _, html in items)
        more = "" if jn else (
            f'<label class="ml-more" for="ml-all">{d[5:].replace("-", "/")}'
            f' · {n} 场赛程，查看全部</label>')
        sections.append(
            f'<section class="ml-sec{"" if jn else " empty-jc"}" id="d-{d}" data-day="{d}">'
            f'<h2 class="ml-day">{d[5:].replace("-", "/")} · '
            f'<span class="n-jc">{jn} 场</span><span class="n-all">{n} 场</span>{tag}</h2>'
            f'<div class="mlines">{rows}</div>{more}</section>'
        )

    week = "一二三四五六日"
    cells = []
    for d in sorted(dates):
        dow = "今天" if d == today else f"周{week[dt.date.fromisoformat(d).weekday()]}"
        cls = "ml-jump-a today" if d == today else "ml-jump-a"
        cells.append(f'<label class="{cls}" for="day-{d}">'
                     f'<span class="dow">{dow}</span>'
                     f'<span class="dm">{d[5:]}</span></label>')
    jump = "".join(cells)
    day_inputs = "".join(
        f'<input type="radio" name="mlday" id="day-{d}" class="fp-radio"'
        f'{" checked" if d == today else ""}>'
        for d in sorted(dates)
    )
    rules = []
    for d in sorted(dates):
        rules.append(
            f'#day-{d}:checked ~ .ml-panel .ml-sec[data-day="{d}"]{{display:block}}'
            f'#day-{d}:checked ~ .ml-panel label[for="day-{d}"]'
            f'{{background:#fff;border-color:#dbe6ff;'
            f'box-shadow:0 3px 12px rgba(37,99,235,.13)}}'
            f'#day-{d}:checked ~ .ml-panel label[for="day-{d}"] .dow,'
            f'#day-{d}:checked ~ .ml-panel label[for="day-{d}"] .dm'
            f'{{color:var(--accent)}}'
            f'#day-{d}:checked ~ .ml-panel .sub-{d}{{display:inline}}'
        )
    day_css = ("<style>.ml-sec{display:none}.sub-day{display:none}"
               + "".join(rules) + "</style>")
    legend = (
        '<p class="ml-legend"><span><i class="w"></i>胜</span>'
        '<span><i class="d"></i>平</span><span><i class="l"></i>负</span>'
        '<b>队名旁为近 5 场</b></p>'
    )
    sub_days = "".join(
        f'<span class="sub-day sub-{d}">'
        f'<span class="n-jc">{jc_counts.get(d, 0)}</span>'
        f'<span class="n-all">{counts.get(d, 0)}</span> 场</span>'
        for d in sorted(dates)
    )
    panel = (
        f'<p class="sub ml-sub">共 {sub_days}；'
        '赛前看方向与比分，赛后就地对照赛果。</p>'
        + f'<div class="ml-jump">{jump}</div>'
        + legend
        + "".join(sections)
        + f'<p class="sub" style="margin-top:18px">更早的场次见 '
          f'<a href="{base}/days/">历史归档</a>。</p>'
    )
    body = (
        head
        + '<div class="ml-tabs">'
        + '<input type="radio" name="mlscope" id="ml-jc" class="fp-radio" checked>'
        + '<label class="fp-opt" for="ml-jc">仅竞彩</label>'
        + '<input type="radio" name="mlscope" id="ml-all" class="fp-radio">'
        + '<label class="fp-opt" for="ml-all">全部赛程</label>'
        + day_inputs
        + day_css
        + f'<div class="ml-panel">{panel}</div>'
        + '</div>'
        + _ML_JUMP_JS
    )
    return L.page(
        cfg, title="比赛列表", description="按日浏览全部赛事，方向与比分旁边就是赛果",
        body=body, canonical=f"{base}/matches.html", depth=0,
    )


def render_features(cfg: Config) -> str:
    """功能页：站点功能清单。只列已上线的能力，每条给真实入口。

    版式与全站统一：白卡网格 + 单色线性 SVG 图标（不用 emoji）。
    """
    base = cfg.base_url.rstrip("/")
    items = [
        (L.ICON_SPORTS, "每日赛事前瞻", "每日 AI 报告列表，逐日归档可回溯", f"{base}/preview/"),
        (L.ICON_ARCHIVE, "历史归档", "逐日归档，历史结论可回溯比对", f"{base}/days/"),
        (L.ICON_SPORTS, "比赛列表", "按日浏览全部赛事，方向与比分旁边就是赛果", f"{base}/matches.html"),
        (L.ICON_SEARCH, "站内搜索", "按队名、联赛、编号检索历史赛事", f"{base}/search.html"),
        (L.ICON_ACTIVITY, "深度数据", "各联赛球队六维战力、赔率与让球走势", f"{base}/depth/"),
        (L.ICON_TREND, "赔率", "竞彩赔率快照按日浏览，完赛场次附赛果对照", f"{base}/odds.html"),
        (L.ICON_CPU, "投注", "投注记录本地留存，赛果自动结算与盈亏统计", f"{base}/bets.html"),
        (L.ICON_CPU, "机器可读数据", "llms.txt / dataset.json，供 LLM 与工具直接消费", f"{base}/llms.txt"),
    ]
    cards = "".join(
        f'<a class="feat-item" href="{url}">'
        f'<span class="feat-ico">{ico}</span>'
        f'<span class="feat-txt"><span class="feat-name">{name}</span>'
        f'<span class="feat-desc">{desc}</span>'
        f'<span class="feat-go">进入 →</span></span></a>'
        for ico, name, desc, url in items
    )
    body = f"<h1 class='page-h1'>{L.ICON_FUNCT} 功能</h1><div class='feat-grid'>{cards}</div>"
    return L.page(
        cfg, title="功能", description="站点功能清单：每日前瞻、历史归档、赛事Top、站内搜索、机器可读数据",
        body=body, canonical=f"{base}/features.html", depth=0,
    )


def render_me(cfg: Config) -> str:
    """👤我的：会员中心占位。功能未上线，如实说明。"""
    base = cfg.base_url.rstrip("/")
    body = (
        f"<h1 class='page-h1'>{L.ICON_USER} 我的</h1>"
        '<div class="me-card">'
        f'<div class="me-avatar">{L.ICON_USER}</div>'
        "<h2>会员中心</h2>"
        '<p class="sub">个性化功能（订阅、收藏、推送）正在开发中，敬请期待。</p>'
        '<p class="sub">当前无需登录，全部数据免费开放浏览。</p>'
        "</div>"
    )
    return L.page(
        cfg, title="我的", description="会员中心占位页：个性化功能开发中",
        body=body, canonical=f"{base}/me.html", depth=0,
    )


def render_search(cfg: Config, days: list[Day]) -> str:
    """🔍搜索：内嵌全量比赛摘要 + 前端过滤。静态站无后端，JS 只做检索。"""
    import json as _json

    base = cfg.base_url.rstrip("/")
    items = [
        [d.date, m.code or "", m.competition or "", m.home.name, m.away.name, m.match_id]
        for d in days for m in d.matches
    ]
    data_js = _json.dumps(items, ensure_ascii=False, separators=(",", ":"))
    body = (
        f"<h1 class='page-h1'>{L.ICON_SEARCH} 站内搜索</h1>"
        f"""<div class="search-page-box">
<form class="site-search-form" action="search.html" method="get">
  <input class="search-input" id="q" name="q" type="text" placeholder="输入队名 / 联赛 / 编号，如：拜仁、欧冠、周三004">
  <button class="search-btn" type="submit">搜索</button>
</form>
<p class="sub" id="search-meta"></p>
<div id="search-results" class="cards"></div>
</div>
<script>
(function () {{
  var DATA = {data_js};
  var q = new URLSearchParams(location.search).get("q") || "";
  document.getElementById("q").value = q;
  var box = document.getElementById("search-results");
  var meta = document.getElementById("search-meta");
  if (!q.trim()) {{ meta.textContent = "输入关键字开始检索，支持队名、联赛、竞彩编号与日期。"; return; }}
  var kw = q.trim().toLowerCase();
  var hits = DATA.filter(function (r) {{
    return r.some(function (v, i) {{ return i !== 5 && String(v).toLowerCase().indexOf(kw) !== -1; }});
  }}).slice(0, 50);
  meta.textContent = "共 " + hits.length + " 场匹配（最多显示 50 条）";
  if (!hits.length) {{ box.innerHTML = '<p class="sub">没有匹配的赛事，换个关键字试试。</p>'; return; }}
  box.innerHTML = hits.map(function (r) {{
    return '<a class="match-card" href="' + "matches/" + r[5] + '.html">'
      + '<div class="mc-header"><div class="mc-meta"><span class="date">' + r[0].slice(5).replace("-", "/")
      + '</span><span class="league">' + r[2] + '</span><span class="num">' + r[1] + '</span></div></div>'
      + '<div class="mc-body"><div class="mc-teams"><div class="mc-team"><span>' + r[3]
      + '</span></div><div class="mc-score"><div class="vs">VS</div></div><div class="mc-team"><span>' + r[4]
      + "</span></div></div></div></a>";
  }}).join("");
}})();
</script>"""
    )
    return L.page(
        cfg, title="站内搜索", description="按队名、联赛、竞彩编号检索全部历史赛事",
        body=body, canonical=f"{base}/search.html", depth=0,
    )


# ---------------------------------------------------------------- 赔率 / 投注


def _odds_payload(ordered: list[Day]) -> tuple[list, list]:
    """全玩法赔率数据集：(倒序日期表, 场次行)。只收带 extras.odds_full 的场次。

    行内含赛果数字（未开赛为 null），赔率页用于对照高亮、投注页用于自动结算。
    """
    import re as _re

    rows = []
    for d in ordered:
        for m in d.matches:
            of = (m.extras or {}).get("odds_full")
            if not of:
                continue
            gh = ga = hh = ha = None
            res = m.result
            if res and res.full_score:
                parts = _re.split(r"[:\-]", str(res.full_score).strip())
                if len(parts) == 2:
                    try:
                        gh, ga = int(parts[0]), int(parts[1])
                    except ValueError:
                        gh = ga = None
                if res.half_score:
                    hp = _re.split(r"[:\-]", str(res.half_score).strip())
                    if len(hp) == 2:
                        try:
                            hh, ha = int(hp[0]), int(hp[1])
                        except ValueError:
                            hh = ha = None
            rows.append({
                "d": d.date, "id": m.match_id, "c": m.code or "",
                "lg": m.competition or "", "h": m.home.name, "a": m.away.name,
                "tm": (m.kickoff or "")[-5:],
                "gh": gh, "ga": ga, "hh": hh, "ha": ha, "of": of,
            })
    rows.reverse()
    dates: list[str] = []
    for r in rows:
        if r["d"] not in dates:
            dates.append(r["d"])
    return dates, rows


def render_odds(cfg: Config, ordered: list[Day]) -> str:
    """📈盘口：竞彩全玩法赔率快照（胜平负/让球/比分/总进球/半全场）。

    版式对照原工具「赔率管理」：每场一卡、分区药丸（标签+数值），已完赛
    场次高亮命中项；数据 = jinbet/odds_data.json（经导入回填 extras.odds_full）。
    """
    import json as _json

    base = cfg.base_url.rstrip("/")
    dates, rows = _odds_payload(ordered)
    data_js = _json.dumps({"dates": dates, "rows": rows},
                          ensure_ascii=False, separators=(",", ":"))
    body = (
        f"<h1 class='page-h1'>{L.ICON_TREND} 赔率</h1>"
        '<input type="date" class="date-cal" id="odds-dates" data-mode="odds" '
        f'value="{dates[0]}" min="{min(dates)}" max="{max(dates)}" '
        f"data-dates='{_json.dumps(dates, separators=(',', ':'))}'>"
        '<div id="odds-out"></div>'
        "<script>\n(function () {\n"
        f"  var DATA = {data_js};\n"
        '''  var out = document.getElementById("odds-out");
  if (!DATA.dates.length) { out.innerHTML = '<p class="sub">暂无盘口数据。</p>'; return; }
  function pill(lab, val, hit, cls) {
    if (val === undefined || val === null || val === "") return "";
    return '<span class="odds-pill' + (hit ? " hit" : "") + '"><b class="' + (cls || "") + '">'
      + lab + "</b><i>" + val + "</i></span>";
  }
  function sec(title, inner) {
    if (!inner) return "";
    return '<div class="odds-sec"><div class="odds-sec-t">' + title + '</div><div class="odds-pills">' + inner + "</div></div>";
  }
  function render(d) {
    var rows = DATA.rows.filter(function (r) { return r.d === d; });
    var html = "";
    rows.forEach(function (r) {
      var of = r.of, done = r.gh !== null && r.gh !== undefined;
      var head = '<div class="odds-m-head">'
        + (r.c ? '<span class="odds-code">' + r.c + "</span>" : "")
        + (r.tm ? '<span class="odds-time">' + r.tm + "</span>" : "")
        + (r.lg ? '<span class="odds-lg">' + r.lg + "</span>" : "")
        + '<span class="odds-vs"><a href="matches/' + r.id + '.html"><b>' + r.h + "</b><i>VS</i><b>" + r.a + "</b></a></span>"
        + (done ? '<span class="odds-res">赛果 ' + r.gh + "-" + r.ga
          + (r.hh !== null && r.hh !== undefined ? " (半 " + r.hh + "-" + r.ha + ")" : "") + "</span>" : "")
        + "</div>";
      // 胜平负
      var w = done ? (r.gh > r.ga ? "胜" : r.gh < r.ga ? "负" : "平") : null;
      var s = pill("胜", of.spf && of.spf["胜"], w === "胜", "s-h")
        + pill("平", of.spf && of.spf["平"], w === "平", "s-d")
        + pill("负", of.spf && of.spf["负"], w === "负", "s-a");
      html += '<section class="odds-match">' + head + sec("胜平负", s);
      // 让球（多行；走水行不高亮）
      var rq = "";
      (of.rq || []).forEach(function (row) {
        var line = parseFloat(row.handicap), rw = null;
        if (done && line === line) {
          var adj = r.gh + line;
          rw = adj > r.ga ? "胜" : adj < r.ga ? "负" : "平";
        }
        rq += '<span class="rq-tag">让球' + row.handicap + "</span>"
          + pill("胜", row["胜"], rw === "胜", "s-h")
          + pill("平", row["平"], rw === "平", "s-d")
          + pill("负", row["负"], rw === "负", "s-a");
      });
      html += sec("让球", rq);
      // 比分：胜比分 / 平比分 / 负比分 三组分行（网易布局）
      function scoreGroup(k) {
        var mm = k.match(/^(\\d+):(\\d+)$/);
        if (mm) { var x = +mm[1], y = +mm[2]; return x > y ? "h" : x < y ? "a" : "d"; }
        return k.indexOf("胜") >= 0 ? "h" : k.indexOf("平") >= 0 ? "d" : k.indexOf("负") >= 0 ? "a" : "d";
      }
      var scG = {h: [], d: [], a: []};
      Object.keys(of.score || {}).forEach(function (k) {
        if (of.score[k]) scG[scoreGroup(k)].push(k);
      });
      var scT = {h: "胜比分", d: "平比分", a: "负比分"};
      ["h", "d", "a"].forEach(function (gk) {
        var s = "";
        scG[gk].forEach(function (k) {
          var v = of.score[k], hit = false, cls = gk === "h" ? "s-h" : gk === "a" ? "s-a" : "s-d";
          var mm = k.match(/^(\\d+):(\\d+)$/);
          if (mm) hit = done && r.gh === +mm[1] && r.ga === +mm[2];
          s += pill(k, v, hit, cls);
        });
        if (s) html += sec(scT[gk], s);
      });
      // 总进球
      var gl = "", tg = done ? r.gh + r.ga : null;
      Object.keys(of.goals || {}).forEach(function (k) {
        var hit = false;
        if (tg !== null) hit = k === "7+" ? tg >= 7 : +k === tg;
        gl += pill(k, of.goals[k], hit, "");
      });
      html += sec("总进球", gl);
      // 半全场（胜胜…负负）
      var ht = "", hr = done ? (r.hh > r.ha ? "胜" : r.hh < r.ha ? "负" : "平") : null;
      var fr = done ? w : null;
      Object.keys(of.htft || {}).forEach(function (k) {
        ht += pill(k, of.htft[k], done && k === hr + fr, "");
      });
      html += sec("半全场", ht) + "</section>";
    });
    out.innerHTML = html || '<p class="sub">当日无盘口数据。</p>';
  }
  window.renderOddsDay = render; // 日历控件 change 时由全局 JS 调用
  render(DATA.dates[0]);
})();
</script>'''
    )
    return L.page(
        cfg, title="赔率", description="竞彩全玩法赔率快照：胜平负、让球、比分、总进球、半全场，完赛对照高亮",
        body=body, canonical=f"{base}/odds.html", depth=0,
    )


def render_bets(cfg: Config, ordered: list[Day]) -> str:
    """🎯记录本：赛程区照网易彩票竞彩页重做（赔率格点选 + 投注篮）。

    左侧按日历日期列出当日场次：编号/联赛徽章/开赛时间/对阵 + 胜平负与
    让球赔率格（点击选号，选中红底高亮；胜平负/让球同玩法单选，比分/总
    进球/半全场可多选）+「更多玩法」展开让球其余盘口/比分/总进球/半全场；
    右侧 sticky 投注篮：已选清单可删、过关方式 chips（场数不足自动禁用）、
    倍数 −/+、人员与倍数，实时算注数/金额/预计奖金区间后保存为投注票。
    下方沿用记录区：统计卡、个人汇总、载入赛果自动结算（五玩法判定与
    组合逻辑同原工具足彩记录）。记录存浏览器 localStorage。
    """
    import json as _json

    base = cfg.base_url.rstrip("/")
    dates, rows = _odds_payload(ordered)
    data_js = _json.dumps({"dates": dates, "rows": rows},
                          ensure_ascii=False, separators=(",", ":"))
    person_opts = "ABCDEF"
    body = (
        f"<h1 class='page-h1'>{L.ICON_ACTIVITY} 投注</h1>"
        '<div class="bets-stats" id="bk-stats"></div>'
        '<div class="bets-card"><h3>📊 投注汇总</h3><div id="bk-person"></div></div>'
        '<div class="nb-layout">'
        '<div class="nb-main">'
        '<div class="nb-topbar">'
        + _date_input(dates, dates[0] if dates else "", "bets")
        + '<span class="nb-day" id="nb-day"></span>'
        '<span class="nb-count" id="nb-count"></span>'
        "</div>"
        '<div id="nb-list"></div>'
        "</div>"
        '<div class="nb-basket">'
        '<div class="nb-bk-t">已选 <span class="sub" id="nb-bk-n"></span>'
        '<a class="nb-bk-clear" id="nb-clear">清空</a></div>'
        '<div class="nb-bk-list" id="nb-bk-list"></div>'
        '<div class="nb-lab">过关方式</div>'
        '<div class="nb-pass" id="nb-pass"></div>'
        '<div class="nb-mult">倍数 '
        '<button type="button" id="nb-minus">−</button>'
        '<input id="nb-mult" type="number" value="1" min="1" step="1">'
        '<button type="button" id="nb-plus">＋</button></div>'
        '<div class="nb-pers">'
        '<div id="bk-persons" class="bf-persons"></div>'
        '<div class="bf-addperson"><select id="bk-psel"><option value="">— 人员 —</option>'
        + "".join(f"<option>{p}</option>" for p in person_opts)
        + '<option value="__c__">自定义</option></select>'
        '<input id="bk-pname" placeholder="名称" style="display:none;width:70px">'
        '<input id="bk-pmult" type="number" value="1" min="0" step="any" style="width:60px">'
        '<button id="bk-padd" type="button" class="bt-mini">添加</button></div>'
        "</div>"
        '<div class="nb-sum"><span>注数</span><b id="nb-n">0</b></div>'
        '<div class="nb-sum"><span>金额(元)</span><b id="nb-amt">0</b></div>'
        '<div class="nb-prize"><span>预计奖金(元)</span><b id="nb-prize">0.00</b></div>'
        '<button class="nb-save" id="nb-save" type="button">保 存</button>'
        '<div class="nb-msg" id="nb-msg"></div>'
        "</div>"
        "</div>"
        '<div class="bets-actions"><button id="bk-loadres" type="button" class="bt-go">⇩ 载入赛果并结算</button>'
        '<span id="bk-loadres-msg" class="sub"></span></div>'
        '<div class="bets-card"><h3>✏️ 自定义赛果结算（站内未回填时手动闭环）</h3>'
        '<div class="cr-bar">'
        + _date_input(dates, dates[0] if dates else "", "bets")
        + '<button id="cr-load" type="button" class="bt-mini">📅 载入当日比赛</button>'
        '<button id="cr-save" type="button" class="bt-go">💾 保存自定义赛果并结算</button>'
        '<a class="nb-bk-clear" id="cr-clear">清空</a>'
        '<span id="cr-msg" class="sub"></span>'
        "</div>"
        '<div id="cr-list" class="cr-list"><p class="sub">默认不显示。点「📅 载入当日比赛」拉取场次后手动填写比分。</p></div></div>'
        '<div class="bets-filter"><label>🔍 状态筛选：</label>'
        '<select id="bk-st"><option value="all">全部</option>'
        '<option value="pending">⏳ 待开奖</option><option value="win">✅ 中奖</option>'
        '<option value="lose">❌ 未中奖</option></select></div>'
        '<div class="bets-twrap"><table class="bets-table"><thead><tr>'
        "<th>#</th><th>场次详情</th><th>过关方式</th><th>注数</th><th>总倍数</th>"
        "<th>预计中奖(元)</th><th>投注(元)</th><th>中奖(元)</th><th>状态</th><th>操作</th>"
        '</tr></thead><tbody id="bk-tbody"></tbody></table></div>'
        '<p class="bets-foot">记录保存在本浏览器；赛果由站内已回填数据自动结算。</p>'
        "<script>\n(function () {\n"
        f"  var DATA = {data_js};\n"
        '''  var $ = function (id) { return document.getElementById(id); };
  function esc(s) { return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;"); }
  var LS = "matlas_tickets_v1";
  var MK_ZH = { spf: "胜平负", rq: "让球", goals: "总进球", score: "比分", htft: "半全场" };
  var MODES = ["单关", "2关", "3关", "4关", "5关", "6关", "7关", "8关"];
  var IDX = {};
  DATA.rows.forEach(function (r) { IDX[r.id] = r; });

  // ---- 存储与结算（同原工具足彩记录） ----
  function load() { try { return JSON.parse(localStorage.getItem(LS)) || []; } catch (e) { return []; } }
  function save(t) { localStorage.setItem(LS, JSON.stringify(t)); render(); }
  function legRes(p, row) {
    if (!row || row.gh === null || row.gh === undefined) return "pending";
    var gh = row.gh, ga = row.ga;
    if (p.mk === "spf") return p.opt === (gh > ga ? "胜" : gh < ga ? "负" : "平") ? "win" : "lose";
    if (p.mk === "rq") {
      var adj = gh + p.line;
      return p.pick === (adj > ga ? "胜" : adj < ga ? "负" : "平") ? "win" : "lose";
    }
    if (p.mk === "goals") { var t2 = gh + ga; return (p.opt === "7+" ? t2 >= 7 : +p.opt === t2) ? "win" : "lose"; }
    if (p.mk === "score") return p.opt === gh + ":" + ga ? "win" : "lose";
    if (p.mk === "htft") {
      if (row.hh === null || row.hh === undefined) return "pending";
      var h = row.hh > row.ha ? "胜" : row.hh < row.ha ? "负" : "平";
      var f = gh > ga ? "胜" : gh < ga ? "负" : "平";
      return p.opt === h + f ? "win" : "lose";
    }
    return "lose";
  }
  function kOf(mode) { return mode === "单关" ? 1 : +mode.charAt(0); }
  function combosOf(t) {
    var out = [];
    (t.passModes || []).forEach(function (mode) {
      var k = kOf(mode);
      var idxs = t.games.map(function (_, i) { return i; });
      function comb(start, acc) {
        if (acc.length === k) {
          function prod(i, accP) {
            if (i === acc.length) { out.push({ sp: accP.reduce(function (a, p) { return a * p.odds; }, 1), legs: accP.slice(), mode: mode }); return; }
            var gm = t.games[acc[i]];
            gm.picks.forEach(function (p) {
              var pc = {}; for (var key in p) pc[key] = p[key];
              pc.mid = gm.mid; // 腿上补 mid，结算时才能按场次查赛果
              accP.push(pc); prod(i + 1, accP); accP.pop();
            });
          }
          prod(0, []);
          return;
        }
        for (var i = start; i < idxs.length; i++) { acc.push(idxs[i]); comb(i + 1, acc); acc.pop(); }
      }
      comb(0, []);
    });
    return out;
  }
  function settle(t) {
    var cs = combosOf(t);
    var winSp = 0, anyPending = false;
    cs.forEach(function (c) {
      var win = true;
      c.legs.forEach(function (p) {
        var r = legRes(p, rowOf(p.mid));
        if (r === "pending") { anyPending = true; win = false; }
        else if (r === "lose") win = false;
      });
      if (win) winSp += c.sp;
    });
    var mult = (t.persons || []).reduce(function (a, p) { return a + (+p.mult || 0); }, 0);
    var gm = t.gmult || 1;
    var winAmt = 2 * mult * gm * winSp;
    var status = winAmt > 0 ? "win" : anyPending ? "pending" : "lose";
    return { betCount: cs.length, winAmt: winAmt, status: status,
      spMin: cs.length ? Math.min.apply(null, cs.map(function (c) { return c.sp; })) : 0,
      spMax: cs.reduce(function (a, c) { return a + c.sp; }, 0) };
  }
  function lgCls(lg) {
    lg = lg || "";
    if (lg.indexOf("欧冠") >= 0) return "lg-ucl";
    if (lg.indexOf("欧罗巴") >= 0 || lg.indexOf("欧联") >= 0) return "lg-uel";
    if (lg.indexOf("欧协") >= 0) return "lg-uecl";
    if (lg.indexOf("解放者") >= 0) return "lg-lib";
    if (lg.indexOf("日职") >= 0) return "lg-j1";
    if (lg.indexOf("英超") >= 0) return "lg-epl";
    var h = 0;
    for (var i = 0; i < lg.length; i++) h = (h * 31 + lg.charCodeAt(i)) % 5;
    return "lg-c" + h;
  }
  function pickName(p) { return p.mk === "rq" ? "让球(" + p.line + ") " + p.pick : MK_ZH[p.mk] + " " + p.opt; }
  function codeNum(c) {
    c = String(c || "");
    var n = 0;
    for (var i = 0; i < c.length; i++) {
      var ch = c.charAt(i);
      if (ch >= "0" && ch <= "9") n = n * 10 + (+ch);
    }
    return n;
  }
  // ---- 自定义赛果（手动闭环）：存 localStorage，优先于站内赛果 ----
  var CRS = {};
  try { CRS = JSON.parse(localStorage.getItem("matlas_custom_results_v1")) || {}; } catch (e) { CRS = {}; }
  function saveCRS() { localStorage.setItem("matlas_custom_results_v1", JSON.stringify(CRS)); }
  function rowOf(mid) {
    var r = IDX[mid], c = CRS[mid];
    if (c && c.gh !== undefined && c.gh !== null && c.gh !== "") {
      var m = Object.assign({}, r || {}, c);
      m.custom = true;
      return m;
    }
    return r;
  }

  // ===== 选号区：场次列表 + 赔率格点选 =====
  var picks = {}; // "mid|mk|opt" -> {mid, mk, opt, odds, line, pick}
  function pKey(p) { return p.mid + "|" + p.mk + "|" + p.opt; }
  function snapD(v) {
    if (DATA.dates.indexOf(v) >= 0) return v;
    var prev = null, next = null;
    DATA.dates.forEach(function (d) {
      if (d < v && (prev === null || d > prev)) prev = d;
      if (d > v && (next === null || d < next)) next = d;
    });
    return prev || next || v;
  }
  var cal = document.querySelector(".nb-topbar .date-cal");
  if (cal) cal.addEventListener("change", function () {
    var t = snapD(this.value); this.value = t; renderMatches(t);
  });
  function dayWk(d) {
    try { return "周" + "日一二三四五六".charAt(new Date(d + "T12:00:00").getDay()); } catch (e) { return ""; }
  }
  function cell(mid, mk, opt, odds, line, pick) {
    var cls = picks[mid + "|" + mk + "|" + opt] ? " on" : "";
    var a = '<a class="nb-cell' + cls + '" data-mid="' + mid + '" data-mk="' + mk + '" data-opt="' + esc(opt) + '"';
    if (odds !== undefined && odds !== null) a += ' data-odds="' + odds + '"';
    if (line !== undefined && line !== null) a += ' data-line="' + line + '" data-pick="' + esc(pick || "") + '"';
    return a + "><b>" + esc(pick || opt) + "</b><i>"
      + (odds !== undefined && odds !== null ? (+odds).toFixed(2) : "-") + "</i></a>";
  }
  function threeCells(mid, mk, row, withLine) {
    var s = "";
    ["胜", "平", "负"].forEach(function (w) {
      if (row[w]) s += cell(mid, mk, withLine ? "让" + row.handicap + " " + w : w, row[w],
        withLine ? parseFloat(row.handicap) : null, w);
    });
    return s;
  }
  function renderMatches(d) {
    var list = DATA.rows.filter(function (r) { return r.d === d; })
      .sort(function (a, b) { return codeNum(a.c) - codeNum(b.c); });
    $("nb-day").textContent = d + " " + dayWk(d);
    $("nb-count").textContent = list.length + "场比赛";
    if (!list.length) { $("nb-list").innerHTML = '<p class="sub">当日无盘口数据。</p>'; return; }
    var html = "";
    list.forEach(function (r, i) {
      var of = r.of, done = r.gh !== null && r.gh !== undefined;
      var head = '<div class="nb-mrow">'
        + '<div class="nb-mleft"><span class="nb-code">' + esc(r.c) + "</span>"
        + '<button type="button" class="nb-more" data-i="' + i + '">更多玩法 ▾</button></div>'
        + '<span class="bf-lg ' + lgCls(r.lg) + '">' + esc(r.lg) + "</span>"
        + '<span class="nb-time">' + esc(r.tm || "") + "</span>"
        + '<span class="nb-vs"><b>' + esc(r.h) + "</b><i>VS</i><b>" + esc(r.a) + "</b></span>"
        + (done ? '<span class="nb-done">赛果 ' + r.gh + "-" + r.ga + "</span>" : "");
      var plays = '<div class="nb-plays">'
        + '<div class="nb-blk"><span class="nb-blk-t">胜平负</span><div class="nb-cells">'
        + threeCells(r.id, "spf", of.spf || {}, false) + "</div></div>";
      if ((of.rq || []).length) {
        plays += '<div class="nb-blk"><span class="nb-blk-t">让球' + of.rq[0].handicap
          + '</span><div class="nb-cells">' + threeCells(r.id, "rq", of.rq[0], true) + "</div></div>";
      }
      head += plays + "</div>";
      head += "</div>";
      var ex = "";
      (of.rq || []).slice(1).forEach(function (row) {
        ex += '<div class="nb-ex-sec"><span class="nb-ex-t">让球' + row.handicap
          + '</span><div class="nb-cells">' + threeCells(r.id, "rq", row, true) + "</div></div>";
      });
      function kvSec(title, src, mk) {
        var s = "";
        Object.keys(src || {}).forEach(function (k) { if (src[k]) s += cell(r.id, mk, k, src[k]); });
        return s ? '<div class="nb-ex-sec"><span class="nb-ex-t">' + title
          + '</span><div class="nb-cells">' + s + "</div></div>" : "";
      }
      function scoreSecs(src, mk) {
        // 比分按 胜/平/负 三组分行（网易布局）
        var g = {h: [], d: [], a: []};
        Object.keys(src || {}).forEach(function (k) {
          if (!src[k]) return;
          var mm = k.match(/^(\\d+):(\\d+)$/);
          var grp;
          if (mm) { var x = +mm[1], y = +mm[2]; grp = x > y ? "h" : x < y ? "a" : "d"; }
          else grp = k.indexOf("胜") >= 0 ? "h" : k.indexOf("平") >= 0 ? "d" : "a";
          g[grp].push(k);
        });
        var t = {h: "胜比分", d: "平比分", a: "负比分"};
        return ["h", "d", "a"].map(function (gk) {
          if (!g[gk].length) return "";
          return '<div class="nb-ex-sec"><span class="nb-ex-t">' + t[gk]
            + '</span><div class="nb-cells">'
            + g[gk].map(function (kk) { return cell(r.id, mk, kk, src[kk]); }).join("")
            + "</div></div>";
        }).join("");
      }
      ex += scoreSecs(of.score, "score") + kvSec("总进球", of.goals, "goals") + kvSec("半全场", of.htft, "htft");
      html += '<div class="nb-match">' + head
        + '<div class="nb-ex" id="nb-ex-' + i + '" style="display:none">' + ex + "</div></div>";
    });
    $("nb-list").innerHTML = html;
  }
  function toggleCell(c) {
    var mid = c.getAttribute("data-mid"), mk = c.getAttribute("data-mk"), opt = c.getAttribute("data-opt");
    var od = c.getAttribute("data-odds");
    if (od === null) return;
    var key = mid + "|" + mk + "|" + opt;
    var had = !!picks[key];
    if (mk === "spf" || mk === "rq") {
      // 同玩法单选：先清掉该场该玩法的已选，再按需加入
      Object.keys(picks).forEach(function (k) { if (k.indexOf(mid + "|" + mk + "|") === 0) delete picks[k]; });
      if (!had) picks[key] = { mid: mid, mk: mk, opt: opt, odds: +od,
        line: c.getAttribute("data-line") !== null ? parseFloat(c.getAttribute("data-line")) : undefined,
        pick: c.getAttribute("data-pick") || undefined };
    } else if (had) delete picks[key];
    else picks[key] = { mid: mid, mk: mk, opt: opt, odds: +od };
    syncCells(); renderBasket();
  }
  function syncCells() {
    document.querySelectorAll("#nb-list .nb-cell").forEach(function (c) {
      c.classList.toggle("on", !!picks[c.getAttribute("data-mid") + "|" + c.getAttribute("data-mk") + "|" + c.getAttribute("data-opt")]);
    });
  }
  $("nb-list").addEventListener("click", function (e) {
    var c = e.target.closest(".nb-cell");
    if (c) { toggleCell(c); return; }
    var mb = e.target.closest(".nb-more");
    if (mb) {
      var ex = document.getElementById("nb-ex-" + mb.getAttribute("data-i"));
      if (ex) {
        var open = ex.style.display !== "none";
        ex.style.display = open ? "none" : "block";
        mb.textContent = open ? "更多玩法 ▾" : "收起 ▴";
      }
    }
  });

  // ===== 投注篮 =====
  function basketGames() {
    var by = {};
    Object.keys(picks).forEach(function (k) { var p = picks[k]; (by[p.mid] || (by[p.mid] = [])).push(p); });
    return DATA.rows.filter(function (r) { return by[r.id]; })
      .map(function (r) { return { mid: r.id, picks: by[r.id] }; });
  }
  var checkedModes = [];
  function validModes() { var n = basketGames().length; return checkedModes.filter(function (m) { return kOf(m) <= n; }); }
  function renderPass() {
    var n = basketGames().length;
    $("nb-pass").innerHTML = MODES.map(function (m) {
      var dis = !n || n < kOf(m);
      return '<label class="' + (dis ? "dis" : "") + '"><input type="checkbox" value="' + m + '"'
        + (checkedModes.indexOf(m) >= 0 ? " checked" : "") + ">" + m + "</label>";
    }).join("");
    $("nb-pass").querySelectorAll("input").forEach(function (x) {
      x.addEventListener("change", function () {
        if (x.checked) { if (checkedModes.indexOf(x.value) < 0) checkedModes.push(x.value); }
        else checkedModes = checkedModes.filter(function (mm) { return mm !== x.value; });
        updateSum();
      });
    });
  }
  function renderBasket() {
    var gs = basketGames(), items = [];
    gs.forEach(function (g) {
      var r = IDX[g.mid];
      g.picks.forEach(function (p) {
        items.push('<div class="nb-bk-item"><span class="m">' + esc(r ? r.c : "") + "</span>"
          + esc(pickName(p)) + '<span class="o">@' + (+p.odds).toFixed(2)
          + '</span><a data-k="' + esc(pKey(p)) + '" title="删除">✕</a></div>');
      });
    });
    $("nb-bk-list").innerHTML = items.join("") || '<div class="nb-bk-empty">点击左侧赔率格选号</div>';
    $("nb-bk-list").querySelectorAll("a[data-k]").forEach(function (a) {
      a.addEventListener("click", function () { delete picks[a.getAttribute("data-k")]; syncCells(); renderBasket(); });
    });
    $("nb-bk-n").textContent = gs.length ? "（" + gs.length + " 场）" : "";
    if (gs.length) {
      checkedModes = checkedModes.filter(function (m) { return kOf(m) <= gs.length; });
      if (!checkedModes.length) checkedModes.push(gs.length === 1 ? "单关" : Math.min(gs.length, 8) + "关");
    }
    renderPass();
    updateSum();
  }
  function updateSum() {
    var gs = basketGames(), modes = validModes();
    var mult = Math.max(1, Math.round(+$("nb-mult").value || 1));
    // 人员倍数：每人一份票，注数与金额同步放大（无人员时按 1 份展示）
    var psum = persons.reduce(function (a, p) { return a + (+p.mult || 0); }, 0);
    var factor = persons.length ? psum : 1;
    var n = 0, spMin = 0, spMax = 0;
    if (gs.length && modes.length) {
      var cs = combosOf({ passModes: modes, games: gs });
      n = cs.length;
      if (n) {
        spMin = Math.min.apply(null, cs.map(function (c) { return c.sp; }));
        spMax = cs.reduce(function (a, c) { return a + c.sp; }, 0);
      }
    }
    var nShow = n * factor;
    $("nb-n").textContent = nShow;
    $("nb-amt").textContent = (2 * factor * mult * n).toFixed(0);
    $("nb-prize").textContent = n ? (2 * factor * mult * spMin).toFixed(2) + " ~ " + (2 * factor * mult * spMax).toFixed(2) : "0.00";
  }
  $("nb-minus").addEventListener("click", function () {
    $("nb-mult").value = Math.max(1, Math.round(+$("nb-mult").value || 1) - 1); updateSum();
  });
  $("nb-plus").addEventListener("click", function () {
    $("nb-mult").value = Math.round(+$("nb-mult").value || 1) + 1; updateSum();
  });
  $("nb-mult").addEventListener("change", updateSum);
  $("nb-clear").addEventListener("click", function () { picks = {}; checkedModes = []; syncCells(); renderBasket(); });

  // ---- 人员与倍数 ----
  var persons = [];
  function renderPersons() {
    $("bk-persons").innerHTML = persons.map(function (p, i) {
      return '<span class="bf-person">' + esc(p.name) + ' × <input type="number" value="' + p.mult
        + '" min="0" step="any" data-i="' + i + '" class="bf-pmult"> <a class="bf-pdel" data-i="' + i + '">✕</a></span>';
    }).join("") || '<span class="sub">尚未添加人员</span>';
    $("bk-persons").querySelectorAll(".bf-pdel").forEach(function (a) {
      a.addEventListener("click", function () { persons.splice(+a.getAttribute("data-i"), 1); renderPersons(); });    });
    $("bk-persons").querySelectorAll(".bf-pmult").forEach(function (inp) {
      inp.addEventListener("change", function () { persons[+inp.getAttribute("data-i")].mult = +inp.value || 0; updateSum(); });
    });
    updateSum();
  }
  $("bk-psel").addEventListener("change", function () {
    var v = this.value;
    $("bk-pname").style.display = v === "__c__" ? "" : "none";
  });
  $("bk-padd").addEventListener("click", function () {
    var v = $("bk-psel").value;
    if (!v) return;
    var name = v === "__c__" ? ($("bk-pname").value || "自定义").trim() : v;
    if (name && !persons.some(function (p) { return p.name === name; })) persons.push({ name: name, mult: +$("bk-pmult").value || 0 });
    $("bk-pname").value = ""; renderPersons();
  });

  // ---- 保存投注票 ----
  $("nb-save").addEventListener("click", function () {
    var gs = basketGames(), modes = validModes();
    var bad = [];
    if (!modes.length) bad.push("过关方式");
    if (!persons.length) bad.push("人员");
    if (!gs.length) bad.push("选号");
    var msg = $("nb-msg");
    if (bad.length) { msg.style.color = "#dc2626"; msg.textContent = "请补全：" + bad.join("、"); return; }
    var t = { ts: Date.now(), passModes: modes, persons: persons.slice(),
      gmult: Math.max(1, Math.round(+$("nb-mult").value || 1)),
      games: JSON.parse(JSON.stringify(gs)) };
    var all = load(); all.unshift(t); save(all);
    picks = {}; checkedModes = []; syncCells(); renderBasket();
    var psum = (t.persons || []).reduce(function (a, p) { return a + (+p.mult || 0); }, 0);
    msg.style.color = "#16a34a";
    msg.textContent = "✅ 已保存 " + t.gmult + " 倍 × " + (t.persons.length ? psum : 1) + " 份，共 "
      + (combosOf(t).length * (t.persons.length ? psum : 1)) + " 注，见下方记录";
  });

  // ---- 📥 载入赛果并结算（按场次匹配站内赛果 → 逐腿判定 → 重算全部票） ----
  $("bk-loadres").addEventListener("click", function () {
    var ts = load(), matched = 0, tickets = 0;
    ts.forEach(function (t) {
      var touched = false;
      t.games.forEach(function (g) {
        var r = rowOf(g.mid);
        if (r && r.gh !== null && r.gh !== undefined) {
          g.result = r.gh + "-" + r.ga;
          g.resHalf = (r.hh !== null && r.hh !== undefined) ? r.hh + "-" + r.ha : "";
          g.isWin = (g.picks || []).some(function (p) { return legRes(p, r) === "win"; });
          matched += 1; touched = true;
        } else { g.result = ""; g.isWin = null; }
      });
      if (touched) tickets += 1;
    });
    localStorage.setItem(LS, JSON.stringify(ts));
    render();
    $("bk-loadres-msg").textContent = tickets
      ? "✅ 已为 " + tickets + " 票匹配 " + matched + " 场赛果并重新结算"
      : "暂无已保存的票";
  });

  // ---- ✏️ 自定义赛果：载入当日比赛 → 手填比分 → 保存即结算（站内未回填时的闭环） ----
  var crDate = document.querySelector(".cr-bar .date-cal");
  if (crDate) crDate.addEventListener("change", function () { this.value = snapD(this.value); });
  function renderCR() {
    if (!crDate) return;
    var d = crDate.value;
    var list = DATA.rows.filter(function (r) { return r.d === d; })
      .sort(function (a, b) { return codeNum(a.c) - codeNum(b.c); });
    if (!list.length) { $("cr-list").innerHTML = '<p class="sub">当日无比赛数据。</p>'; return; }
    $("cr-list").innerHTML = list.map(function (r) {
      var c = CRS[r.id] || {};
      var site = r.gh !== null && r.gh !== undefined;
      function v(k, siteVal) {
        if (c[k] !== undefined && c[k] !== null) return c[k];
        return site && siteVal !== null && siteVal !== undefined ? siteVal : "";
      }
      return '<div class="cr-row" data-mid="' + r.id + '">'
        + '<span class="nb-code">' + esc(r.c) + "</span>"
        + '<span class="bf-lg ' + lgCls(r.lg) + '">' + esc(r.lg) + "</span>"
        + '<span class="cr-vs"><b>' + esc(r.h) + "</b><i>VS</i><b>" + esc(r.a) + "</b></span>"
        + '<span class="cr-in">全场 <input class="cr-n" data-k="gh" value="' + v("gh", r.gh) + '">:<input class="cr-n" data-k="ga" value="' + v("ga", r.ga) + '"></span>'
        + '<span class="cr-in">半场 <input class="cr-n" data-k="hh" value="' + v("hh", r.hh) + '">:<input class="cr-n" data-k="ha" value="' + v("ha", r.ha) + '"></span>'
        + (site ? '<span class="cr-site">站内 ' + r.gh + "-" + r.ga + "</span>"
                : '<span class="cr-site cr-none">站内暂无</span>')
        + "</div>";
    }).join("");
  }
  $("cr-load").addEventListener("click", renderCR);
  function crSettleAll() {
    var games = 0;
    var ts = load();
    ts.forEach(function (t) {
      t.games.forEach(function (g) {
        var r = rowOf(g.mid);
        if (r && r.gh !== null && r.gh !== undefined) {
          g.result = r.gh + "-" + r.ga;
          g.resHalf = (r.hh !== null && r.hh !== undefined) ? r.hh + "-" + r.ha : "";
          g.isWin = (g.picks || []).some(function (p) { return legRes(p, r) === "win"; });
          games += 1;
        }
      });
    });
    localStorage.setItem(LS, JSON.stringify(ts));
    render();
    return games;
  }
  $("cr-save").addEventListener("click", function () {
    var n = 0;
    $("cr-list").querySelectorAll(".cr-row").forEach(function (row) {
      var mid = row.getAttribute("data-mid");
      var ins = row.querySelectorAll(".cr-n");
      function val(i) {
        var s = String(ins[i].value).trim();
        return s === "" ? null : (+s === +s ? +s : null);
      }
      var gh = val(0), ga = val(1), hh = val(2), ha = val(3);
      if (hh === null || ha === null) { hh = null; ha = null; }
      if (gh === null || ga === null) delete CRS[mid];
      else { CRS[mid] = { gh: gh, ga: ga, hh: hh, ha: ha }; n += 1; }
    });
    saveCRS();
    var games = crSettleAll();
    $("cr-msg").textContent = "✅ 已保存 " + n + " 场赛果并重新结算 " + games + " 场（自定义优先于站内）";
    renderCR();
  });
  $("cr-clear").addEventListener("click", function () {
    $("cr-list").innerHTML = '<p class="sub">默认不显示。点「📅 载入当日比赛」拉取场次后手动填写比分。</p>';
    $("cr-msg").textContent = "🗑 已清空载入的赛程";
  });

  // ---- 记录区：统计 / 个人汇总 / 明细表 ----
  function render() {
    var ts = load(), st = $("bk-st").value;
    var shown = ts.map(function (t) { return { t: t, s: settle(t) }; })
      .filter(function (x) { return st === "all" || x.s.status === st; });
    var totTickets = ts.length, totAmt = 0, totWin = 0, pending = 0;
    var byPerson = {};
    ts.forEach(function (t) {
      var s = settle(t);
      var mult = (t.persons || []).reduce(function (a, p) { return a + (+p.mult || 0); }, 0);
      var gm = t.gmult || 1;
      totAmt += 2 * mult * gm * s.betCount; totWin += s.winAmt;
      if (s.status === "pending") pending += 1;
      t.persons.forEach(function (p) {
        var b = byPerson[p.name] || (byPerson[p.name] = { amt: 0, win: 0, n: 0 });
        b.n += 1;
        b.amt += 2 * (+p.mult || 0) * gm * s.betCount;
        b.win += s.winAmt ? s.winAmt * (+p.mult || 0) / mult : 0;
      });
    });
    var pnl = totWin - totAmt;
    var badge = { win: '<span class="bt-chip bt-win">✅ 中奖</span>', lose: '<span class="bt-chip bt-lose">❌ 未中奖</span>', pending: '<span class="bt-chip bt-pending">⏳ 待开奖</span>' };
    $("bk-stats").innerHTML = ""
      + '<div class="stat-card"><div class="stat-num">' + totTickets + '</div><div class="stat-lbl">📋 总票数（待开 ' + pending + '）</div></div>'
      + '<div class="stat-card"><div class="stat-num">' + totAmt.toFixed(1) + '</div><div class="stat-lbl">💰 总投注(元)</div></div>'
      + '<div class="stat-card"><div class="stat-num">' + totWin.toFixed(1) + '</div><div class="stat-lbl">🏆 中奖(元)</div></div>'
      + '<div class="stat-card"><div class="stat-num ' + (pnl >= 0 ? "pnl-pos" : "pnl-neg") + '">' + (pnl >= 0 ? "+" : "") + pnl.toFixed(1) + '</div><div class="stat-lbl">📈 净收益(元)</div></div>';
    var pk = Object.keys(byPerson);
    $("bk-person").innerHTML = pk.length
      ? '<table class="bets-table bt-small"><thead><tr><th>人员</th><th>票数(张)</th><th>投注(元)</th><th>中奖(元)</th><th>净收益(元)</th></tr></thead><tbody>'
        + pk.map(function (k) {
          var b = byPerson[k], net = b.win - b.amt;
          return "<tr><td><b>" + esc(k) + "</b></td><td>" + b.n + "</td><td>" + b.amt.toFixed(1) + "</td><td>" + b.win.toFixed(1)
            + '</td><td class="' + (net >= 0 ? "pnl-pos" : "pnl-neg") + '">' + (net >= 0 ? "+" : "") + net.toFixed(1) + "</td></tr>";
        }).join("") + "</tbody></table>"
      : '<p class="sub">暂无记录。</p>';
    $("bk-tbody").innerHTML = shown.length ? shown.map(function (x, i) {
      var t = x.t, s = x.s;
      var mult = (t.persons || []).reduce(function (a, p) { return a + (+p.mult || 0); }, 0);
      var gm = t.gmult || 1;
      var detail = t.games.map(function (g) {
        var r = rowOf(g.mid);
        var done = r && r.gh !== null && r.gh !== undefined;
        var mark = "";
        if (done) {
          var win = (g.picks || []).some(function (p) { return legRes(p, r) === "win"; });
          mark = ' <b class="' + (win ? "hit-y" : "hit-n") + '">' + (win ? "✓" : "✗") + "</b> <span class='bf-res'>" + r.gh + "-" + r.ga + "</span>";
        }
        return (r ? r.c + " " : "") + g.picks.map(function (p) { return esc(pickName(p)); }).join("/") + mark;
      }).join("<br>");
      return "<tr><td>" + (i + 1) + "</td><td>" + detail + "</td><td>" + t.passModes.join("+") + "</td><td>"
        + (s.betCount * mult) + "</td><td>" + (mult * gm) + "</td><td>" + (2 * mult * gm * s.spMin).toFixed(2) + " ~ " + (2 * mult * gm * s.spMax).toFixed(2)
        + "</td><td>" + (2 * mult * gm * s.betCount).toFixed(1) + "</td><td>" + s.winAmt.toFixed(1) + "</td><td>"
        + badge[s.status] + '</td><td><a class="bt-del" data-ts="' + t.ts + '">删除</a></td></tr>';
    }).join("") : '<tr><td colspan="10"><p class="sub">暂无记录，在上方选号后点「保 存」。</p></td></tr>';
    $("bk-tbody").querySelectorAll(".bt-del").forEach(function (a) {
      a.addEventListener("click", function () {
        save(load().filter(function (x) { return String(x.ts) !== a.getAttribute("data-ts"); }));
      });
    });
  }
  $("bk-st").addEventListener("change", render);
  renderPersons();
  if (DATA.dates.length) renderMatches(DATA.dates[0]);
  renderBasket();
  render();
})();
</script>'''
    )
    return L.page(
        cfg, title="投注", description="足彩投注：竞彩式赔率格选号、投注篮计注算奖、载入赛果自动结算与个人盈亏汇总",
        body=body, canonical=f"{base}/bets.html", depth=0,
    )


def _lt_header(name: str, *, logo: str, meta: str, ph_char: str = "") -> str:
    """联赛/球队专题页头部（对齐对方 .lt-header：徽章 + 标题 + 统计行）。"""
    img = (
        f'<img class="lt-logo" src="../{C.esc(logo)}" alt="{C.esc(name)}徽标" loading="lazy">'
        if logo
        else f'<div class="lt-logo lt-logo-ph" aria-hidden="true">{C.esc(ph_char or name[:1])}</div>'
    )
    return (
        '<div class="lt-header">'
        f"{img}"
        f'<div><h1 class="lt-title">{C.esc(name)}</h1>'
        f'<div class="lt-meta">{meta}</div></div>'
        "</div>"
    )


def render_league(cfg: Config, league: str, matches: list[Match],
                  stats: tuple[int, int] | None = None) -> str:
    """联赛专题页：头部（徽章+标题+统计）+ 该联赛全部已收录场次列表。

    框架对齐对方 league-topic 页；列表与命中统计是我们自己的增量内容。
    """
    base = cfg.base_url.rstrip("/")
    ordered = sorted(matches, key=lambda m: (m.day, m.code or ""), reverse=True)
    cards = "".join(_card(cfg, m, pre="../") for m in ordered[:60]) or (
        '<p class="sub">该联赛暂无已收录场次。</p>'
    )
    hit, total = stats or (0, 0)
    acc = (hit / total * 100) if total else 0.0
    meta = (
        f"已收录 <b>{len(matches)}</b> 场 · 已结算 <b>{total}</b> 场 · "
        f'方向命中 <span class="pct"><b>{acc:.1f}%</b></span>'
        if total
        else f"已收录 <b>{len(matches)}</b> 场 · 赛果回填后自动统计命中率"
    )
    logo = logos.league_crest_url(league)
    body = (
        _lt_header(league, logo=logo, meta=meta)
        + f'<div class="cards">{cards}</div>'
    )
    return L.page(
        cfg, title=f"{league} 赛事专题", description=f"{league} 全部已收录场次的方向命中率与逐场分析",
        body=body, canonical=f"{base}/leagues/{league}.html", depth=1,
    )


def render_team(cfg: Config, team_name: str, matches: list[Match],
                stats: tuple[int, int] | None = None,
                board: dict | None = None) -> str:
    """球队专题页：六维战力 + 市场走势 + 该队全部已收录场次列表。"""
    base = cfg.base_url.rstrip("/")
    ordered = sorted(matches, key=lambda m: (m.day, m.code or ""), reverse=True)
    hit, total = stats or (0, 0)
    acc = (hit / total * 100) if total else 0.0
    meta = (
        f"已收录 <b>{len(matches)}</b> 场 · 已结算 <b>{total}</b> 场 · "
        f'方向命中 <span class="pct"><b>{acc:.1f}%</b></span>'
        if total
        else f"已收录 <b>{len(matches)}</b> 场 · 赛果回填后自动统计命中率"
    )
    logo = logos.crest_url(team_name)
    blocks = _team_depth_blocks(team_name, board or {}, ordered)
    cards = "".join(_card(cfg, m, pre="../") for m in ordered[:60]) or (
        '<p class="sub">该球队暂无已收录场次。</p>'
    )
    body = (
        _lt_header(team_name, logo=logo, meta=meta)
        + blocks
        + '<div class="cards">' + cards + "</div>"
    )
    return L.page(
        cfg, title=f"{team_name} 赛事专题", description=f"{team_name} 全部已收录场次的方向命中率与逐场分析",
        body=body, canonical=f"{base}/teams/{team_name}.html", depth=1,
    )


def _team_depth_blocks(team_name: str, b: dict, matches: list[Match]) -> str:
    """球队深度块：六维雷达 + 六轴数值 + 市场赔率/让球走势 + 近况。"""
    out = []
    met = b.get("metrics")
    if met:
        axes = [zh for _, zh in Metrics.AXES]
        vals = met.values()
        radar = C.radar_one(vals, axes, team_name, size=440)
        power = b.get("power")
        head = (f'<p class="sub">综合战力 <b>{power}</b> · 联赛内分位 0–100</p>'
                if power is not None else "")
        out.append(C.panel("六维战力", radar + head))

    series = b.get("series") or []
    if len(series) >= 2:
        pts = [{"label": s["date"][5:], "price": s.get("price"),
                "hcp": s.get("hcp"), "res": s.get("res")} for s in series]
        chart = C.odds_trend_svg(pts)
        if chart:
            rows = []
            for s in reversed(series):
                res = {"w": "胜", "d": "平", "l": "负"}[s["res"]]
                price = f'{s["price"]:g}' if s.get("price") else "—"
                hcp = f'{s["hcp"]:+g}' if isinstance(s.get("hcp"), (int, float)) else "—"
                rows.append([s["date"][5:], f'{s["opp"]}（{"主" if s["ha"] == "home" else "客"}）',
                             f'{s["gf"]}-{s["ga"]}', res, price, hcp])
            out.append(C.panel(
                "市场走势",
                chart + C.table(["日期", "对手", "比分", "结果", "获胜赔率", "让球"], rows),
            ))

    if b.get("recent"):
        rec = b["recent"]
        n = len(rec)
        res = [x["res"] for x in rec]
        line = (f'近 {n} 场 {res.count("w")}胜 {res.count("d")}平 {res.count("l")}负 · '
                f'场均进 {sum(x["gf"] for x in rec) / n:.2f} 失 {sum(x["ga"] for x in rec) / n:.2f}')
        out.append(C.panel("近期战绩", C.form_dots(res) + f'<p class="sub">{line}</p>'))
    return "".join(out)


def render_depth(cfg: Config, days: list[Day], board: dict[str, dict]) -> str:
    """深度数据：各联赛各球队六维战力总览，点卡片进球队页看走势。"""
    base = cfg.base_url.rstrip("/")
    axes = [zh for _, zh in Metrics.AXES]
    rows = [b for b in board.values() if b.get("metrics")]
    lg_count: dict[str, int] = {}
    for b in rows:
        lg_count[b["league"]] = lg_count.get(b["league"], 0) + 1
    zones = sorted(lg_count.items(), key=lambda kv: (-kv[1], kv[0]))
    # 联赛成块（队多的在前）+ 组内按综合战力降序：全部视图自然分组，选联赛后仍是战力榜
    rows.sort(key=lambda b: (-lg_count[b["league"]], b["league"],
                             -(b.get("power") or 0), b["name"]))
    opts = "".join(
        f'<option value="{C.esc(z)}">{C.esc(z)}（{n}）</option>' for z, n in zones)

    cards = []
    for b in rows:
        mini = C.radar_one(b["metrics"].values(), axes, b["name"], size=88, small=True)
        total = b["settled"] or b["matches"]
        line = f'进 {b["gf_avg"]:.2f} 失 {b["ga_avg"]:.2f} · {total} 场'
        cards.append(
            f'<a class="dt-card" href="../teams/{b["name"]}.html" data-lg="{C.esc(b["league"])}">'
            f'<span class="dt-radar">{mini}</span>'
            '<span class="dt-main">'
            f'<span class="dt-name">{C.esc(b["name"])}</span>'
            f'<span class="dt-lg">{C.esc(b["league"])}</span>'
            f'<span class="dt-line">{line}</span>'
            "</span>"
            f'<span class="dt-power">{b["power"]}<small>战力</small></span>'
            "</a>"
        )
    body = (
        f"<h1 class='page-h1'>{L.ICON_ACTIVITY} 深度数据</h1>"
        f'<p class="sub">{len(rows)} 支球队 · {len(zones)} 项赛事 · '
        "六维战力为联赛内分位（0–100），点球队看赔率与让球走势</p>"
        '<div class="depth-tools">'
        f'<select id="dt-lg" aria-label="按赛事筛选"><option value="">全部赛事</option>{opts}</select>'
        '<span class="sub" id="dt-count"></span>'
        f'<span class="sub" style="margin-left:auto">按综合战力排序</span>'
        "</div>"
        '<div class="depth-grid" id="depth-grid">' + "".join(cards) + "</div>"
        """<script>
(function () {
  var sel = document.getElementById("dt-lg");
  var grid = document.getElementById("depth-grid");
  var cnt = document.getElementById("dt-count");
  var cards = [].slice.call(grid.querySelectorAll(".dt-card"));
  function apply() {
    var v = sel.value, n = 0;
    for (var i = 0; i < cards.length; i++) {
      var ok = !v || cards[i].getAttribute("data-lg") === v;
      cards[i].style.display = ok ? "" : "none";
      if (ok) n++;
    }
    cnt.textContent = "共 " + n + " 支球队";
  }
  sel.addEventListener("change", apply);
  apply();
})();
</script>"""
    )
    return L.page(
        cfg, title="深度数据",
        description=f"{len(rows)} 支球队六维战力、赔率与让球走势，按赛事分类浏览",
        body=body, canonical=f"{base}/depth/", depth=1,
    )
