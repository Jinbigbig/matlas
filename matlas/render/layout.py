"""页面外壳：CSS + head（含 JSON-LD）+ 页头页脚。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..config import Config
from ..models import SCHEMA_VERSION
from . import components as C

_CSS = """
/* 设计变量与 jinbet 报告页完全同源（--bg/--ink/--accent/--home/--away 等），
   改这里就等于改两边的观感，避免出现两套设计语言。 */
:root {
  --bg: #f0f2f5; --bg2: #ffffff; --ink: #1a1a2e; --muted: #6c757d; --rule: #dee2e6;
  --accent: #e63946; --accent2: #2a9d8f; --accent3: #f4a261;
  --win: #2a9d8f; --draw: #f4a261; --loss: #e63946;
  --home: #457b9d; --away: #e76f51; --text-muted: #6c757d;
}
*,*::before,*::after { box-sizing: border-box; margin: 0; padding: 0; }
html { -webkit-text-size-adjust: 100%; scroll-behavior: smooth; }
body {
  background: var(--bg); color: var(--ink); line-height: 1.7; min-height: 100vh;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue',
    Arial, 'PingFang SC', 'Microsoft YaHei', sans-serif; font-size: 15px;
}
a { color: var(--accent2); text-decoration: none; }
a:hover { text-decoration: underline; }
.wrap { max-width: 1080px; margin: 0 auto; padding: 0 1.5rem; }
main.wrap { padding-bottom: 2.5rem; }

/* ---------- 页头：jinbet hero 同款深色渐变 ---------- */
header.site {
  background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
  color: #fff; position: relative; overflow: hidden;
}
header.site::before {
  content: ''; position: absolute; inset: 0;
  background: radial-gradient(circle at 20% 50%, rgba(230,57,70,0.15) 0%, transparent 50%),
              radial-gradient(circle at 80% 50%, rgba(42,157,143,0.15) 0%, transparent 50%);
}
header.site .wrap { position: relative; z-index: 1; padding-top: 1rem; padding-bottom: 1rem;
  display: flex; align-items: center; gap: 1rem; flex-wrap: wrap; }
