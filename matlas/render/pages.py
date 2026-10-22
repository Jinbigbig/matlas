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

    teams_row = (
        f'<h1 class="match-teams">'
        f'<span class="home">{C.esc(m.home.name)}</span>'
        f'<span class="vs">VS</span>'
        f'<span class="away">{C.esc(m.away.name)}</span>'
        f"</h1>"
    )
    header = C.card_header(
        match_id=m.code or m.match_id,
        league=m.competition,
        time_=m.kickoff,
        extra=C.confidence_badge(m.confidence, settled),
    )
    body_parts = [
        '<div class="card">',
        teams_row,
        f'<p class="sub" style="text-align:center">{C.esc(meta)}{cold}{sample}</p>',
        header,
        "</div>",
        _picks(m),
        _charts_panel(m),
        _odds_panel(m),
        _standings_panel(m),
        _h2h_panel(m),
        _form_panel(m),
        _injury_panel(m),
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


def _card(cfg: Config, m: Match, *, pre: str = "") -> str:
    url = f"{pre}matches/{m.match_id}.html"
    times = m.kickoff[-5:] if m.kickoff else ""
    picks = []
    hd = m.headline
    rename = {"direction": "方向", "score": "比分", "goals": "进球", "htft": "半全"}
    for kind in ("direction", "score", "goals", "htft"):
        f = hd.get(kind)
        if not f:
            continue
        picks.append(
            f'<span class="mini">{rename[kind]} {C.esc(f.label)}</span> {C.prob_tag(f.prob)}'
        )
    score = ""
    if m.result and m.result.full_score:
        score = f'<div class="card-score">赛果 {C.esc(m.result.full_score)}</div>'
    teams = (
        f'<div class="match-teams">'
        f'<span class="home">{C.esc(m.home.name)}</span>'
        f'<span class="vs">VS</span>'
        f'<span class="away">{C.esc(m.away.name)}</span>'
        f"</div>"
    )
    return (
        f'<a class="card" href="{url}">'
        + C.card_header(
            match_id=m.code or m.match_id,
            league=m.competition,
            time_=times,
            extra=C.confidence_badge(m.confidence, m.result.direction_hit if m.result else None),
        )
        + teams
        + score
        + f'<div class="card-picks">{"".join(picks)}</div>'
        + "</a>"
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
    desc = (
        f"{day.date} 共 {len(ms)} 场赛事的结构化量化数据与结论，"
        f"含 {C.esc('、'.join(sorted({m.competition for m in ms if m.competition})))}。"
    )
    cards = "".join(_card(cfg, m, pre="" if is_today else "../") for m in ms) or "<p>当日无赛事数据。</p>"
    if day.note:
        cards = f'<p class="sub">{C.esc(day.note)}</p>' + cards
    body = (
        f"<h1>{C.esc(h1)}</h1>"
        f'<p class="sub">{C.esc(desc)}</p>'
        f'<div class="cards">{cards}</div>'
        f'<p class="disclaimer">{C.esc(cfg.disclaimer)}</p>'
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
