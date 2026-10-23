"""页面渲染：今日列表、单场落地页、按日归档、归档索引。"""

from __future__ import annotations

from typing import Any

from ..config import Config
from ..models import Match, Day, Metrics, Momentum, sort_matches
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


def _odds_panel(m: Match) -> str:
    """市场数据：jinbet 同款三列赔率格 + 完整盘口表。"""
    o = m.odds
    if not o:
        return ""
    imp = o.implied() or {}
    grid_rows: list[tuple[str, str, str]] = []
    if o.home and o.draw and o.away:
        grid_rows = [
            (f"{m.home.name} 胜", f"{o.home:g}", "win"),
            ("平", f"{o.draw:g}", "draw"),
            (f"{m.away.name} 胜", f"{o.away:g}", "loss"),
        ]
    grid = C.odds_grid(grid_rows)

    rows = []
    if o.home and o.draw and o.away:
        rows.append(["胜平负", f"{o.home:g}", f"{o.draw:g}", f"{o.away:g}"])
    if imp:
        # §3.2：概率一律走 prob_tag，不裸写百分比
        rows.append([
            "去水概率",
            C.prob_tag(imp["home"]),
            C.prob_tag(imp["draw"]),
            C.prob_tag(imp["away"]),
        ])
    if o.handicap is not None and (o.handicap_home or o.handicap_away):
        rows.append([
            f"让球 {o.handicap:+g}".replace("+0", "0"),
            f"{o.handicap_home:g}" if o.handicap_home else "—",
            "—",
            f"{o.handicap_away:g}" if o.handicap_away else "—",
        ])
    if o.total is not None and (o.over or o.under):
        rows.append([
            f"进球数 {o.total:g}",
            f"大 {o.over:g}" if o.over else "—",
            "—",
            f"小 {o.under:g}" if o.under else "—",
        ])
    body = grid + (C.table(["市场", m.home.name, "平", m.away.name], rows) if rows else "")
    if o.bookmaker:
        body += f'<p class="panel-hint">来源：{C.esc(o.bookmaker)}</p>'
    return C.panel("市场数据", body) if body.strip() else ""


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


def _form_panel(m: Match) -> str:
    """近期战绩：明细（自产历史聚合，含半全场结果）+ 网易近况圆点（当日场次）。

    明细来自站点已回填赛果（date < 本场，赛前视角可回溯）；网易序列只有
    进失球（无对手/日期），出圆点概括不冒充明细。
    """
    parts = []
    for title, rows_src in (
        (f"{m.home.name} 近期", m.recent_home),
        (f"{m.away.name} 近期", m.recent_away),
    ):
        if not rows_src:
            continue
        dots = C.form_dots([r.outcome for r in rows_src])
        zh = {"W": "胜", "D": "平", "L": "负"}
        rows = [
            [r.date, r.competition, ("主" if r.venue == "home" else "客") + " " + r.opponent,
             r.score, r.half_ft or "—", zh.get(r.outcome, r.outcome)]
            for r in rows_src
        ]
        parts.append(
            f"<h3>{C.esc(title)}</h3>{dots}"
            + C.table(["日期", "赛事", "对手", "比分", "半全场", "结果"], rows, cls="history-table")
        )
    # 网易赛前状态（gf/ga 序列）：圆点 + 场均进失，主客各两组
    fn = m.extras.get("form_net") or {}

    def _net_bits(key: str) -> str:
        seq = fn.get(key) or []
        if not seq:
            return ""
        outcomes = []
        gf_sum = ga_sum = 0
        for x in seq:
            try:
                gf, ga = int(x.get("gf", 0)), int(x.get("ga", 0))
            except (ValueError, TypeError, AttributeError):
                continue
            outcomes.append("W" if gf > ga else ("D" if gf == ga else "L"))
            gf_sum += gf
            ga_sum += ga
        if not outcomes:
            return ""
        n = len(outcomes)
        return (
            f"<h3>{C.esc(key_map[key])}</h3>{C.form_dots(outcomes)}"
            f'<p class="sub">近 {n} 场 进 {gf_sum} 失 {ga_sum}'
            f"（场均 {gf_sum / n:.1f} / {ga_sum / n:.1f}）</p>"
        )

    key_map = {"home_7": f"{m.home.name} 近期", "home_home": f"{m.home.name} 近期主场",
               "away_7": f"{m.away.name} 近期", "away_away": f"{m.away.name} 近期客场"}
    net_parts = "".join(filter(None, (_net_bits(k) for k in key_map)))
    if net_parts:
        parts.append('<div class="net-form">' + net_parts + "</div>")
    if parts:
        return C.panel("近期战绩", "".join(parts))
    return C.panel(
        "近期战绩",
        '<p class="panel-empty">近期战绩数据源尚未接入，框架已预留，数据补齐后自动展示。</p>',
    )


