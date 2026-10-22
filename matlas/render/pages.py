"""页面渲染：今日列表、单场落地页、按日归档、归档索引。"""

from __future__ import annotations

from typing import Any

from ..config import Config
from ..models import Match, Day, Metrics, Momentum, sort_matches
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

    teams_row = f'<h1 class="sr-only">{C.esc(m.home.name)} vs {C.esc(m.away.name)}</h1>' + _mc_teams(m)
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
        f'<p class="disclaimer">{C.esc(cfg.disclaimer)}</p>',
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


def _mc_teams(m: Match) -> str:
    """队徽 + 大比分（括号内半场）。未结算时中间出 VS。"""
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
        return f'<div class="mc-team">{C.crest_img(t)}<span>{C.esc(t.name)}</span></div>'

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
        + _mc_teams(m)
        + _mc_tags(m)
        + footer
        + "</div></a>"
    )


def render_day(cfg: Config, day: Day, *, is_today: bool = False, rel: str = "") -> str:
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
    if day.note:
        cards = f'<p class="sub">{C.esc(day.note)}</p>' + cards

    # 联赛筛选：纯 CSS（radio + :checked ~ 兄弟选择器），不引 JS。
    # 单选/标签取联赛下标而非联赛名，避免中文名进选择器后转义出错。
    filter_bar = filter_css = ""
    if len(leagues) > 1:
        opts = [
            '<input type="radio" name="lf" id="lf-all" class="lf" checked>'
            '<label for="lf-all">全部</label>'
        ]
        rules = []
        for i, lg in enumerate(leagues):
            opts.append(
                f'<input type="radio" name="lf" id="lf-{i}" class="lf">'
                f'<label for="lf-{i}">{C.esc(lg)}</label>'
            )
            # radio 在 .lf-bar 内部，不是 .cards 的兄弟，所以不能用 `~`；
            # 用 body:has() 从根上匹配，规则不受 DOM 层级限制。
            rules.append(
                f'body:has(#lf-{i}:checked) .cards .match-card:not([data-lg="{i}"])'
                "{display:none}"
            )
        filter_bar = f'<div class="lf-bar">{"".join(opts)}</div>'
        filter_css = "<style>" + "".join(rules) + "</style>"

    date_lab = f"{int(day.date[5:7])}月{int(day.date[8:10])}日"
    body = (
        f'<h1 class="sr-only">{C.esc(h1)}</h1>'
        f'<p class="site-disclaimer">{C.esc(cfg.disclaimer)}</p>'
        f'<div class="v4-filter-bar">'
        f'<div class="v4-date">📅 {date_lab}（{len(ms)}场）</div>'
        f'<div class="v4-filter-btn">🔍 {C.esc("、".join(leagues)) or "筛选"}</div>'
        f"</div>"
        f'<p class="sub">{C.esc(desc)}</p>'
        f"{filter_css}{filter_bar}"
        f'<div class="cards">{cards}</div>'
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
