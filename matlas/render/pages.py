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
    """四宫格：方向 / 比分 / 进球 / 半全。缺哪维就不画哪格。"""
    titles = {"direction": "方向", "score": "比分", "goals": "进球", "htft": "半全场"}
    cells = []
    for kind, title in titles.items():
        items = m.forecasts_of(kind)
        if not items:
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
    """近期战绩：jinbet 同款 —— 圆点概括 + 明细表（二者始终并列）。"""
    parts = []
    for title, rows_src, team in (
        (f"{m.home.name} 近期", m.recent_home, m.home),
        (f"{m.away.name} 近期", m.recent_away, m.away),
    ):
        if not rows_src:
            continue
        dots = C.form_dots([r.outcome for r in rows_src])
        rows = [
            [r.date, r.competition, ("主" if r.venue == "home" else "客") + " " + r.opponent, r.score, r.outcome]
            for r in rows_src
        ]
        parts.append(
            f"<h3>{C.esc(title)}</h3>{dots}"
            + C.table(["日期", "赛事", "对手", "比分", "结果"], rows, cls="history-table")
        )
    return C.panel("近期战绩", "".join(parts)) if parts else ""


def _h2h_panel(m: Match) -> str:
    if not m.h2h:
        return C.panel("历史交锋", "<p>暂无交锋记录</p>")
    rows = [[h.date, h.competition, f"{h.home} {h.score} {h.away}"] for h in m.h2h]
    return C.panel("历史交锋", C.table(["日期", "赛事", "对阵与比分"], rows))


def _injury_panel(m: Match) -> str:
    if not m.injuries:
        return ""
    rows = []
    for inj in m.injuries:
        who = m.home.name if inj.team == "home" else (m.away.name if inj.team == "away" else inj.team)
        status = {"out": "缺阵", "doubt": "存疑", "suspended": "停赛"}.get(inj.status, inj.status)
        rows.append([who, inj.player, inj.reason or "—", status])
    return C.panel("伤停与缺阵", C.table(["球队", "球员", "原因", "状态"], rows))


def _charts_panel(m: Match) -> str:
    if not m.metrics_home or not m.metrics_away:
        return ""
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
    header = _mc_header(m)
    body_parts = [
        '<div class="card card-match">',
        header,
        '<div class="mc-body">',
        teams_row,
        f'<p class="sub" style="text-align:center;margin:0">{C.esc(meta)}{cold}{sample}</p>',
        "</div>",
        "</div>",
        _main_pick_block(m),
        _risk_panel(m),
        _picks(m),
        _charts_panel(m),
        _odds_panel(m),
        _handicap_panel(m),
        _standings_panel(m),
        _h2h_panel(m),
        _form_panel(m),
        _injury_panel(m),
        _reference_panel(m),
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


def _mc_header(m: Match) -> str:
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
        f'<span class="league">{C.esc(m.competition)}</span>'
        + (f'<span class="num">{C.esc(m.code)}</span>' if m.code else "")
        + f'<span class="time">{C.esc(time_txt)}</span>'
        '</div><div class="mc-status">'
        f'<span class="mc-conf {conf_cls}">AI置信度:{C.esc(conf_lab)}</span>{stamp}'
        "</div></div>"
    )


def _mc_teams(m: Match, pre: str = "") -> str:
    """队徽 + 大比分（括号内半场）。未结算时中间出 VS。pre 为页深前缀。"""
    if m.result and m.result.full_score:
        sub = (
            f'<div class="sub">({C.esc(m.result.half_score)})</div>'
            if m.result.half_score
            else ""
        )
        score = (
            f'<div class="mc-score"><div class="main">{C.esc(m.result.full_score)}</div>'
            f"{sub}</div>"
        )
    else:
        score = '<div class="mc-score"><div class="vs">VS</div></div>'

    def cell(t) -> str:
        return (
            f'<div class="mc-team">{C.crest_img(t, pre=pre)}'
            f"<span>{C.esc(t.name)}</span></div>"
        )

    return f'<div class="mc-teams">{cell(m.home)}{score}{cell(m.away)}</div>'