def _h2h_panel(m: Match) -> str:
    """历史交锋：两队交手明细（自产聚合，含半全场）；无记录时出占位。"""
    if not m.h2h:
        return C.panel(
            "历史交锋",
            '<p class="panel-empty">两队在本站收录期内暂无交手记录，数据积累后自动展示。</p>',
        )
    rows = []
    for h in m.h2h:
        # 主客对调过的场次按当时主客呈现，另标出本场视角的半全场意义有限，仅列比分
        rows.append([h.date, h.competition, f"{h.home} {h.score} {h.away}"])
    return C.panel("历史交锋", C.table(["日期", "赛事", "对阵与比分"], rows, cls="history-table"))


def _injury_panel(m: Match) -> str:
    if not m.injuries:
        return C.panel(
            "伤停与缺阵",
            '<p class="panel-empty">伤停数据源尚未接入，框架已预留，数据补齐后自动展示。</p>',
        )
    rows = []
    for inj in m.injuries:
        who = m.home.name if inj.team == "home" else (m.away.name if inj.team == "away" else inj.team)
        status = {"out": "缺阵", "doubt": "存疑", "suspended": "停赛"}.get(inj.status, inj.status)
        rows.append([who, inj.player, inj.reason or "—", status])
    return C.panel("伤停与缺阵", C.table(["球队", "球员", "原因", "状态"], rows))


