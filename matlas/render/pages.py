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
    """右栏「AI 预测」卡：风格与左侧赛程统一（ranking-card 卡壳 + fp-opt 筛选芯片）。

    卡内自带与左侧同构的筛选条件：
    - 时间行：日期 radio 切换（10月22日 (13场) 式），横向滚动、数量无上限；
    - 赛事行：联赛 radio 过滤（body:has 规则按生成时联赛数展开）。
    交互全部纯 CSS；概率一律走 C.prob_tag（pct 红线口径）。
    """
    if not digest:
        return ""
    lg_idx: dict[str, str] = {}
    for _, _, items in digest:
        for it in items:
            if it["lg"] and it["lg"] not in lg_idx:
                lg_idx[it["lg"]] = str(len(lg_idx))

    tabs, bodies, rules = [], [], []
    first = True
    for i, (date, n, items) in enumerate(digest):
        if not items:
            continue
        lab = f"{int(date[5:7])}月{int(date[8:10])}日 ({n}场)"
        checked = " checked" if first else ""
        first = False
        # radio 紧贴 label：复用全站 .fp-radio:checked + .fp-opt 的选中态样式
        tabs.append(
            f'<input type="radio" name="aid" id="aid-{i}" class="fp-radio"{checked}>'
            f'<label class="fp-opt" for="aid-{i}">{C.esc(lab)}</label>'
        )
        rules.append(f'body:has(#aid-{i}:checked) .ai-body-{i}{{display:block}}')
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

    return (
        "<style>" + "".join(rules) + "</style>"
        '<div id="ai-pred-card" class="ranking-card ai-pred-card">'
        f'<div class="card-header">{L.ICON_CPU} AI 预测</div>'
        '<div class="ai-filter">'
        '<div class="fp-row"><div class="fp-label">时间:</div>'
        f'<div class="fp-options fp-scroll">{"".join(tabs)}</div></div>'
        '<div class="fp-row"><div class="fp-label">赛事:</div>'
        f'<div class="fp-options fp-scroll">{"".join(lg_opts)}</div></div>'
        "</div>"
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
    # 时间行：跨日期切换赛程（导航，不是本页过滤）。最新日期在首位。
    # 日期条横向滚动、数量无上限——"更多"展开在日期堆到成百上千时不可用，
    # 一条可滑动的 strip 才是可扩展方案；当前日期由全局 JS 滚进可视区。
    time_row = ""
    if dates:
        pre_d = "" if is_today else "../"
        opts = []
        for dstr in dates:
            lab = f"{int(dstr[5:7])}月{int(dstr[8:10])}日"
            if dstr == day.date:
                opts.append(f'<a class="fp-opt active" href="#">{lab}</a>')
            else:
                opts.append(
                    f'<a class="fp-opt" href="{pre_d}days/{dstr}.html">{lab}</a>'
                )
        time_row = (
            '<div class="fp-row"><div class="fp-label">时间:</div>'
            f'<div class="fp-options fp-scroll">{"".join(opts)}</div></div>'
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
        f'<div class="v4-date">{L.ICON_CALENDAR} {date_lab} ({len(ms)}场)</div>'
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

    body = (
        f"<h1 class='page-h1'>{L.ICON_DATA} 数据统计</h1>"
        '<p class="stats-note">准确率主口径为「方向命中」（胜/平/负），与首页卡片同一数据源；'
        "半全场自 2026-10-22 起接入，样本量随日期积累。全部数字由已回填赛果自动计算。</p>"
        '<div class="stats-grid stats-main">'
        f'<div class="stat-card"><div class="pct stat-num">{n_matches}</div><div class="stat-lbl">📊 总预测场次</div></div>'
        f'<div class="stat-card"><div class="pct stat-num">{acc:.1f}%</div><div class="stat-lbl">🎯 整体准确率</div></div>'
        f'<div class="stat-card"><div class="pct stat-num">{hit}</div><div class="stat-lbl">✅ 命中场次</div></div>'
        "</div>"
        '<div class="stats-box"><h3>🔍 单项维度准确率</h3>'
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


def render_features(cfg: Config) -> str:
    """功能页：站点功能清单。只列已上线的能力，每条给真实入口。

    版式与全站统一：白卡网格 + 单色线性 SVG 图标（不用 emoji）。
    """
    base = cfg.base_url.rstrip("/")
    items = [
        (L.ICON_SPORTS, "每日赛事前瞻", "当日全部赛事的结构化量化分析与 AI 置信度", f"{base}/"),
        (L.ICON_ARCHIVE, "历史归档", "逐日留档，结论带哈希指纹，不删不改可核验", f"{base}/days/"),
        (L.ICON_TROPHY, "赛事 / 球队 Top 榜", "按已结算场次统计联赛与球队的方向命中率", f"{base}/"),
        (L.ICON_SEARCH, "站内搜索", "按队名、联赛、编号检索历史赛事", f"{base}/search.html"),
        (L.ICON_ACTIVITY, "单场深度数据", "六维雷达、0-90' 动量曲线、赔率与让球面板", f"{base}/days/"),
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
    """赔率数据集：(按日倒序的日期表, 场次行)。只收带盘口的场次，不造假。"""
    rows = []
    for d in ordered:
        for m in d.matches:
            o = m.odds
            if not (o and (o.home or o.handicap is not None or o.total is not None)):
                continue
            rows.append({
                "d": d.date, "c": m.code or "", "lg": m.competition or "",
                "h": m.home.name, "a": m.away.name, "id": m.match_id,
                "o": [o.home, o.draw, o.away, o.handicap, o.handicap_home,
                      o.handicap_away, o.total, o.over, o.under],
                "r": (m.result.full_score or "") if m.result else "",
            })
    rows.reverse()
    dates: list[str] = []
    for r in rows:
        if r["d"] not in dates:
            dates.append(r["d"])
    return dates, rows


def render_odds(cfg: Config, ordered: list[Day]) -> str:
    """📈赔率：盘口浏览页（数据=jinbet/网易抓取的竞彩盘口快照）。

    日期 tab（JS 切换）+ 当日全部场次的胜平负 / 让球 / 进球盘口表；
    已完赛场次附带比分，便于对照盘口与赛果。
    """
    import json as _json

    base = cfg.base_url.rstrip("/")
    dates, rows = _odds_payload(ordered)
    data_js = _json.dumps({"dates": dates, "rows": rows},
                          ensure_ascii=False, separators=(",", ":"))
    body = (
        f"<h1 class='page-h1'>{L.ICON_TREND} 赔率</h1>"
        '<p class="stats-note">竞彩盘口快照（胜平负 / 让球 / 进球数），数据来源与首页单场页一致；'
        "已完赛场次附带比分。盘口为赛前快照，不随时间更新。</p>"
        '<div class="odds-strip" id="odds-dates"></div>'
        '<div id="odds-out"></div>'
        "<script>\n(function () {\n"
        f"  var DATA = {data_js};\n"
        '''  var strip = document.getElementById("odds-dates");
  var out = document.getElementById("odds-out");
  if (!DATA.dates.length) { out.innerHTML = '<p class="sub">暂无盘口数据。</p>'; return; }
  var fmt = function (v) { return (v === null || v === undefined || v === "") ? "—" : v; };
  DATA.dates.forEach(function (d, i) {
    var b = document.createElement("a");
    b.className = "fp-opt" + (i === 0 ? " active" : "");
    b.href = "javascript:;";
    b.textContent = (+d.slice(5, 7)) + "月" + (+d.slice(8, 10)) + "日";
    b.addEventListener("click", function () {
      strip.querySelectorAll(".fp-opt").forEach(function (x) { x.classList.remove("active"); });
      b.classList.add("active");
      render(d);
    });
    strip.appendChild(b);
  });
  function render(d) {
    var rows = DATA.rows.filter(function (r) { return r.d === d; });
    var html = '<section class="panel"><h3>' + d + ' 共 ' + rows.length + ' 场</h3>'
      + '<table class="history-table"><tr><th>编号</th><th>赛事</th><th>对阵</th>'
      + '<th>主胜</th><th>平</th><th>客胜</th><th>让球</th><th>主</th><th>客</th>'
      + '<th>进球</th><th>大</th><th>小</th><th>赛果</th></tr>';
    rows.forEach(function (r) {
      var o = r.o;
      html += '<tr><td>' + r.c + '</td><td>' + r.lg + '</td>'
        + '<td><a href="matches/' + r.id + '.html">' + r.h + ' vs ' + r.a + '</a></td>'
        + '<td>' + fmt(o[0]) + '</td><td>' + fmt(o[1]) + '</td><td>' + fmt(o[2]) + '</td>'
        + '<td>' + fmt(o[3]) + '</td><td>' + fmt(o[4]) + '</td><td>' + fmt(o[5]) + '</td>'
        + '<td>' + fmt(o[6]) + '</td><td>' + fmt(o[7]) + '</td><td>' + fmt(o[8]) + '</td>'
        + '<td>' + (r.r || "—") + '</td></tr>';
    });
    out.innerHTML = html + '</table></section>';
  }
  render(DATA.dates[0]);
})();
</script>'''
    )
    return L.page(
        cfg, title="赔率", description="竞彩盘口快照浏览：胜平负、让球、进球数盘口与赛果对照",
        body=body, canonical=f"{base}/odds.html", depth=0,
    )


def render_bets(cfg: Config, ordered: list[Day]) -> str:
    """🎯投注：个人记录页（静态站实现：localStorage 存记录 + 内嵌赛果自动结算）。

    添加记录（日期→场次→玩法→选项→赔率→本金）后，JS 按 embed 的赛果自动判
    赢 / 输 / 走水；未开赛自动挂「待开赛」，赛果回填后刷新页面即自动结算。
    记录保存在浏览器本地（localStorage），不依赖后端。
    """
    import json as _json

    base = cfg.base_url.rstrip("/")
    ms = []
    for d in ordered:
        for m in d.matches:
            o = m.odds
            ms.append({
                "id": m.match_id, "d": d.date, "c": m.code or "",
                "lg": m.competition or "", "h": m.home.name, "a": m.away.name,
                "o": ([o.home, o.draw, o.away, o.handicap, o.handicap_home,
                       o.handicap_away, o.total, o.over, o.under] if o else None),
                "r": (m.result.full_score or "") if m.result else "",
                "hf": (m.result.half_score or "") if m.result else "",
            })
    data_js = _json.dumps(ms, ensure_ascii=False, separators=(",", ":"))
    body = (
        f"<h1 class='page-h1'>{L.ICON_ACTIVITY} 投注</h1>"
        '<p class="stats-note">个人投注记录本：记录保存在本浏览器（localStorage），'
        "赛果回填后自动结算盈亏。仅供个人记账复盘，不构成任何购彩建议。</p>"
        '<div class="stats-grid stats-main" id="bet-sum"></div>'
        '<div class="stats-box"><h3>➕ 添加记录</h3>'
        '<div class="bet-form">'
        '<label>日期<select id="b-date"></select></label>'
        '<label>场次<select id="b-match"></select></label>'
        '<label>玩法<select id="b-mk">'
        '<option value="胜平负">胜平负</option><option value="让球">让球</option>'
        '<option value="总进球">总进球</option><option value="比分">精确比分</option>'
        '<option value="半全场">半全场</option></select></label>'
        '<label>选项<select id="b-pick"></select></label>'
        '<label id="b-score-w" style="display:none">比分<input id="b-score" type="text" placeholder="如 2-1"></label>'
        '<label id="b-line-w" style="display:none">盘口<input id="b-line" type="number" step="0.5" placeholder="如 -1 / 2.5"></label>'
        '<label>赔率<input id="b-odds" type="number" step="0.01" min="1"></label>'
        '<label>本金<input id="b-stake" type="number" step="1" min="1" value="10"></label>'
        '<button class="search-btn" id="b-add" type="button">添加</button>'
        "</div>"
        '<p class="sub" id="b-hint">选好场次后，胜平负 / 让球 / 总进球的赔率会按盘口自动填入，可手动修改。</p>'
        "</div>"
        '<div class="stats-box"><h3>📒 我的记录</h3><div id="b-list"></div></div>'
        "<script>\n(function () {\n"
        f"  var MS = {data_js};\n"
        '''  var KEY = "matlas_bets_v1";
  var $ = function (id) { return document.getElementById(id); };
  var byId = {}; MS.forEach(function (m) { byId[m.id] = m; });
  var dates = []; MS.forEach(function (m) { if (dates.indexOf(m.d) === -1) dates.push(m.d); });
  dates.reverse();

  function load() { try { return JSON.parse(localStorage.getItem(KEY) || "[]"); } catch (e) { return []; } }
  function save(v) { try { localStorage.setItem(KEY, JSON.stringify(v)); } catch (e) {} }

  var PICKS = {
    "胜平负": ["主胜", "平", "客胜"],
    "让球": ["主", "客"],
    "总进球": ["大", "小"],
    "比分": [],
    "半全场": ["主/主", "主/平", "主/客", "平/主", "平/平", "平/客", "客/主", "客/平", "客/客"]
  };

  function fillMatches() {
    var d = $("b-date").value;
    var sel = $("b-match");
    sel.innerHTML = "";
    MS.filter(function (m) { return m.d === d; }).forEach(function (m) {
      var op = document.createElement("option");
      op.value = m.id;
      op.textContent = (m.c ? m.c + " " : "") + m.h + " vs " + m.a + (m.r ? "（" + m.r + "）" : "");
      sel.appendChild(op);
    });
    fillPicks();
  }
  function fillPicks() {
    var mk = $("b-mk").value, sel = $("b-pick");
    sel.innerHTML = "";
    (PICKS[mk] || []).forEach(function (p) {
      var op = document.createElement("option"); op.value = p; op.textContent = p; sel.appendChild(op);
    });
    var isScore = mk === "比分";
    sel.style.display = isScore ? "none" : "";
    $("b-score-w").style.display = isScore ? "" : "none";
    $("b-line-w").style.display = (mk === "让球" || mk === "总进球") ? "" : "none";
    autoOdds();
  }
  function autoOdds() {
    var m = byId[$("b-match").value];
    if (!m || !m.o) return;
    var mk = $("b-mk").value, pick = $("b-pick").value;
    var o = m.o, v = null;
    if (mk === "胜平负") v = pick === "主胜" ? o[0] : (pick === "平" ? o[1] : o[2]);
    else if (mk === "让球") v = pick === "主" ? o[4] : o[5];
    else if (mk === "总进球") v = pick === "大" ? o[7] : o[8];
    if (v) $("b-odds").value = v;
    if (mk === "让球" && o[3] !== null && o[3] !== undefined && !$("b-line").value) $("b-line").value = o[3];
    if (mk === "总进球" && o[6] !== null && o[6] !== undefined && !$("b-line").value) $("b-line").value = o[6];
  }

  function settle(bet, m) {
    if (!m || !m.r) return null;
    var f = m.r.split("-"); if (f.length !== 2) return null;
    var h = +f[0], a = +f[1], hf = m.hf ? m.hf.split("-") : null;
    switch (bet.mk) {
      case "胜平负":
        return (bet.pick === "主胜" ? h > a : bet.pick === "平" ? h === a : a > h) ? "win" : "lose";
      case "让球": {
        var eh = h + parseFloat(bet.line);
        if (eh === a) return "push";
        return (bet.pick === "主" ? eh > a : eh < a) ? "win" : "lose";
      }
      case "总进球": {
        var t = h + a, ln = parseFloat(bet.line);
        if (t === ln) return "push";
        return (bet.pick === "大" ? t > ln : t < ln) ? "win" : "lose";
      }
      case "比分": return bet.pick === m.r ? "win" : "lose";
      case "半全场": {
        if (!hf) return null;
        var hs = +hf[0] > +hf[1] ? "主" : (+hf[0] < +hf[1] ? "客" : "平");
        var fs = h > a ? "主" : (h < a ? "客" : "平");
        return bet.pick === hs + "/" + fs ? "win" : "lose";
      }
    }
    return null;
  }

  function render() {
    var bets = load().slice().reverse();
    var n = bets.length, win = 0, lose = 0, push = 0, pending = 0, stake = 0, pnl = 0;
    var html = "";
    bets.forEach(function (b) {
      var m = byId[b.mid];
      var st = settle(b, m);
      if (st === "win") { win++; pnl += b.stake * (b.odds - 1); }
      else if (st === "lose") { lose++; pnl -= b.stake; }
      else if (st === "push") { push++; }
      else pending++;
      if (st !== "push") stake += b.stake;
      var badge = st === "win" ? '<span class="b-win">✔ 已中</span>'
        : st === "lose" ? '<span class="b-lose">✘ 未中</span>'
        : st === "push" ? '<span class="b-push">＝ 走水</span>'
        : '<span class="b-wait">… 待开赛</span>';
      html += '<div class="bet-rec"><div class="br-head"><b>' + (m ? m.h + " vs " + m.a : b.mid)
        + '</b>' + badge
        + '<a class="br-del" href="javascript:;" data-ts="' + b.ts + '">删除</a></div>'
        + '<div class="br-meta">' + b.mid + ' · ' + b.mk
        + (bet.line !== "" && bet.line !== undefined && (b.mk === "让球" || b.mk === "总进球") ? "（盘口 " + b.line + "）" : "")
        + ' · <b>' + b.pick + '</b> @ ' + b.odds + ' · 本金 ' + b.stake
        + ' · 盈亏 <b>' + (st === "win" ? "+" + (b.stake * (b.odds - 1)).toFixed(1)
          : st === "lose" ? "-" + b.stake : st === "push" ? "0" : "—") + '</b>'
        + (m && m.r ? ' · 赛果 ' + m.r + (m.hf ? '（' + m.hf + '）' : '') : '')
        + '</div></div>';
    });
    $("b-list").innerHTML = html || '<p class="sub">还没有记录，用上面表单添加第一笔。</p>';
    var settled = win + lose;
    $("bet-sum").innerHTML =
      '<div class="stat-card"><div class="stat-num">' + n + '</div><div class="stat-lbl">总记录</div></div>'
      + '<div class="stat-card"><div class="stat-num">' + (settled ? (win / settled * 100).toFixed(1) + '%' : '—') + '</div><div class="stat-lbl">命中率</div></div>'
      + '<div class="stat-card"><div class="stat-num">' + stake.toFixed(0) + '</div><div class="stat-lbl">总投入</div></div>'
      + '<div class="stat-card"><div class="stat-num ' + (pnl >= 0 ? 'pnl-pos' : 'pnl-neg') + '">' + (pnl >= 0 ? '+' : '') + pnl.toFixed(1) + '</div><div class="stat-lbl">净盈亏</div></div>';
    $("b-list").querySelectorAll(".br-del").forEach(function (a) {
      a.addEventListener("click", function () {
        save(load().filter(function (x) { return String(x.ts) !== a.getAttribute("data-ts"); }));
        render();
      });
    });
  }

  $("b-date").innerHTML = dates.map(function (d) {
    return '<option value="' + d + '">' + d + '</option>';
  }).join("");
  $("b-date").addEventListener("change", fillMatches);
  $("b-mk").addEventListener("change", fillPicks);
  $("b-pick").addEventListener("change", autoOdds);
  $("b-match").addEventListener("change", autoOdds);
  $("b-add").addEventListener("click", function () {
    var mid = $("b-match").value;
    var mk = $("b-mk").value;
    var pick = mk === "比分" ? ($("b-score") ? $("b-score").value.trim() : "") : $("b-pick").value;
    var odds = parseFloat($("b-odds").value);
    var stake = parseFloat($("b-stake").value);
    if (!mid || !pick || !(odds >= 1) || !(stake > 0)) { alert("请补全：场次、选项、赔率与本金。"); return; }
    if (mk === "让球" || mk === "总进球") {
      var ln = parseFloat($("b-line").value);
      if (isNaN(ln)) { alert("该玩法需要填写盘口。"); return; }
      var bets = load();
      bets.push({ mid: mid, mk: mk, pick: pick, line: ln, odds: odds, stake: stake, ts: Date.now() });
      save(bets);
    } else {
      var bets = load();
      bets.push({ mid: mid, mk: mk, pick: pick, line: "", odds: odds, stake: stake, ts: Date.now() });
      save(bets);
    }
    render();
  });
  fillMatches();
  render();
})();
</script>'''
    )
    return L.page(
        cfg, title="投注", description="个人投注记录本：localStorage 存档，赛果回填后自动结算盈亏",
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