.brand { font-weight: 700; font-size: 1.15rem; letter-spacing: -0.01em; }
.brand span { font-weight: 400; color: rgba(255,255,255,0.65); font-size: 0.78rem; margin-left: 0.5rem; }
nav.site { margin-left: auto; display: flex; gap: 1.1rem; font-size: 0.85rem; }
nav.site a { color: rgba(255,255,255,0.75); }
nav.site a:hover { color: #fff; }

/* ---------- 标题层级 ---------- */
main .wrap > h1 { font-weight: 700; font-size: 1.7rem; letter-spacing: -0.02em;
  margin: 2rem 0 0.35rem; }
h2 { font-weight: 700; font-size: 1.5rem; margin: 2.5rem 0 1.25rem; padding-bottom: 0.5rem;
  border-bottom: 3px solid var(--accent); display: inline-block; }
h3 { font-weight: 700; font-size: 1.15rem; margin: 1.5rem 0 0.75rem; }
h4 { font-size: 0.85rem; font-weight: 600; color: var(--muted); text-transform: uppercase;
  letter-spacing: 0.05em; margin: 1rem 0 0.5rem; }
.sub { color: var(--muted); font-size: 0.85rem; margin: 0 0 1.25rem; }
.rank-tag { font-size: 0.55em; color: var(--text-muted); vertical-align: sub;
  margin-left: 2px; opacity: 0.7; }

/* ---------- 卡片 ---------- */
.card { background: var(--bg2); border-radius: 10px; padding: 1.25rem 1.5rem;
  margin-bottom: 1.25rem; box-shadow: 0 1px 3px rgba(0,0,0,0.06), 0 1px 2px rgba(0,0,0,0.04);
  border: 1px solid var(--rule); display: block; color: inherit; }
a.card:hover { border-color: var(--accent2); text-decoration: none; }
.card-header { display: flex; align-items: center; justify-content: space-between;
  flex-wrap: wrap; gap: 0.75rem; margin-bottom: 1rem; padding-bottom: 0.75rem;
  border-bottom: 1px solid var(--rule); font-size: 0.8rem; color: var(--muted); }
.card-header .match-id { font-family: 'SFMono-Regular', Consolas, monospace; font-size: 0.78rem;
  color: var(--muted); background: var(--bg); padding: 0.2rem 0.6rem; border-radius: 4px; }
.card-header .match-league { font-size: 0.78rem; font-weight: 600; color: var(--accent);
  text-transform: uppercase; letter-spacing: 0.05em; }
.card-header .match-time { font-family: 'SFMono-Regular', Consolas, monospace;
  font-size: 0.82rem; color: var(--muted); }
.match-teams { display: flex; align-items: center; justify-content: center; gap: 1rem;
  margin: 0.75rem 0; font-size: 1.3rem; font-weight: 700; }
.match-teams .vs { font-family: 'SFMono-Regular', Consolas, monospace; font-size: 0.82rem;
  color: var(--muted); background: var(--bg); padding: 0.3rem 0.8rem; border-radius: 20px;
  font-weight: 400; }
/* 队徽：Team.logo 有值才出现，没有就只剩文字，不留占位框 */
.match-teams .tm { display: inline-flex; align-items: center; gap: 0.5rem; min-width: 0;
  overflow-wrap: anywhere; }
.crest { width: 32px; height: 32px; object-fit: contain; flex: none; }
h1.match-teams .crest { width: 40px; height: 40px; }
.match-teams .home { color: var(--home); }
.match-teams .away { color: var(--away); }
h1.match-teams { justify-content: center; gap: 1rem; margin: 0.5rem 0 0.25rem; }
.card-score { font-family: 'SFMono-Regular', Consolas, monospace; font-size: 0.85rem;
  color: var(--ink); text-align: center; }
.card-score .half { color: var(--muted); font-size: 0.92em; }

/* ---------- 面板 / 洞察 ---------- */
.panel { background: var(--bg2); border-radius: 10px; padding: 1.25rem 1.5rem; margin: 1.25rem 0;
  box-shadow: 0 1px 3px rgba(0,0,0,0.06), 0 1px 2px rgba(0,0,0,0.04); border: 1px solid var(--rule); }
.panel > h3:first-child { margin-top: 0; }
.panel-hint { color: var(--muted); font-size: 0.8rem; margin: 0.25rem 0 0.75rem; }
.insight-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 0.75rem; margin: 0.75rem 0; }
.insight-card { background: var(--bg); padding: 0.75rem 1rem; border-radius: 8px;
  border-left: 3px solid var(--accent); }
.insight-card .insight-label { font-size: 0.72rem; color: var(--muted); text-transform: uppercase;
  letter-spacing: 0.04em; margin-bottom: 0.2rem; }
.insight-card .insight-value { font-size: 0.95rem; font-weight: 600; color: var(--ink); }

/* ---------- 赔率 ---------- */
.odds-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 0.75rem; margin: 0.75rem 0; }
.odds-item { text-align: center; padding: 0.75rem 0.5rem; background: var(--bg); border-radius: 8px; }
.odds-item .label { font-size: 0.75rem; color: var(--muted); margin-bottom: 0.25rem; }
.odds-item .value { font-family: 'SFMono-Regular', Consolas, monospace; font-size: 1.3rem; font-weight: 700; }
.odds-item .value.win { color: var(--win); }
.odds-item .value.draw { color: var(--draw); }
.odds-item .value.loss { color: var(--loss); }

/* ---------- 表格 ---------- */
.tw { overflow-x: auto; margin: 0.75rem 0; border-radius: 8px; border: 1px solid var(--rule); }
table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
thead th { background: var(--bg); font-weight: 600; font-size: 0.78rem; text-transform: uppercase;
  letter-spacing: 0.04em; color: var(--muted); padding: 0.6rem 0.75rem; text-align: left;
  border-bottom: 2px solid var(--rule); }
tbody td { padding: 0.55rem 0.75rem; border-bottom: 1px solid var(--rule); }
tbody tr:last-child td { border-bottom: none; }
tbody tr:hover { background: rgba(0,0,0,0.02); }
td:first-child { color: var(--muted); white-space: nowrap; }
table.duo td:not(:first-child) { font-variant-numeric: tabular-nums; }
.history-table td { padding: 0.4rem 0.6rem; }