def _charts_panel(m: Match) -> str:
    if not m.metrics_home or not m.metrics_away:
        return C.panel(
            "战力对照",
            '<p class="panel-empty">六维战力 / 动量曲线数据源尚未接入，框架已预留，数据补齐后自动展示。</p>',
        )
    axes = [zh for _, zh in Metrics.AXES]
    radar = C.radar_svg(
        m.metrics_home.values(), m.metrics_away.values(), axes,
        m.home.name, m.away.name,
    )
    mom = ""
    if m.momentum and len(m.momentum.labels) >= 2:
        mom = (
            '<div style="margin-top:22px"><h3>进球威胁度走势</h3>'
            + C.momentum_svg(
                m.momentum.labels, m.momentum.home, m.momentum.away,
                m.home.name, m.away.name,
            )
            + "</div>"
        )
    return C.panel(
        "战力对照",
        f"<h3>六维战力</h3>{radar}{mom}",
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


def _compare_panel(m: Match) -> str:
    """核心数据对比：主客两队可量化指标并排（对方「核心数据对比」同框架）。"""
    ex = m.extras or {}
    rows = []
    lam_h, lam_a = ex.get("lam_home"), ex.get("lam_away")
    if lam_h is not None and lam_a is not None:
        rows.append(["期望进球（模型）", f"{lam_h:g}", f"{lam_a:g}"])
    dn = ex.get("data_n") or {}
    if dn.get("home") or dn.get("away"):
        rows.append(["统计样本（场）", str(dn.get("home", "—")), str(dn.get("away", "—"))])
    body = (
        C.table(["数据维度", m.home.name, m.away.name], rows, cls="duo")
        if rows
        else '<p class="panel-empty">两队量化指标数据源尚未接入，框架已预留。</p>'
    )
    return C.panel("核心数据对比", body)


def _model_panel(m: Match) -> str:
    """模型视角：λ 总量 / 三方向最可能比分 / 冷门评估（来自模型快照 extras）。"""
    ex = m.extras or {}
    bits = []
    if ex.get("lam_total") is not None:
        bits.append(f"<p>模型预期总进球合计：<b>{ex['lam_total']:g}</b> 球</p>")
    quad = ex.get("quad_top") or {}
    qrows = []
    for key, lab in (("home", "主胜"), ("draw", "平"), ("away", "客胜")):
        q = quad.get(key)
        if isinstance(q, dict) and q.get("score"):
            qrows.append([lab, str(q["score"]).replace(":", "-"), f"{q.get('prob', 0):g}%"])
    if qrows:
        bits.append(
            "<h4>三方向最可能比分</h4>"
            + C.table(["方向", "最可能比分", "模型概率"], qrows)
        )
    if ex.get("upset_prob") is not None:
        lvl = ex.get("upset_level", "")
        bits.append(
            f"<p>冷门评估：<b>{C.esc(str(lvl))}</b>"
            f'（冷门概率 <span class="pct mini">{ex["upset_prob"]:g}%</span>）</p>'
        )
    body = "".join(bits) or (
        '<p class="panel-empty">模型过程数据尚未接入，框架已预留。</p>'
    )
    return C.panel("模型视角", body)


def _referee_panel(m: Match) -> str:
    """裁判执法数据：暂无数据源，框架占位（对齐对方同区块）。"""
    return C.panel(
        "裁判执法数据",
        '<p class="panel-empty">裁判执法数据源尚未接入，框架已预留，数据补齐后自动展示。</p>',
    )


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


def _ledger(m: Match) -> str:
    settled = ""
    if m.result and m.result.full_score:
        r = m.result
        marks = []
        for lab, v in (("方向", r.direction_hit), ("比分", r.score_hit), ("进球", r.goals_hit), ("半全", r.htft_hit)):
            if v is None:
                continue
            marks.append(f"{lab} {'命中' if v else '未中'}")
        settled = (
            f'<p>赛后回填：半场 {C.esc(r.half_score or "—")} · 全场 '
            f'<strong>{C.esc(r.full_score)}</strong>　{C.esc("　".join(marks))}'
            + (f'<br>结算于 {C.esc(r.settled_at)}' if r.settled_at else "")
            + "</p>"
        )
    return (
        '<div class="ledger">'
        f"<strong>留档核验</strong><br>"
        f"结论指纹 <code>{C.esc(m.fingerprint())}</code>　（仅覆盖赛前结论，赛后回填不改变该值）<br>"
        f"生成于 {C.esc(m.generated_at or '—')}"
        + (f'<br>数据来源 <a href="{C.esc(m.source_url)}">{C.esc(m.source_url)}</a>' if m.source_url else "")
        + settled
        + "</div>"
    )


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
        _intel_panel(m),        # 1. 📌 赛前情报速览
        _main_pick_block(m),    # 一句话主推（有才出现）
        _compare_panel(m),      # 2. 🔍 核心数据对比
        _h2h_panel(m),          # 3. ⚔️ 历史交锋数据
        _form_panel(m),         # 4. 📈 球队状态（近期战绩）
        _injury_panel(m),       # 5. ⚠️ 核心球员缺阵影响
        _referee_panel(m),      # 6. ⚖️ 裁判执法数据
        _odds_panel(m),         # 市场数据
        _handicap_panel(m),     # 7. 🤔 让步可信度分析
        _model_panel(m),        # 8. 🧠 模型视角
        C.panel("综合赛果推演", picks) if picks else "",   # 9. 🎯
        _charts_panel(m),       # 战力对照（雷达/动量，有数据才画）
        _standings_panel(m),    # 积分排名（有数据才画）
        _reference_panel(m),    # 外部对照（有才出现）
        _ledger(m),
    ]

    jsonld = _match_jsonld(cfg, m, url, title, desc)
    return L.page(
        cfg,
        title=title,
        description=desc,
        body="".join(body_parts),
        canonical=url,
        jsonld=jsonld,
        nav_day=m.day,
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
                f'<a class="ranking-item" href="{pre}days/">'
                f'<div class="rank-index">{i}</div>{img}'
                f'<span class="rank-name lg-link" data-goto="{goto}">{C.esc(name)}</span>'
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
        '<a class="v4-day-arrow" href="#" data-aid-step="1" aria-label="前一天">‹</a>'
        f'<div class="v4-date">{L.ICON_CALENDAR} {"".join(date_spans)}</div>'
        '<a class="v4-day-arrow" href="#" data-aid-step="-1" aria-label="后一天">›</a>'
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
        arrow = lambda d, ch: (
            f'<a class="v4-day-arrow" href="{pre_d}days/{d}.html" '
            f'aria-label="{ch}一天">{ch}</a>'
            if d else f'<span class="v4-day-arrow off">{ch}</span>'
        )
        arrows = (
            f'{arrow(prev_d, "‹")}'
            f'<div class="v4-date">{L.ICON_CALENDAR} {date_lab} ({len(ms)}场)</div>'
            f'{arrow(next_d, "›")}'
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
        jsonld=jsonld, nav_day=day.date,
        depth=0 if is_today else 1,
    )


def render_archive_index(cfg: Config, days: list[str],
                         leagues: list[tuple[str, int, int, int]] | None = None,
                         teams: list[tuple[str, int, int, int]] | None = None) -> str:
    """历史归档页：交易日 / 联赛 / 球队 三视图（纯 CSS radio 切换）。

    leagues/teams 元素为 (名称, 已收录场数, 命中场数, 已结算场数)。
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

    lg_view = _grid(leagues or [], "leagues") or '<p class="sub">暂无联赛数据。</p>'
    tm_view = _grid(teams or [], "teams") or '<p class="sub">暂无球队数据。</p>'
    body = (
        "<h1>历史归档</h1>"
        f'<p class="sub">共 {len(ds)} 个交易日，逐日留档，结论指纹可核验；'
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
        body=body, canonical=f"{base}/days/", nav_day="", depth=1,
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
    → 联赛/杯赛准确率排名 → 球队准确率 Top 15 → 机器可读数据。
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

    def _pc(pair) -> str:
        h, n = pair
        return f'<span class="pct">{h / n * 100:.0f}%</span>' if n else "—"

    lg_rows = [
        [C.esc(lg), str(a["n"]), f'<span class="pct">{a["h"] / a["n"] * 100:.1f}%</span>',
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

    # ---- 球队 Top 15 ----
    t15 = compute_team_ranking(ordered, top=15)
    t_rows = [
        [str(i), C.esc(name), str(n), f'<span class="pct">{h / n * 100:.1f}%</span>']
        for i, (name, h, n) in enumerate(t15, 1)
    ]
    team_box = (
        '<div class="stats-box"><h3>🛡️ 球队准确率排名 (Top 15)</h3>'
        + (
            C.table(["#", "球队", "已结算", "准确率"], t_rows, cls="history-table")
            if t_rows
            else '<p class="panel-empty">暂无已结算样本。</p>'
        )
        + "</div>"
    )

    # ---- 洞察总结：把上方各板块数字聚成一句话结论 ----
    insights: list[str] = []
    if settled:
        insights.append(
            f'🎯 已结算 <b>{len(settled)}</b> 场，方向命中 <b>{hit}</b> 场，'
            f'整体命中率 <span class="pct"><b>{acc:.1f}%</b></span>'
        )
    dim_ok = [(zh, _dim(name)[0] / _dim(name)[1] * 100, _dim(name)[1])
              for name, zh in dims if _dim(name)[1] >= 5]
    if dim_ok:
        best = max(dim_ok, key=lambda x: x[1])
        worst = min(dim_ok, key=lambda x: x[1])
        insights.append(f'📌 四维最稳：「{best[0]}」<span class="pct"><b>{best[1]:.1f}%</b></span>（{best[2]} 场）')
        if best is not worst and worst[0] != best[0]:
            insights.append(f'⚠️ 待提升：「{worst[0]}」<span class="pct"><b>{worst[1]:.1f}%</b></span>（{worst[2]} 场）')
    by_day_acc = []
    for d in ordered:
        dd = [m for m in d.matches if m.result and m.result.full_score]
        if dd:
            by_day_acc.append((sum(1 for m in dd if m.result.direction_hit), len(dd)))
    if len(by_day_acc) >= 6:
        rh = sum(x[0] for x in by_day_acc[-5:])
        rn = sum(x[1] for x in by_day_acc[-5:])
        ph = sum(x[0] for x in by_day_acc[:-5])
        pn = sum(x[1] for x in by_day_acc[:-5])
        ra, pa = rh / rn * 100, ph / pn * 100
        trend = "↗ 走高" if ra > pa + 2 else ("↘ 走低" if ra < pa - 2 else "→ 持平")
        insights.append(
            f'📈 近 5 个比赛日 <span class="pct"><b>{ra:.1f}%</b></span>'
            f'（此前 <span class="pct"><b>{pa:.1f}%</b></span>）{trend}'
        )
    by_lg_acc: dict[str, tuple[int, int]] = {}
    for m in settled:
        if m.competition:
            h2, n2 = by_lg_acc.get(m.competition, (0, 0))
            by_lg_acc[m.competition] = (h2 + (1 if m.result.direction_hit else 0), n2 + 1)
    lg_ok = [(k, v[0] / v[1] * 100, v[1]) for k, v in by_lg_acc.items() if v[1] >= 5]
    if lg_ok:
        blg = max(lg_ok, key=lambda x: x[1])
        insights.append(f'🏆 表现最佳赛事：「{C.esc(blg[0])}」<span class="pct"><b>{blg[1]:.1f}%</b></span>（{blg[2]} 场）')
    insight_box = ""
    if insights:
        insight_box = (
            '<div class="stats-box insight-box"><h3>🧾 洞察总结</h3>'
            '<ul class="insight-list">' + "".join(f"<li>{x}</li>" for x in insights) + "</ul></div>"
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
        "<h2>机器可读数据</h2>"
        '<ul class="plain-list">'
        f'<li><a href="{base}/llms.txt">llms.txt</a> — 站点结构索引（LLM/GEO 用）</li>'
        f'<li><a href="{base}/dataset.json">dataset.json</a> — 全量结构化数据</li>'
        f'<li><a href="{base}/days/">📅 历史归档</a> — 逐日留档，结论指纹可核验</li>'
        "</ul>"
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
    days = [d for d in reversed(ordered) if d.matches]

    # 按年→月分组，<details> 原生展开收起；最新年/月默认展开
    def card(d: Day) -> str:
        lgs: list[str] = []
        for m in d.matches:
            if m.competition and m.competition not in lgs:
                lgs.append(m.competition)
        lg_txt = "、".join(lgs[:3]) + ("等" if len(lgs) > 3 else "")
        return (
            f'<a class="pv-day" href="{d.date}.html">'
            f'<span class="pv-d">{d.date}</span><span class="pv-w">{_pv_wd(d.date)}</span>'
            f'<span class="pv-n">共 {len(d.matches)} 场</span>'
            f'<span class="pv-lg">{C.esc(lg_txt)}</span>'
            f'<span class="pv-go">打开 AI 报告 →</span></a>'
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
        description="每日赛事前瞻列表：AI 报告逐日留档，方向、比分、总进球首选与信心分层",
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


def render_features(cfg: Config) -> str:
    """功能页：站点功能清单。只列已上线的能力，每条给真实入口。

    版式与全站统一：白卡网格 + 单色线性 SVG 图标（不用 emoji）。
    """
    base = cfg.base_url.rstrip("/")
    items = [
        (L.ICON_SPORTS, "每日赛事前瞻", "每日 AI 报告列表，逐日留档可回溯", f"{base}/preview/"),
        (L.ICON_ARCHIVE, "历史归档", "逐日留档，结论带哈希指纹，不删不改可核验", f"{base}/days/"),
        (L.ICON_TROPHY, "赛事 / 球队 Top 榜", "按已结算场次统计联赛与球队的方向命中率", f"{base}/"),
        (L.ICON_SEARCH, "站内搜索", "按队名、联赛、编号检索历史赛事", f"{base}/search.html"),
        (L.ICON_ACTIVITY, "单场深度数据", "六维雷达、0-90' 动量曲线、赔率与让球面板", f"{base}/days/"),
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
      // 比分（主胜组 / 平组 / 客胜组）
      var sc = "";
      Object.keys(of.score || {}).forEach(function (k) {
        var v = of.score[k], cls = "", hit = false;
        var mm = k.match(/^(\\d+):(\\d+)$/);
        if (mm) {
          var x = +mm[1], y = +mm[2];
          cls = x > y ? "s-h" : x < y ? "s-a" : "s-d";
          hit = done && r.gh === x && r.ga === y;
        } else {
          cls = k.indexOf("胜") === 0 ? "s-h" : k.indexOf("负") === 0 ? "s-a" : "s-d";
        }
        sc += pill(k, v, hit, cls);
      });
      html += sec("比分", sc);
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
      ex += kvSec("比分", of.score, "score") + kvSec("总进球", of.goals, "goals") + kvSec("半全场", of.htft, "htft");
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
    if (!crDate) return;
    var d = crDate.value;
    var n = 0;
    DATA.rows.forEach(function (r) {
      if (r.d === d && CRS[r.id]) { delete CRS[r.id]; n += 1; }
    });
    saveCRS();
    crSettleAll();
    $("cr-msg").textContent = n ? "🗑 已清空当日 " + n + " 场自定义赛果并重新结算" : "当日没有已保存的自定义赛果";
    renderCR();
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
                stats: tuple[int, int] | None = None) -> str:
    """球队专题页：头部（队徽+队名+统计）+ 该队全部已收录场次列表。"""
    base = cfg.base_url.rstrip("/")
    ordered = sorted(matches, key=lambda m: (m.day, m.code or ""), reverse=True)
    cards = "".join(_card(cfg, m, pre="../") for m in ordered[:60]) or (
        '<p class="sub">该球队暂无已收录场次。</p>'
    )
    hit, total = stats or (0, 0)
    acc = (hit / total * 100) if total else 0.0
    meta = (
        f"已收录 <b>{len(matches)}</b> 场 · 已结算 <b>{total}</b> 场 · "
        f'方向命中 <span class="pct"><b>{acc:.1f}%</b></span>'
        if total
        else f"已收录 <b>{len(matches)}</b> 场 · 赛果回填后自动统计命中率"
    )
    logo = logos.crest_url(team_name)
    body = (
        _lt_header(team_name, logo=logo, meta=meta)
        + f'<div class="cards">{cards}</div>'
    )
    return L.page(
        cfg, title=f"{team_name} 赛事专题", description=f"{team_name} 全部已收录场次的方向命中率与逐场分析",
        body=body, canonical=f"{base}/teams/{team_name}.html", depth=1,
    )