def _mc_tags(m: Match) -> str:
    """四个维度的 emoji 标签，命中项加 .hit 提亮。

    只带 emoji + 结论，不带维度名 —— 维度名由 emoji 表达，
    否则窄屏一行放不下会折行。
    """
    emoji = {"direction": "🧭", "score": "🔢", "goals": "⚽", "htft": "📈"}
    hit_of = {
        "direction": "direction_hit", "score": "score_hit",
        "goals": "goals_hit", "htft": "htft_hit",
    }
    tags = []
    for kind in ("direction", "score", "goals", "htft"):
        f = m.headline.get(kind)
        if not f:
            continue
        hit = bool(m.result and getattr(m.result, hit_of[kind], None))
        tags.append(
            f'<div class="mc-tag{" hit" if hit else ""}">'
            f"{emoji[kind]} {C.esc(f.label)}</div>"
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
        + _mc_header(m)
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
            else:
                logo, alt = logos.league_crest_url(name), "徽章"
            img = (
                f'<img src="{pre}{C.esc(logo)}" class="rank-logo" alt="{C.esc(name)}{alt}" loading="lazy">'
                if logo
                else f'<span class="rank-logo rank-logo-ph" aria-hidden="true">{C.esc(name[:1])}</span>'
            )
            items.append(
                f'<a class="ranking-item" href="{pre}days/">'
                f'<div class="rank-index">{i}</div>{img}'
                f'<span class="rank-name">{C.esc(name)}</span>'
                f'<div class="rank-bar-wrap">'
                f'<div class="rank-bar" style="width:{acc:.1f}%"></div></div>'
                f'<span class="rank-acc pct">{acc:.1f}%</span></a>'
            )
        inner = f'<div class="ranking-list">{"".join(items)}</div>'
    head = "🛡️ 球队Top 10" if kind == "team" else "🏆 赛事Top 10"
    return (
        f'<div id="{"team-ranking-card" if kind == "team" else "league-ranking-card"}" class="ranking-card">'
        f'<div class="card-header">{head}</div>'
        f"{inner}</div>"
    )


def render_day(cfg: Config, day: Day, *, is_today: bool = False, rel: str = "",
               ranking: list[tuple[str, int, int]] | None = None,
               team_ranking: list[tuple[str, int, int]] | None = None) -> str:
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
    panel = (
        f'{filter_css}<input type="checkbox" id="fp-toggle" class="fp-toggle">'
        '<div id="filter-panel" class="filter-panel">'
        f"{type_row}{league_row}"
        "</div>"
    )
    main_col = (
        '<div class="v4-main-col">'
        '<div class="v4-filter-bar">'
        f'<div class="v4-date">📅 {date_lab} ({len(ms)}场)</div>'
        '<label class="v4-filter-btn" for="fp-toggle">'
        f'<span>🔍 筛选</span></label>'
        "</div>"
        f"{panel}"
        f'<div class="cards">{cards}</div>'
        "</div>"
    )
    body = (
        f'<h1 class="sr-only">{C.esc(h1)}</h1>'
        f'<div class="v4-layout">{main_col}'
        '<aside class="right-sidebar-new">'
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


def render_archive_index(cfg: Config, days: list[str]) -> str:
    base = cfg.base_url.rstrip("/")
    rows = [[f'<a href="{d}.html">{d}</a>', "查看"] for d in sorted(days, reverse=True)]
    body = (
        "<h1>历史归档</h1>"
        f'<p class="sub">共 {len(days)} 个交易日，逐日留档，结论指纹可核验。</p>'
        + (C.table(["日期", ""], rows) if rows else "<p>暂无归档。</p>")
    )
    return L.page(
        cfg, title="历史归档", description="按日期归档的全部赛事分析",
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
    """📊数据：站点统计页。全部数字实时从已发布数据计算，不造假。"""
    base = cfg.base_url.rstrip("/")
    total = len(days)
    n_matches = sum(len(d.matches) for d in days)
    settled = [m for d in days for m in d.matches if m.result and m.result.full_score]
    hit = sum(1 for m in settled if m.result.direction_hit)
    acc = (hit / len(settled) * 100) if settled else 0.0
    ranking = compute_ranking(days, top=999)
    rows = [
        [C.esc(lg), str(n), str(h), f'<span class="pct">{(h / n * 100):.0f}%</span>']
        for lg, h, n in ranking
    ]
    body = (
        "<h1>📊 数据统计</h1>"
        '<div class="stats-grid">'
        f'<div class="stat-card"><div class="pct stat-num">{total}</div><div class="stat-lbl">交易日</div></div>'
        f'<div class="stat-card"><div class="pct stat-num">{n_matches}</div><div class="stat-lbl">赛事场次</div></div>'
        f'<div class="stat-card"><div class="pct stat-num">{len(settled)}</div><div class="stat-lbl">已结算</div></div>'
        f'<div class="stat-card"><div class="pct stat-num">{acc:.0f}%</div><div class="stat-lbl">方向命中率</div></div>'
        "</div>"
        "<h2>各联赛方向命中</h2>"
        + (
            C.table(["联赛", "已结算", "命中", "命中率"], rows)
            if rows
            else '<p class="sub">暂无已结算赛事，赛后自动回填。</p>'
        )
        + "<h2>机器可读数据</h2>"
        '<ul class="plain-list">'
        f'<li><a href="{base}/llms.txt">llms.txt</a> — 站点结构索引（LLM/GEO 用）</li>'
        f'<li><a href="{base}/dataset.json">dataset.json</a> — 全量结构化数据</li>'
        f'<li><a href="{base}/days/">📅 历史归档</a> — 逐日留档，结论指纹可核验</li>'
        "</ul>"
    )
    return L.page(
        cfg, title="数据统计", description="站点赛事统计：交易日、场次、方向命中率与各联赛分布",
        body=body, canonical=f"{base}/data.html", depth=0,
    )


def render_features(cfg: Config) -> str:
    """🧩功能：站点功能清单。只列已上线的能力，每条给真实入口。"""
    base = cfg.base_url.rstrip("/")
    items = [
        ("📅 每日赛事前瞻", "当日全部赛事的结构化量化分析与 AI 置信度", f"{base}/"),
        ("📚 历史归档", "逐日留档，结论带哈希指纹，不删不改可核验", f"{base}/days/"),
        ("🏆 赛事 Top 榜", "按已结算场次统计各联赛方向命中率", f"{base}/"),
        ("🔍 站内搜索", "按队名、联赛、编号检索历史赛事", f"{base}/search.html"),
        ("📈 单场深度数据", "六维雷达、0-90' 动量曲线、赔率与让球面板", f"{base}/days/"),
        ("🤖 机器可读数据", "llms.txt / dataset.json，供 LLM 与工具直接消费", f"{base}/llms.txt"),
    ]
    lis = "".join(
        f'<li class="feat-item"><div class="feat-name">{name}</div>'
        f'<div class="feat-desc">{desc}</div><a href="{url}">进入 →</a></li>'
        for name, desc, url in items
    )
    body = f"<h1>🧩 功能</h1><ul class='feat-list'>{lis}</ul>"
    return L.page(
        cfg, title="功能", description="站点功能清单：每日前瞻、历史归档、赛事Top、站内搜索、机器可读数据",
        body=body, canonical=f"{base}/features.html", depth=0,
    )


def render_me(cfg: Config) -> str:
    """👤我的：会员中心占位。功能未上线，如实说明。"""
    base = cfg.base_url.rstrip("/")
    body = (
        "<h1>👤 我的</h1>"
        '<div class="me-card">'
        '<div class="me-avatar">👤</div>'
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
        "<h1>🔍 站内搜索</h1>"
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