/* ---------- 近况圆点：与 jinbet form-dot 同名同色 ---------- */
.form-row { display: flex; gap: 0.35rem; align-items: center; flex-wrap: wrap; }
.form-dot { width: 22px; height: 22px; border-radius: 50%; display: inline-flex;
  align-items: center; justify-content: center; font-size: 0.65rem; font-weight: 700; color: #fff; }
.form-dot.w { background: var(--win); }
.form-dot.d { background: var(--draw); }
.form-dot.l { background: var(--loss); }

/* ---------- 概率与评级 ---------- */
.pct { display: inline-block; font-variant-numeric: tabular-nums; font-size: 0.82rem;
  padding: 0.1rem 0.45rem; border-radius: 4px; font-weight: 600; }
.p-hi { background: rgba(42,157,143,0.12); color: var(--win); }
.p-mid { background: rgba(244,162,97,0.14); color: #b4700f; }
.p-lo { background: rgba(108,117,125,0.1); color: var(--muted); }
.badge { display: inline-block; font-size: 0.75rem; padding: 0.15rem 0.5rem; border-radius: 4px;
  font-weight: 600; vertical-align: middle; }
.hit { display: inline-block; font-size: 0.75rem; padding: 0.15rem 0.5rem; border-radius: 4px;
  font-weight: 600; margin-left: 0.35rem; vertical-align: middle; }
.hit-y { background: rgba(42,157,143,0.12); color: var(--win); }
.hit-n { background: rgba(230,57,70,0.1); color: var(--loss); }
.tag { display: inline-block; padding: 0.15rem 0.5rem; border-radius: 4px; font-size: 0.75rem;
  font-weight: 600; }
.tag-green { background: rgba(42,157,143,0.12); color: var(--win); }
.tag-red { background: rgba(230,57,70,0.1); color: var(--loss); }
.tag-yellow { background: rgba(244,162,97,0.12); color: var(--draw); }
.tag-blue { background: rgba(69,123,157,0.1); color: var(--home); }
.mini { display: inline-block; font-size: 0.75rem; color: var(--muted); border: 1px solid var(--rule);
  border-radius: 4px; padding: 0.05rem 0.45rem; }

/* ---------- 主推条：整页第一视觉重心 ---------- */
.mainpick { display: flex; align-items: center; gap: 0.9rem; flex-wrap: wrap;
  background: linear-gradient(135deg, #1a1a2e 0%, #16213e 60%, #0f3460 100%);
  color: #fff; border-radius: 10px; padding: 0.9rem 1.25rem; margin: 1rem 0;
  box-shadow: 0 2px 10px rgba(26,26,46,0.18); }
.mainpick .mp-lab { font-size: 0.7rem; font-weight: 700; letter-spacing: 0.12em;
  text-transform: uppercase; color: rgba(255,255,255,0.55);
  border-right: 1px solid rgba(255,255,255,0.2); padding-right: 0.9rem; }
.mainpick .mp-txt { font-size: 1rem; font-weight: 600; line-height: 1.5; flex: 1; min-width: 200px; }
.mainpick .mp-tag { display: inline-flex; align-items: center; gap: 0.4rem; }

/* ---------- 风险提示：三档色条 ---------- */
.risk-note { display: flex; align-items: flex-start; gap: 0.75rem; flex-wrap: wrap;
  border-radius: 8px; padding: 0.7rem 1rem; margin: 0.75rem 0; font-size: 0.85rem;
  border-left: 3px solid var(--rule); background: var(--bg); }
.risk-note .risk-lab { font-size: 0.7rem; font-weight: 700; letter-spacing: 0.08em;
  padding: 0.1rem 0.5rem; border-radius: 4px; white-space: nowrap; }
.risk-note .risk-txt { flex: 1; min-width: 180px; }
.risk-note .risk-factors { margin: 0.3rem 0 0; padding-left: 1.1rem; color: var(--muted); }
.risk-note .risk-factors li { line-height: 1.6; }
.r-info { border-left-color: var(--home); }
.r-info .risk-lab { background: rgba(69,123,157,0.12); color: var(--home); }
.r-warn { border-left-color: var(--accent3); background: rgba(244,162,97,0.08); }
.r-warn .risk-lab { background: rgba(244,162,97,0.18); color: #b4700f; }
.r-block { border-left-color: var(--accent); background: rgba(230,57,70,0.06); }
.r-block .risk-lab { background: rgba(230,57,70,0.12); color: var(--accent); }

/* ---------- 外部对照表 ---------- */
table.ref-table td:not(:first-child) { font-variant-numeric: tabular-nums; }
table.ref-table td:nth-child(3) { color: var(--muted); }
table.ref-table .hit { margin-left: 0.25rem; }

/* ---------- 结论四宫格 ---------- */
.prediction { background: linear-gradient(135deg, rgba(42,157,143,0.08), rgba(42,157,143,0.02));
  border: 1px solid rgba(42,157,143,0.2); border-radius: 10px; padding: 1rem 1.25rem; margin: 1rem 0; }
.prediction .pred-title { font-size: 0.8rem; font-weight: 600; color: var(--accent2);
  text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 0.5rem; }
.picks4 { display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 0.75rem; }
.pick { background: var(--bg2); border: 1px solid rgba(42,157,143,0.25); border-radius: 8px;
  padding: 0.75rem 0.9rem; }
.pick .lab { font-size: 0.75rem; color: var(--muted); }
.pick .val { font-family: 'SFMono-Regular', Consolas, monospace; font-size: 1.25rem; font-weight: 700;
  color: var(--accent); margin: 0.25rem 0; }

/* ---------- 图表 ---------- */
.legend { display: flex; gap: 1.1rem; flex-wrap: wrap; font-size: 0.8rem; color: var(--muted);
  margin: 0.25rem 0 0.5rem; }
.legend span { display: inline-flex; align-items: center; gap: 0.35rem; }
.legend i { width: 11px; height: 11px; border-radius: 3px; display: inline-block; }
svg.radar, svg.mom { width: 100%; height: auto; display: block; margin-top: 0.25rem; }
svg.radar { max-width: 340px; }
svg.mom { max-width: 620px; }

/* ---------- 列表网格 ---------- */
.cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 1rem; }
.cards .card { margin-bottom: 0; }
.card-picks { display: flex; flex-wrap: wrap; gap: 0.4rem; margin-top: 0.75rem; font-size: 0.8rem;
  color: var(--muted); }

/* ---------- 置信度条 ---------- */
.conf-bar { display: flex; align-items: center; gap: 0.5rem; margin: 0.5rem 0; }
.bar-track { flex: 1; height: 8px; background: var(--bg); border-radius: 4px; overflow: hidden; }
.bar-fill { height: 100%; background: linear-gradient(90deg, var(--accent2), var(--accent3));
  border-radius: 4px; }
.bar-label { font-size: 0.8rem; color: var(--muted); }

/* ---------- 提示与页脚 ---------- */
.warning { background: rgba(244,162,97,0.1); border: 1px solid rgba(244,162,97,0.3);
  border-radius: 8px; padding: 0.75rem 1rem; margin: 0.75rem 0; font-size: 0.85rem; color: #d35400; }
.ledger { background: var(--bg2); border: 1px dashed var(--rule); border-radius: 10px;
  padding: 1rem 1.25rem; margin: 1.25rem 0; font-size: 0.8rem; color: var(--muted); }
.ledger code { font-family: 'SFMono-Regular', Consolas, monospace; background: var(--bg);
  padding: 0.1rem 0.4rem; border-radius: 4px; color: var(--ink); }
.disclaimer { background: var(--bg2); border-left: 3px solid var(--rule); padding: 0.6rem 1rem;
  color: var(--muted); font-size: 0.8rem; margin: 1.5rem 0; }
footer.site { background: var(--bg2); border-top: 1px solid var(--rule); padding: 1.5rem 0;
  margin-top: 2.5rem; text-align: center; font-size: 0.8rem; color: var(--muted); }

@media (max-width: 768px) {
  .wrap { padding: 0 1rem; }
  main .wrap > h1 { font-size: 1.35rem; }
  .match-teams { font-size: 1.05rem; gap: 0.6rem; }
  .odds-grid { gap: 0.5rem; }
  .cards { grid-template-columns: 1fr; }
  .mainpick { flex-direction: column; align-items: flex-start; gap: 0.5rem; }
  .mainpick .mp-lab { border-right: none; border-bottom: 1px solid rgba(255,255,255,0.2);
    padding: 0 0 0.35rem; }
}

/* 平板竖屏 / 大屏手机：四宫格降到两列，面板内边距收紧 */
@media (max-width: 640px) {
  .picks4 { grid-template-columns: repeat(2, 1fr); }
  .insight-grid { grid-template-columns: 1fr; }
  .pick .val { font-size: 1.1rem; }
  .card, .panel { padding: 1rem 0.9rem; }
  .odds-item .value { font-size: 1.1rem; }
  .match-teams { font-size: 1rem; }
  .crest { width: 26px; height: 26px; }
  h1.match-teams .crest { width: 34px; height: 34px; }
  svg.radar { max-width: 100%; }
  .mainpick .mp-txt { font-size: 0.92rem; }
  table { font-size: 0.8rem; }
  thead th, tbody td { padding: 0.45rem 0.5rem; }
}

/* 小屏手机：四宫格单列，页头副标题让位给导航 */
@media (max-width: 480px) {
  .wrap { padding: 0 0.75rem; }
  main .wrap > h1 { font-size: 1.15rem; }
  .picks4 { grid-template-columns: 1fr; }
  .odds-grid { gap: 0.35rem; }
  .odds-item { padding: 0.55rem 0.25rem; }
  .odds-item .value { font-size: 1rem; }
  .match-teams { font-size: 0.92rem; gap: 0.4rem; }
  .crest { width: 22px; height: 22px; }
  h1.match-teams .crest { width: 28px; height: 28px; }
  .brand span { display: none; }
  .card-header { gap: 0.4rem; font-size: 0.75rem; }
  nav.site { gap: 0.7rem; font-size: 0.78rem; }
  .form-dot { width: 18px; height: 18px; font-size: 0.6rem; }
  .risk-note { padding: 0.6rem 0.75rem; }
  .legend { gap: 0.7rem; font-size: 0.72rem; }
}
"""


def _write_style(cfg: Config) -> None:
    s = cfg.out_dir / "assets"
    s.mkdir(parents=True, exist_ok=True)
    (s / "style.css").write_text(_CSS.strip() + "\n", encoding="utf-8")


def _jsonld(blocks: list[dict[str, Any]]) -> str:
    if not blocks:
        return ""
    body = "\n".join(
        '<script type="application/ld+json">'
        + json.dumps(b, ensure_ascii=False, indent=None, separators=(",", ":"))
        + "</script>"
        for b in blocks
    )
    return body


def page(
    cfg: Config,
    *,
    title: str,
    description: str,
    body: str,
    canonical: str,
    jsonld: list[dict[str, Any]] | None = None,
    nav_day: str = "",
    depth: int = 0,
) -> str:
    """页面外壳。

    `depth` 用于算相对前缀：站点可能挂在域名子路径下（/matlas/），
    用相对路径比绝对 URL 更稳 —— 本地 file:// 预览同样能加载样式。
    canonical / og 仍输出绝对 URL 供搜索引擎识别。
    """
    _write_style(cfg)
    base = cfg.base_url.rstrip("/")
    pre = "../" * depth
    home = pre or "./"
    nav_extra = f'<a href="{pre}days/{nav_day}.html">当日归档</a>' if nav_day else ""
    head_title = title if title.endswith(cfg.site_name) else f"{title} - {cfg.site_name}"
    return f"""<!DOCTYPE html>
<html lang="{cfg.language}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{C.esc(head_title)}</title>
<meta name="description" content="{C.esc(description)}">
<link rel="canonical" href="{C.esc(canonical)}">
<link rel="stylesheet" href="{pre}assets/style.css">
<meta property="og:type" content="article">
<meta property="og:title" content="{C.esc(head_title)}">
<meta property="og:description" content="{C.esc(description)}">
<meta name="robots" content="index,follow">
{_jsonld(jsonld or [])}
</head>
<body>
<header class="site"><div class="wrap">
  <div class="brand">{C.esc(cfg.site_name)}<span>{C.esc(cfg.site_tagline)}</span></div>
  <nav class="site">
    <a href="{home}">今日</a>
    <a href="{pre}days/">归档</a>
    {nav_extra}
    <a href="{pre}llms.txt">llms.txt</a>
  </nav>
</div></header>
<main class="wrap">
{body}
</main>
<footer class="site"><div class="wrap">
  <p>{C.esc(cfg.site_name)} · {C.esc(cfg.site_tagline)}　{C.esc(cfg.disclaimer)}</p>
  <p>数据契约 v{SCHEMA_VERSION} · 全部历史可被哈希指纹核验，结论不做事后修改。</p>
</div></footer>
</body>
</html>
"""


def write(cfg: Config, rel: str, content: str) -> Path:
    p = cfg.out_dir / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p
