"""页面外壳：CSS + head（含 JSON-LD）+ 页头页脚。"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from ..config import Config
from ..models import SCHEMA_VERSION  # noqa: F401  （llms.txt 出口仍引用）
from . import components as C

# CSS 版本号：每次构建变化 → style.css 引用带 ?v=，部署后浏览器不再吃旧缓存
# （此前筛选面板的联动修复因 Pages 10 分钟 CSS 缓存迟迟不生效）
_CSS_VER = str(int(time.time()))

_CSS = """
/* 配色直接对齐 qiuxiaoce.com：Tailwind 标准色板（blue-600 / emerald-500 /
   amber-500 / red-600 / gray 系列），底色 #f5f7fa，卡片 8–12px 圆角。 */
:root {
  --bg: #f5f7fa; --bg2: #ffffff; --ink: #111111; --muted: #6b7280; --rule: #e5e7eb;
  --accent: #2563eb; --accent2: #10b981; --accent3: #f59e0b;
  --win: #10b981; --draw: #f59e0b; --loss: #dc2626;
  --home: #2563eb; --away: #f59e0b; --text-muted: #6b7280;
  --gray-50: #f9fafb; --gray-100: #f3f4f6; --gray-200: #e5e7eb;
  --gray-500: #6b7280; --gray-700: #374151;
  --blue-50: #eff6ff;
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
.wrap { max-width: 1200px; margin: 0 auto; padding: 0 1.5rem; }
main.wrap { padding-bottom: 2.5rem; }
/* 只给读屏和搜索引擎的文本（视觉标题用 mc-teams 表达） */
.sr-only { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px;
  overflow: hidden; clip: rect(0,0,0,0); white-space: nowrap; border: 0; }

/* ---------- 提示条与筛选条：对齐 qiuxiaoce 首页 ---------- */
.site-disclaimer { background: #fff1f2; border: 1px solid #fecdd3; color: #9f1239;
  padding: 8px 12px; font-size: 12px; line-height: 1.5; border-radius: 8px;
  margin: 1rem 0 10px; }
.v4-filter-bar { display: flex; justify-content: space-between; align-items: center;
  background: #fff; border-radius: 10px; padding: 10px 14px; gap: 0.75rem;
  box-shadow: 0 1px 3px rgba(0,0,0,0.06); margin-bottom: 12px; }
.v4-date { font-weight: 700; color: #111; font-size: 15px; }
/* 展开式筛选面板：对齐 qiuxiaoce 的 #filter-panel（类型/赛事两行） */
.fp-toggle { position: absolute; opacity: 0; width: 0; height: 0; }
.filter-panel { display: none; background: #fff; border: 1px solid var(--rule);
  border-radius: 8px; padding: 12px 14px; margin: 0 0 12px; }
body:has(#fp-toggle:checked) #filter-panel { display: block; }
.v4-filter-btn { display: flex; align-items: center; gap: 4px; background: #fff;
  border: 1px solid #e5e7eb; padding: 6px 12px; border-radius: 20px; font-size: 13px;
  color: #4b5563; white-space: nowrap; cursor: pointer; }
.v4-filter-btn:hover { color: var(--accent); border-color: #93c5fd; }
.fp-row { display: flex; align-items: flex-start; gap: 10px; }
.fp-row + .fp-row { margin-top: 10px; }
.fp-label { font-size: 13px; color: #6b7280; flex: none; line-height: 28px; }
.fp-options { display: flex; gap: 8px; flex-wrap: wrap; }
.fp-radio { position: absolute; opacity: 0; width: 0; height: 0; }
.fp-opt { font-size: 13px; padding: 4px 14px; border-radius: 6px; border: 1px solid #e5e7eb;
  background: #fff; color: #4b5563; cursor: pointer; transition: all 0.15s;
  display: inline-block; text-decoration: none; }
.fp-opt:hover { border-color: #93c5fd; color: var(--accent); text-decoration: none; }
a.fp-opt.active { background: var(--accent); color: #fff; border-color: var(--accent); }
/* 行内 SVG 图标与文字对齐（顶导/卡片头/筛选条统一走这条） */
.card-header svg, .v4-date svg, .v4-filter-btn svg, .feat-ico svg, .page-h1 svg,
.me-avatar svg, .fp-label svg { flex: none; }
.card-header svg { vertical-align: -3px; }
.page-h1 svg { vertical-align: -3px; margin-right: 2px; }
.v4-date svg { vertical-align: -2.5px; margin-right: 2px; }
.v4-filter-btn svg { vertical-align: -2.5px; margin-right: 2px; }
.v4-nav-icon svg { width: 20px; height: 20px; }
.fp-radio:checked + .fp-opt { background: var(--accent); color: #fff; border-color: var(--accent); }
.fp-radio:focus-visible + .fp-opt { outline: 2px solid #93c5fd; outline-offset: 2px; }
/* 时间行：原生下拉（optgroup 按月分组），日期数量再大也不占版面；
   筛选条上另有 ‹ › 箭头做前后翻日。appearance 去掉系统样式，自绘箭头。
   .ai-date-select 是 AI 卡内同款（值是 radio id，由全局 JS 切换，不跳转） */
.date-select, .ai-date-select { appearance: none; -webkit-appearance: none;
  font-size: 13px;
  color: #111; background: #fff
  url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6' viewBox='0 0 10 6'%3E%3Cpath d='M1 1l4 4 4-4' fill='none' stroke='%236b7280' stroke-width='1.6' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E")
  no-repeat right 11px center;
  border: 1px solid #e5e7eb; border-radius: 8px; padding: 6px 30px 6px 12px;
  cursor: pointer; max-width: 260px; font-family: inherit; }
.date-select:hover, .ai-date-select:hover { border-color: #93c5fd; color: var(--accent); }
.date-select:focus-visible, .ai-date-select:focus-visible {
  outline: 2px solid #93c5fd; outline-offset: 2px; }
.v4-date-nav { display: flex; align-items: center; gap: 8px; min-width: 0; }
.v4-day-arrow { display: flex; align-items: center; justify-content: center;
  width: 26px; height: 26px; border-radius: 50%; border: 1px solid #e5e7eb;
  background: #fff; color: #4b5563; font-size: 15px; line-height: 1;
  text-decoration: none; flex: none; }
.v4-day-arrow:hover { color: var(--accent); border-color: #93c5fd; text-decoration: none; }
.v4-day-arrow.off { opacity: 0.35; pointer-events: none; }
.note-line { color: #9ca3af; font-size: 12px; margin: -4px 0 10px; }

/* ---------- 独立页面：数据统计 / 功能 / 我的 ---------- */
.stats-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin: 16px 0; }
.stat-card { background: #fff; border: 1px solid var(--rule); border-radius: 10px;
  padding: 18px 12px; text-align: center; }
.stat-num { font-size: 1.6rem; font-weight: 800; color: var(--accent); }
.stat-lbl { font-size: 12px; color: #6b7280; margin-top: 4px; }
.plain-list { margin: 10px 0 0 1.2em; }
.plain-list li { margin: 6px 0; }
.feat-list { list-style: none; margin: 14px 0; padding: 0; display: grid; gap: 10px; }
.feat-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; margin: 14px 0; }
.feat-item { display: flex; align-items: flex-start; gap: 12px; background: #fff;
  border: 1px solid var(--rule); border-radius: 10px; padding: 16px;
  text-decoration: none; transition: border-color 0.15s, box-shadow 0.15s; }
a.feat-item:hover { border-color: #93c5fd; box-shadow: 0 2px 8px rgba(37, 99, 235, 0.08);
  text-decoration: none; }
.feat-ico { width: 38px; height: 38px; flex: none; border-radius: 10px; background: #eff6ff;
  color: var(--accent); display: inline-flex; align-items: center; justify-content: center; }
.feat-ico svg { width: 20px; height: 20px; }
.feat-txt { min-width: 0; }
.feat-name { font-weight: 700; font-size: 15px; color: #111; display: block; }
.feat-desc { font-size: 13px; color: #6b7280; margin-top: 4px; display: block; }
a.feat-item .feat-go { font-size: 13px; color: var(--accent); margin-top: 8px; display: block; }
.me-card { background: #fff; border: 1px solid var(--rule); border-radius: 12px;
  padding: 32px 20px; text-align: center; max-width: 480px; margin: 20px auto; }
.me-avatar { width: 68px; height: 68px; margin: 0 auto; border-radius: 50%;
  background: #eff6ff; color: var(--accent); display: flex; align-items: center;
  justify-content: center; }
.me-avatar svg { width: 34px; height: 34px; }
.me-card h2 { margin: 10px 0 6px; }
@media (max-width: 640px) { .stats-grid { grid-template-columns: repeat(2, 1fr); } }

/* ---------- 页头：白底 + 左 logo + 右上功能按钮，同 qiuxiaoce 的 header ---------- */
header.site {
  background: #fff; color: var(--ink); position: relative; z-index: 99;
  padding: 22px 0 18px; margin-bottom: 20px;
  box-shadow: 0 1px 5px rgba(0,0,0,0.06);
}
header.site .wrap { position: relative; z-index: 1;
  display: flex; align-items: center; gap: 1rem; flex-wrap: wrap; }
.brand { font-weight: 800; font-size: 1.3rem; letter-spacing: -0.02em; color: var(--accent);
  display: flex; align-items: center; gap: 7px; }
.brand .brand-mark { width: 30px; height: 30px; border-radius: 8px;
  background: linear-gradient(135deg, #2563eb, #1d4ed8); color: #fff;
  display: inline-flex; align-items: center; justify-content: center;
  font-size: 15px; font-weight: 800; letter-spacing: -0.03em; flex: none; }
.brand span { font-weight: 400; color: #6b7280; font-size: 0.75rem; margin-left: 2px; }
nav.site { margin-left: auto; display: flex; align-items: center; gap: 0.35rem;
  font-size: 0.86rem; }
nav.site a { color: #4b5563; padding: 6px 10px; border-radius: 8px; white-space: nowrap;
  display: inline-flex; align-items: center; gap: 5px; }
nav.site a svg { flex: none; }
nav.site a:hover { color: var(--accent); background: #eff6ff; text-decoration: none; }
nav.site a.is-btn, nav.site a.is-icon, nav.site label.is-icon { border: none; }
nav.site label.is-icon { display: inline-flex; align-items: center; cursor: pointer; color: #4b5563; padding: 6px 9px; }
/* 回顶部：滚过一屏后出现，右下角悬浮（对方同款交互） */
.back-top { position: fixed; right: 22px; bottom: 90px; z-index: 90; width: 42px; height: 42px;
  border-radius: 50%; background: #fff; color: #4b5563; border: 1px solid var(--rule);
  box-shadow: 0 2px 8px rgba(0,0,0,0.12); display: none; align-items: center;
  justify-content: center; cursor: pointer; text-decoration: none; }
.back-top.show { display: inline-flex; }
.back-top:hover { color: var(--accent); border-color: #93c5fd; }
@media (max-width: 768px) { .back-top { right: 14px; bottom: 76px; } }
nav.site label.is-icon:hover { color: var(--accent); background: #eff6ff; }
/* 「功能」下拉菜单：悬停/键盘聚焦展开，收纳赔率与投注（盘口 / 记录本） */
.nav-drop { position: relative; }
.nav-drop .nav-menu { display: none; position: absolute; top: 100%; right: 0;
  background: #fff; border: 1px solid #eef2f7; border-radius: 10px;
  box-shadow: 0 6px 18px rgba(15,23,42,0.10); padding: 6px; min-width: 128px;
  z-index: 60; }
.nav-drop:hover .nav-menu, .nav-drop:focus-within .nav-menu { display: block; }
.nav-menu a { display: flex; align-items: center; gap: 6px; padding: 8px 12px;
  border-radius: 8px; font-size: 13px; color: #374151; white-space: nowrap; }
.nav-menu a svg { width: 14px; height: 14px; flex: none; color: #94a3b8; }
.nav-menu a:hover { background: #f1f5f9; color: var(--accent); text-decoration: none; }
.nav-menu a:hover svg { color: var(--accent); }
/* 搜索滑出层：checkbox hack，零 JS（对齐 qiuxiaoce 的 .site-search） */
.ss-toggle { position: absolute; opacity: 0; width: 0; height: 0; }
.site-search { display: none; background: #fff; border-bottom: 1px solid var(--rule);
  padding: 14px 0; }
body:has(.ss-toggle:checked) .site-search { display: block; }
.site-search-form { display: flex; gap: 8px; }
.search-input { flex: 1; border: 1px solid var(--rule); border-radius: 8px;
  padding: 9px 14px; font-size: 14px; outline: none; }
.search-input:focus { border-color: var(--accent); box-shadow: 0 0 0 3px #dbeafe; }
.search-btn { border: none; background: var(--accent); color: #fff; border-radius: 8px;
  padding: 0 18px; cursor: pointer; display: inline-flex; align-items: center; }
.search-btn:hover { background: #1d4ed8; }

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
/* 单场页顶部整块沿用列表卡片的外观：无内边距，头部/主体各自带边距 */
.card-match { padding: 0; overflow: hidden; border-radius: 12px; margin-top: 1.25rem; }
.card-match .mc-teams { margin: 0.15rem 0 0; }
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
.mc-team .crest { width: 48px; height: 48px; }
/* 无队徽时的同尺寸圆形占位：取队名首字，保证卡片高度整齐 */
.crest-ph { border-radius: 50%; background: #f3f4f6; color: #9ca3af;
  display: flex; align-items: center; justify-content: center;
  font-size: 18px; font-weight: 700; line-height: 1; }
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
.p-hi { background: rgba(16,185,129,0.12); color: var(--win); }
.p-mid { background: rgba(245,158,11,0.14); color: #b45309; }
.p-lo { background: rgba(107,114,128,0.1); color: var(--muted); }
.badge { display: inline-block; font-size: 0.75rem; padding: 0.15rem 0.5rem; border-radius: 4px;
  font-weight: 600; vertical-align: middle; }
.hit { display: inline-block; font-size: 0.75rem; padding: 0.15rem 0.5rem; border-radius: 4px;
  font-weight: 600; margin-left: 0.35rem; vertical-align: middle; }
.hit-y { background: rgba(16,185,129,0.12); color: var(--win); }
.hit-n { background: rgba(220,38,38,0.1); color: var(--loss); }
.tag { display: inline-block; padding: 0.15rem 0.5rem; border-radius: 4px; font-size: 0.75rem;
  font-weight: 600; }
.tag-green { background: rgba(16,185,129,0.12); color: var(--win); }
.tag-red { background: rgba(220,38,38,0.1); color: var(--loss); }
.tag-yellow { background: rgba(245,158,11,0.12); color: var(--draw); }
.tag-blue { background: rgba(37,99,235,0.1); color: var(--home); }
.mini { display: inline-block; font-size: 0.75rem; color: var(--muted); border: 1px solid var(--rule);
  border-radius: 4px; padding: 0.05rem 0.45rem; }

/* ---------- 主推条：对齐对方的浅蓝结论块（#eff6ff + 蓝字） ---------- */
.mainpick { display: flex; align-items: center; gap: 0.9rem; flex-wrap: wrap;
  background: var(--blue-50); color: var(--ink); border: 1px solid #bfdbfe;
  border-radius: 12px; padding: 0.9rem 1.25rem; margin: 1rem 0;
  box-shadow: 0 1px 2px rgba(0,0,0,0.02); }
.mainpick .mp-lab { font-size: 0.7rem; font-weight: 700; letter-spacing: 0.12em;
  text-transform: uppercase; color: var(--accent);
  border-right: 1px solid #bfdbfe; padding-right: 0.9rem; }
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
.r-info .risk-lab { background: rgba(37,99,235,0.12); color: var(--home); }
.r-warn { border-left-color: var(--accent3); background: rgba(245,158,11,0.08); }
.r-warn .risk-lab { background: rgba(245,158,11,0.18); color: #b45309; }
.r-block { border-left-color: var(--accent); background: rgba(220,38,38,0.06); }
.r-block .risk-lab { background: rgba(220,38,38,0.12); color: var(--accent); }

/* ---------- 外部对照表 ---------- */
table.ref-table td:not(:first-child) { font-variant-numeric: tabular-nums; }
table.ref-table td:nth-child(3) { color: var(--muted); }
table.ref-table .hit { margin-left: 0.25rem; }

/* ---------- 结论四宫格 ---------- */
.prediction { background: linear-gradient(135deg, rgba(16,185,129,0.08), rgba(16,185,129,0.02));
  border: 1px solid rgba(16,185,129,0.2); border-radius: 10px; padding: 1rem 1.25rem; margin: 1rem 0; }
.prediction .pred-title { font-size: 0.8rem; font-weight: 600; color: var(--accent2);
  text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 0.5rem; }
.picks4 { display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 0.75rem; }
.pick { background: var(--bg2); border: 1px solid rgba(16,185,129,0.25); border-radius: 8px;
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

/* ---------- 比赛卡片：结构与样式照搬 qiuxiaoce .match-card ---------- */
.match-card {
  display: block; background: #fff; border: 1px solid #e5e7eb; border-radius: 12px;
  overflow: hidden; margin: 0 0 15px; text-decoration: none; color: inherit;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.02); transition: all 0.2s;
}
.match-card:hover { border-color: #10b981; box-shadow: 0 4px 12px rgba(16,185,129,0.1);
  transform: translateY(-2px); text-decoration: none; }
.mc-header { display: flex; justify-content: space-between; align-items: center;
  padding: 10px 15px; background: #fff; border-bottom: 1px solid #f3f4f6; font-size: 13px; }
.mc-meta { display: flex; gap: 10px; align-items: center; }
.mc-meta .date { font-weight: 700; color: #111; font-size: 14px; }
.mc-meta .league { background: #eff6ff; color: #2563eb; padding: 2px 6px; border-radius: 4px;
  font-weight: 700; font-size: 12px; }
.mc-meta .num { color: #4b5563; background: #f3f4f6; padding: 2px 6px; border-radius: 4px;
  font-size: 12px; font-weight: 600; }
.mc-meta .time { font-weight: 700; color: #111; }
.mc-status { display: flex; gap: 8px; align-items: center; flex-shrink: 0; }
.mc-conf { padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 700;
  color: #fff; background: #6b7280; white-space: nowrap; }
.mc-conf.high { background: #dc2626; }
.mc-conf.medium { background: #f59e0b; }
.mc-conf.low { background: #3b82f6; }
.mc-conf.cold { background: #7c3aed; }
.mc-body { padding: 15px; display: flex; flex-direction: column; gap: 12px; }
.mc-teams { display: flex; justify-content: center; align-items: center; gap: 16px; }
.mc-team { width: 100px; text-align: center; display: flex; flex-direction: column;
  align-items: center; gap: 6px; flex-shrink: 0; }
.mc-team img { width: 48px; height: 48px; object-fit: contain; }
.mc-team span { font-size: 14px; font-weight: 600; color: #111; display: -webkit-box;
  -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
  line-height: 1.3; max-width: 100px; }
.mc-score { text-align: center; min-width: 80px; }
.mc-score .main { font-size: 28px; font-weight: 800; color: #111; line-height: 1; }
.mc-score .sub { font-size: 13px; color: #6b7280; margin-top: 4px; }
.mc-score .vs { font-size: 20px; font-weight: 700; color: #d1d5db; }
.mc-tags { display: flex; justify-content: center; gap: 8px; margin-top: 4px; flex-wrap: wrap; }
.mc-tag { font-size: 12px; padding: 4px 10px; border-radius: 6px; background: #f3f4f6;
  color: #6b7280; display: inline-flex; align-items: center; gap: 4px; transition: all 0.2s; }
.mc-tag svg { width: 13px; height: 13px; }
.mc-tag .tag-state { display: inline-flex; align-items: center; }
.mc-tag .tag-state svg { width: 12px; height: 12px; }
.mc-tag.miss { background: #f3f4f6; color: #9ca3af; }
.mc-tag.miss .tag-state { color: #ef4444; }
.mc-tag-ph { background: transparent; border: 1px dashed #d1d5db; color: #9ca3af; }
.net-form { display: grid; grid-template-columns: 1fr 1fr; gap: 4px 24px; margin-top: 10px; }
.net-form h3 { margin: 6px 0 4px; }
@media (max-width: 640px) { .net-form { grid-template-columns: 1fr; } }
.panel-empty { font-size: 13px; color: #9ca3af; margin: 4px 0; }
.pick-ph { color: #9ca3af; }
.pick-ph .lab { color: #9ca3af; }
[data-goto] { cursor: pointer; }
a.lg-link:hover, .lg-link:hover, .team-link:hover span:last-child { color: var(--accent); }
.team-link { display: inline-flex; flex-direction: column; align-items: center; gap: 6px; }
.mc-team .team-link span:last-child { transition: color 0.15s; }

/* ---------- 历史归档三视图：交易日 / 联赛 / 球队（纯 CSS radio 切换） ---------- */
.arch-tabs .fp-opt { margin-bottom: 10px; }
.arch-view { display: none; }
#at-date:checked ~ .av-date, #at-lg:checked ~ .av-lg, #at-tm:checked ~ .av-tm { display: block; }
#at-date:checked + label[for="at-date"], #at-lg:checked + label[for="at-lg"],
#at-tm:checked + label[for="at-tm"] { background: var(--accent); color: #fff; border-color: var(--accent); }
.arch-days { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 8px; }
.arch-day { display: flex; justify-content: space-between; align-items: center; gap: 6px;
  background: #fff; border: 1px solid var(--rule); border-radius: 8px; padding: 10px 12px;
  font-size: 13px; color: #374151; text-decoration: none; }
.arch-day:hover { border-color: #93c5fd; text-decoration: none; }
.arch-date { font-weight: 600; }
.arch-go { color: var(--accent); font-size: 12px; }
.arch-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 10px; }
.arch-cell { display: grid; grid-template-columns: 1fr auto; gap: 2px 8px; align-items: center;
  background: #fff; border: 1px solid var(--rule); border-radius: 10px; padding: 12px 14px;
  text-decoration: none; }
.arch-cell:hover { border-color: #93c5fd; text-decoration: none; }
.arch-name { font-weight: 700; font-size: 14px; color: #111; overflow: hidden;
  text-overflow: ellipsis; white-space: nowrap; }
.arch-n { font-size: 12px; color: #6b7280; }
.arch-cell .rank-bar-wrap { grid-column: 1 / -1; }
.arch-cell .rank-acc, .arch-cell .mini { grid-column: 1 / -1; text-align: right; }
.mc-tag.hit { background: #fff1f0; color: #f56c6c; border: 1px solid #ffccc7; font-weight: 600; }
.mc-footer { display: flex; justify-content: space-between; align-items: center;
  padding: 10px 15px; background: #f9fafb; border-top: 1px solid #f3f4f6;
  margin: 0 -15px -15px; font-size: 12px; color: #6b7280; }
.mc-footer-left { display: flex; align-items: center; gap: 6px; flex: 1; overflow: hidden; }
.mc-highlight-icon { font-size: 14px; }
.mc-highlight-text { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.prediction-stamp { display: inline-flex; align-items: center; justify-content: center;
  width: 22px; height: 22px; font-size: 12px; line-height: 20px; border-width: 1px;
  border-radius: 50%; flex-shrink: 0; }
.stamp-red { color: #dc2626; border: 1px solid #dc2626; background: #fff1f2; }
.stamp-black { color: #374151; border: 1px solid #374151; background: #f3f4f6; }

/* ---------- 双栏：主列 + 右侧栏（对齐 qiuxiaoce 的 v4 布局） ---------- */
.v4-layout { display: flex; gap: 20px; align-items: flex-start; }
.v4-main-col { flex: 1; min-width: 0; }
.right-sidebar-new { width: 360px; flex: none; display: flex; flex-direction: column; }
/* 右栏垂直节奏与左栏完全一致：间距全部用 margin（bar mb 12 / 卡 mb 15），
   不用 flex gap——gap 会叠加 bar 的 margin-bottom，把 AI 卡推低 16px */
.right-sidebar-new .ranking-card { margin: 0 0 15px; }
@media (max-width: 1000px) {
  .right-sidebar-new { display: none; }
}

/* ---------- Top 卡：榜序号 / 徽章 / 名称 / 绿色进度条 / 命中率 ---------- */
.ranking-card { background: #fff; border-radius: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.06);
  overflow: hidden; }
.ranking-card .card-header { font-size: 14px; font-weight: 700; color: #111;
  padding: 10px 15px; border-bottom: 1px solid #f1f5f9; }
.ranking-list { padding: 6px 0; }
.ranking-item { display: flex; align-items: center; gap: 8px; padding: 7px 14px;
  color: #374151; font-size: 13px; }
.ranking-item:hover { background: #f8fafc; text-decoration: none; }
.rank-index { width: 18px; flex: none; text-align: center; font-size: 12px;
  font-weight: 700; color: #9ca3af; }
.ranking-item:nth-child(1) .rank-index { color: #dc2626; }
.ranking-item:nth-child(2) .rank-index { color: #ea580c; }
.ranking-item:nth-child(3) .rank-index { color: #ca8a04; }
.rank-logo { width: 22px; height: 22px; flex: none; object-fit: contain;
  border-radius: 50%; background: #f8fafc; }
.rank-logo-ph { display: inline-flex; align-items: center; justify-content: center;
  font-size: 11px; font-weight: 700; color: #64748b; }
.rank-name { flex: none; width: 76px; overflow: hidden; text-overflow: ellipsis;
  white-space: nowrap; }
.rank-bar-wrap { flex: 1; height: 6px; background: #f1f5f9; border-radius: 3px; overflow: hidden; }
.rank-bar { height: 100%; background: linear-gradient(90deg, #6ee7b7, #10b981); border-radius: 3px; }
.rank-acc { flex: none; width: 44px; text-align: right; font-size: 12px; font-weight: 600;
  color: #10b981; }
.ranking-empty { padding: 14px 16px; font-size: 12px; color: #9ca3af; }

/* ---------- 右栏 AI 预测卡：复用 .ranking-card 卡壳，筛选芯片与左侧同款 ---------- */
/* 卡内自带时间/赛事两行筛选（fp-opt 同款），日期横向滚动、赛事横向滚动 */
/* AI 预测卡：筛选条完全独立在卡片外（与左侧同款白条），卡内只留标题+面板+列表 */
.ai-date { color: #6b7280; font-weight: 600; font-size: 13px;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
#ai-filter-panel { display: none; background: #fff; border-bottom: 1px solid #f1f5f9;
  padding: 12px 14px; }
#ai-filter-panel .fp-row + .fp-row { margin-top: 8px; }
.ai-body { display: none; max-height: 480px; overflow-y: auto; padding: 8px 10px 12px; }
.ai-m { display: block; padding: 8px 8px 9px; border-radius: 8px; color: inherit;
  text-decoration: none; }
.ai-m:hover { background: #f8fafc; text-decoration: none; }
.ai-m + .ai-m { border-top: 1px solid #f8fafc; }
.ai-m-head { display: flex; align-items: center; gap: 8px; font-size: 13px; font-weight: 600;
  color: #111; margin-bottom: 5px; }
.ai-m-code { flex: none; font-family: 'SFMono-Regular', Consolas, monospace; font-size: 11px;
  color: #6b7280; background: #f1f5f9; padding: 1px 6px; border-radius: 4px; }
.ai-m-vs { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ai-m-picks { display: flex; flex-wrap: wrap; gap: 5px; }
.ai-chip { display: inline-flex; align-items: center; gap: 3px; font-size: 11px;
  color: #374151; background: #f8fafc; border: 1px solid #eef2f7; border-radius: 6px;
  padding: 2px 6px; }
.ai-chip svg { width: 12px; height: 12px; flex: none; color: #94a3b8; }
.ai-chip .pct { font-size: 11px; }

/* ---------- 数据统计页（结构对齐球小策 /shu-ju-tong-ji/） ---------- */
.stats-note { font-size: 13px; color: #6b7280; margin: 0 0 14px; }
.stats-main .stat-card .stat-num { font-size: 30px; font-weight: 800; color: #111; }
.stats-main .stat-card .stat-lbl { font-size: 13px; color: #6b7280; margin-top: 2px; }
.stats-box { background: #fff; border-radius: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.06);
  padding: 16px; min-width: 0; }
.stats-box h3 { margin: 0 0 12px; font-size: 14px; font-weight: 700; color: #111; }
.stats-box .history-table { margin-top: 8px; }
.stats-duo { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; align-items: start; }
@media (max-width: 1000px) { .stats-duo { grid-template-columns: 1fr; } }
.dim-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; }
@media (max-width: 640px) { .dim-grid { grid-template-columns: repeat(2, 1fr); } }
.dim-card { background: #f8fafc; border: 1px solid #eef2f7; border-radius: 10px;
  padding: 10px 12px; text-align: center; }
.dim-name { font-size: 12px; color: #6b7280; }
.dim-acc { font-size: 20px; font-weight: 800; color: var(--accent); margin: 3px 0; }
.dim-n { font-size: 11px; color: #9ca3af; }
.trend { display: flex; gap: 8px; align-items: stretch; }
.t-col { flex: 1; min-width: 0; text-align: center; }
.t-val { font-size: 11px; font-weight: 700; color: #10b981; }
.t-area { height: 90px; display: flex; align-items: flex-end; margin: 4px 0; }
.t-bar { width: 100%; background: linear-gradient(180deg, #6ee7b7, #10b981);
  border-radius: 4px 4px 0 0; min-height: 4px; }
.t-lbl { font-size: 10px; color: #6b7280; white-space: nowrap; }
.t-sub { font-size: 10px; color: #9ca3af; }
.team-out { max-height: 340px; overflow-y: auto; }
.team-stat + .team-stat { margin-top: 10px; }
.team-stat .ts-head { display: flex; justify-content: space-between; align-items: baseline;
  gap: 8px; font-size: 13px; margin-bottom: 4px; }
.team-stat .ts-head span { font-size: 12px; color: #6b7280; }
.team-stat .pct { color: #10b981; font-weight: 700; }

/* ---------- 赔率 / 投注页 ---------- */
.odds-strip { display: flex; gap: 8px; overflow-x: auto; padding-bottom: 8px; margin-bottom: 12px; }
.odds-strip .fp-opt { flex: none; }
.odds-strip a.fp-opt { text-decoration: none; }
.bet-form { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; align-items: end; }
@media (max-width: 800px) { .bet-form { grid-template-columns: repeat(2, 1fr); } }
.bet-form label { display: flex; flex-direction: column; gap: 4px; font-size: 12px; color: #6b7280; }
.bet-form select, .bet-form input { padding: 7px 9px; border: 1px solid var(--rule); border-radius: 8px;
  font-size: 13px; background: #fff; }
.bet-form .search-btn { align-self: end; padding: 8px 0; }
.bet-rec { padding: 9px 10px; border-radius: 8px; border: 1px solid #f1f5f9; }
.bet-rec + .bet-rec { margin-top: 8px; }
.bet-rec .br-head { display: flex; align-items: center; gap: 10px; font-size: 13px; }
.bet-rec .br-head b { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.bet-rec .br-del { font-size: 11px; color: #dc2626; text-decoration: none; }
.bet-rec .br-meta { font-size: 12px; color: #6b7280; margin-top: 4px; }
.bet-rec .br-meta b { color: #111; }
.b-win { color: #dc2626; font-weight: 700; font-size: 12px; }
.b-lose { color: #9ca3af; font-weight: 700; font-size: 12px; }
.b-push { color: #2563eb; font-weight: 700; font-size: 12px; }
.b-wait { color: #d97706; font-weight: 700; font-size: 12px; }
.pnl-pos { color: #dc2626; }
.pnl-neg { color: #16a34a; }

/* 盘口页：全玩法面板（对照原工具「赔率管理」：彩色标签 + 数值框） */
.odds-match { background: #fff; border-radius: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.06);
  padding: 14px 16px; margin-bottom: 14px; }
.odds-m-head { display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
  font-size: 14px; font-weight: 700; color: #111; margin-bottom: 4px; }
.odds-m-head a { color: inherit; text-decoration: none; }
.odds-m-head a:hover { color: var(--accent); }
.odds-code { font-family: 'SFMono-Regular', Consolas, monospace; font-size: 11px; font-weight: 500;
  background: #f1f5f9; padding: 2px 7px; border-radius: 5px; color: #6b7280; }
.odds-lg { font-size: 11px; font-weight: 600; background: #eff6ff; color: var(--accent);
  padding: 2px 7px; border-radius: 5px; }
.odds-res { margin-left: auto; font-size: 12px; color: #16a34a; font-weight: 700; }
.odds-sec { margin-top: 10px; }
.odds-sec-t { font-size: 12px; color: #6b7280; font-weight: 600; margin-bottom: 6px; }
.odds-pills { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
.odds-pill { display: inline-flex; align-items: stretch; border: 1px solid #eef0f4;
  border-radius: 8px; overflow: hidden; font-size: 12px; background: #fff; }
.odds-pill b { padding: 4px 8px; font-weight: 600; background: #f8f9fc; }
.odds-pill i { font-style: normal; padding: 4px 9px; font-weight: 700; color: #111;
  min-width: 40px; text-align: center; }
.odds-pill b.s-h { color: #dc2626; }
.odds-pill b.s-d { color: #6b7280; }
.odds-pill b.s-a { color: #0d9488; }
.odds-pill.hit { border-color: var(--accent); box-shadow: 0 0 0 1px var(--accent) inset; }
.odds-pill.hit i { color: var(--accent); }
.rq-tag { font-size: 11px; color: #6b7280; background: #f1f5f9; border-radius: 6px;
  padding: 4px 8px; }

/* 记录本页：统计卡 / 编辑器 / 主表格（对照原工具「足彩记录」） */
.bets-stats { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin: 14px 0; }
.bets-stats .stat-num { font-size: 1.4rem; }
@media (max-width: 800px) { .bets-stats { grid-template-columns: repeat(2, 1fr); } }
.bets-card { background: #fff; border-radius: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.06);
  padding: 14px 16px; margin-bottom: 14px; }
.bets-card h3 { font-size: 14px; margin: 0 0 10px; color: #111; }
.bf-row { margin-bottom: 12px; }
.bf-row > label { display: block; font-size: 12px; color: #6b7280; font-weight: 600; margin-bottom: 6px; }
.bf-chips { display: flex; flex-wrap: wrap; gap: 6px; }
.bf-check, .bf-opt { font-size: 12px; color: #374151; background: #f8f9fc;
  border: 1px solid #eef0f4; border-radius: 6px; padding: 4px 9px; cursor: pointer;
  display: inline-flex; align-items: center; gap: 4px; }
.bf-check:has(input:checked), .bf-opt:has(input:checked) { background: #eff6ff;
  border-color: var(--accent); color: var(--accent); font-weight: 600; }
.bf-persons { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 6px; }
.bf-person { font-size: 12px; background: #f8f9fc; border: 1px solid #eef0f4;
  border-radius: 6px; padding: 3px 8px; display: inline-flex; align-items: center; gap: 4px; }
.bf-person input { width: 52px; border: none; background: transparent; font-size: 12px; }
.bf-pdel { color: #dc2626; text-decoration: none; cursor: pointer; }
.bf-addperson { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
.bf-addperson select, .bf-addperson input { font-size: 12px; padding: 4px 7px;
  border: 1px solid var(--rule); border-radius: 6px; }
.bf-schedule { display: flex; gap: 8px; align-items: center; margin-bottom: 8px; }
.bt-mini, .bf-actions button { font-size: 12px; padding: 6px 12px; border-radius: 8px;
  border: 1px solid #e2e8f0; background: #fff; color: #374151; cursor: pointer; }
.bt-mini:hover { border-color: #93c5fd; color: var(--accent); }
.bt-gold { background: #fef3c7; border-color: #fcd34d; font-weight: 600; }
.bt-go { background: var(--accent); border-color: var(--accent); color: #fff; font-weight: 600; }
.bf-actions { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; margin: 12px 0; }
.bf-sp { font-size: 12px; color: #6b7280; background: #f8f9fc; border-radius: 16px; padding: 5px 12px; }
.bf-sp b { color: #111; }
.bf-games { display: flex; flex-direction: column; gap: 8px; }
.bf-game { border: 1px solid #eef0f4; border-radius: 10px; padding: 8px 10px; }
.bf-game-h { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; font-size: 13px;
  font-weight: 600; color: #111; margin-bottom: 6px; }
.bf-game-h select { font-size: 12px; padding: 3px 7px; border: 1px solid var(--rule); border-radius: 6px; }
.bf-gdel { color: #dc2626; text-decoration: none; cursor: pointer; margin-left: auto; }
.bf-done { font-size: 11px; color: #16a34a; font-weight: 600; }
.bf-opts { display: flex; flex-wrap: wrap; gap: 5px; }
.bk-combos { background: #fafbfc; border: 1px solid #eef0f4; border-radius: 10px;
  padding: 10px 12px; font-size: 12px; color: #374151; max-height: 300px; overflow-y: auto; }
.bk-combos b { display: block; margin-bottom: 6px; color: #111; }
.bk-combo { padding: 3px 0; border-bottom: 1px dashed #eef0f4; }
.bets-filter { display: flex; align-items: center; gap: 8px; margin-bottom: 10px;
  font-size: 13px; color: #374151; }
.bets-filter select { font-size: 13px; padding: 5px 9px; border: 1px solid var(--rule);
  border-radius: 8px; background: #fff; }
.bets-twrap { background: #fff; border-radius: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.06);
  padding: 6px 12px; overflow-x: auto; }
.bets-table { width: 100%; border-collapse: collapse; font-size: 12.5px; }
.bets-table th, .bets-table td { padding: 8px 9px; text-align: left; border-bottom: 1px solid #f1f5f9;
  vertical-align: top; }
.bets-table th { color: #6b7280; font-weight: 600; font-size: 12px; white-space: nowrap; }
.bt-small { font-size: 12px; }
.bt-chip { font-size: 11px; font-weight: 700; border-radius: 12px; padding: 3px 9px; white-space: nowrap; }
.bt-win { background: #fee2e2; color: #dc2626; }
.bt-lose { background: #f1f5f9; color: #9ca3af; }
.bt-pending { background: #fef3c7; color: #d97706; }
.bt-del { color: #dc2626; font-size: 12px; text-decoration: none; cursor: pointer; }
.bets-foot { font-size: 12px; color: #9ca3af; margin: 10px 2px; }

/* ---------- 联赛 / 球队专题页：头部对齐对方 .lt-header（徽章 + 标题 + 统计） ---------- */
.lt-header { background: #fff; border-radius: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.06);
  padding: 22px 24px; display: flex; align-items: center; gap: 16px; margin-bottom: 16px; }
.lt-logo { width: 52px; height: 52px; object-fit: contain; flex: none;
  border-radius: 50%; background: #f8fafc; }
.lt-logo-ph { display: flex; align-items: center; justify-content: center; font-size: 22px;
  font-weight: 700; color: #64748b; }
.lt-title { font-size: 20px; font-weight: 800; color: #111; margin: 0 0 4px; }
.lt-meta { font-size: 13px; color: #6b7280; }
.lt-meta b { color: var(--accent); }
/* 卡片/列表里联赛名、球队名的内链：继承原样式，hover 出主题色 */
a.team-link { color: inherit; text-decoration: none; }
a.team-link:hover { color: var(--accent); text-decoration: none; }
a.team-link span, a.team-link img { cursor: pointer; }
a.lg-link { color: inherit; text-decoration: none; }
a.lg-link:hover { color: var(--accent); text-decoration: none; }

/* ---------- 列表网格：对方是单列垂直列表，主列宽度约等于其 1200 - 侧栏 ---------- */
.cards { display: block; }
.card-picks { display: flex; flex-wrap: wrap; gap: 0.4rem; margin-top: 0.75rem; font-size: 0.8rem;
  color: var(--muted); }

/* ---------- 置信度条 ---------- */
.conf-bar { display: flex; align-items: center; gap: 0.5rem; margin: 0.5rem 0; }
.bar-track { flex: 1; height: 8px; background: var(--bg); border-radius: 4px; overflow: hidden; }
.bar-fill { height: 100%; background: linear-gradient(90deg, var(--accent2), var(--accent3));
  border-radius: 4px; }
.bar-label { font-size: 0.8rem; color: var(--muted); }

/* ---------- 提示与页脚 ---------- */
.warning { background: rgba(245,158,11,0.1); border: 1px solid rgba(245,158,11,0.3);
  border-radius: 8px; padding: 0.75rem 1rem; margin: 0.75rem 0; font-size: 0.85rem; color: #b45309; }
.ledger { background: var(--bg2); border: 1px dashed var(--rule); border-radius: 10px;
  padding: 1rem 1.25rem; margin: 1.25rem 0; font-size: 0.8rem; color: var(--muted); }
.ledger code { font-family: 'SFMono-Regular', Consolas, monospace; background: var(--bg);
  padding: 0.1rem 0.4rem; border-radius: 4px; color: var(--ink); }
.disclaimer { background: var(--bg2); border-left: 3px solid var(--rule); padding: 0.6rem 1rem;
  color: var(--muted); font-size: 0.8rem; margin: 1.5rem 0; }
footer.site { background: var(--bg2); border-top: 1px solid var(--rule); padding: 1.5rem 0;
  margin-top: 2.5rem; text-align: center; font-size: 0.8rem; color: var(--muted); }

/* ---------- 移动端底部导航：桌面隐藏，≤768px 固定贴底 ---------- */
.v4-bottom-nav-global { display: none; }
.v4-nav-item { display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: 2px; color: #6b7280; text-decoration: none; flex: 1; padding: 6px 0; }
.v4-nav-item:hover { text-decoration: none; }
.v4-nav-item.active { color: #2563eb; }
.v4-nav-icon { font-size: 20px; line-height: 1; }
.v4-nav-lbl { font-size: 10px; }

@media (max-width: 768px) {
  .wrap { padding: 0 1rem; }
  main .wrap > h1 { font-size: 1.35rem; }
  .match-teams { font-size: 1.05rem; gap: 0.6rem; }
  .odds-grid { gap: 0.5rem; }
  .cards { grid-template-columns: 1fr; }
  .mainpick { flex-direction: column; align-items: flex-start; gap: 0.5rem; }
  .mainpick .mp-lab { border-right: none; border-bottom: 1px solid #bfdbfe;
    padding: 0 0 0.35rem; }
  /* 以下六条照抄对方 768px 的卡片规则 */
  .match-card { margin: 0 0 12px; }
  .mc-header { padding: 8px 12px; }
  .mc-body { padding: 12px; gap: 10px; }
  .mc-team { width: 88px; }
  .mc-team .crest { width: 40px; height: 40px; }
  .mc-team span { font-size: 12px; max-width: 80px; }
  .crest-ph { font-size: 15px; }
  .mc-score .main { font-size: 24px; }
  .mc-score .vs { font-size: 18px; }
  .mc-tags { gap: 6px; }
  .mc-tag { font-size: 10px; padding: 3px 8px; }
  .mc-footer { padding: 8px 12px; margin: 0 -12px -12px; }
  /* 移动端：顶部文字导航让位给底部固定导航 */
  header.site nav.site { display: none; }
  .v4-bottom-nav-global { display: flex; position: fixed; bottom: 0; left: 0; width: 100%;
    background: #fff; border-top: 1px solid #e5e7eb; justify-content: space-around;
    align-items: center; height: 60px; z-index: 9999;
    box-shadow: 0 -2px 10px rgba(0, 0, 0, 0.05);
    padding-bottom: env(safe-area-inset-bottom); }
  body { padding-bottom: 70px; }
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


# 顶导图标：单色线性 SVG（stroke 随 currentColor），与搜索放大镜同风格。
# 刻意不用对方那套彩色 emoji——视觉更统一，也算"灵活替代"。
_ICON_ATTRS = (
    'viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" '
    'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"'
)
ICON_SEARCH = (
    f'<svg {_ICON_ATTRS}>'
    '<circle cx="11" cy="11" r="7"></circle><line x1="21" y1="21" x2="16.2" y2="16.2"></line></svg>'
)
ICON_SPORTS = (  # 赛事：足球
    f'<svg {_ICON_ATTRS}><circle cx="12" cy="12" r="9"></circle>'
    '<path d="M12 7.2l4.6 3.3-1.8 5.4H9.2L7.4 10.5z"></path>'
    '<path d="M12 3v4.2M3.6 9.4l3.8 1.1M20.4 9.4l-3.8 1.1M8 20l1.2-4.1M16 20l-1.2-4.1"></path></svg>'
)
ICON_DATA = (  # 数据：柱状图
    f'<svg {_ICON_ATTRS}><path d="M5 20v-6M12 20V7M19 20v-9"></path>'
    '<path d="M3 20h18"></path></svg>'
)
ICON_FUNCT = (  # 功能：四宫格
    f'<svg {_ICON_ATTRS}><rect x="3" y="3" width="7.5" height="7.5" rx="1.5"></rect>'
    '<rect x="13.5" y="3" width="7.5" height="7.5" rx="1.5"></rect>'
    '<rect x="3" y="13.5" width="7.5" height="7.5" rx="1.5"></rect>'
    '<rect x="13.5" y="13.5" width="7.5" height="7.5" rx="1.5"></rect></svg>'
)
ICON_USER = (  # 我的：人形
    f'<svg {_ICON_ATTRS}><circle cx="12" cy="8" r="4"></circle>'
    '<path d="M4.5 21c0-3.9 3.4-6.2 7.5-6.2s7.5 2.3 7.5 6.2"></path></svg>'
)
ICON_TOP = (  # 回顶部：向上箭头
    f'<svg {_ICON_ATTRS}><path d="M12 19V5"></path><path d="M6 11l6-6 6 6"></path></svg>'
)
ICON_CALENDAR = (  # 日期
    f'<svg {_ICON_ATTRS}><rect x="3" y="4.5" width="18" height="17" rx="2"></rect>'
    '<path d="M8 2.5v4M16 2.5v4M3 10.5h18"></path></svg>'
)
ICON_FILTER = (  # 筛选：漏斗
    f'<svg {_ICON_ATTRS}><path d="M3 5h18l-7 8.5V19l-4 2.5v-8z"></path></svg>'
)
ICON_TROPHY = (  # 赛事Top：奖杯
    f'<svg {_ICON_ATTRS}><path d="M6 9H4.5a2.5 2.5 0 0 1 0-5H6"></path>'
    '<path d="M18 9h1.5a2.5 2.5 0 0 0 0-5H18"></path><path d="M4 22h16"></path>'
    '<path d="M10 14.66V17c0 .55-.47.98-.97 1.21C7.85 18.75 7 20.24 7 22"></path>'
    '<path d="M14 14.66V17c0 .55.47.98.97 1.21C16.15 18.75 17 20.24 17 22"></path>'
    '<path d="M18 2H6v7a6 6 0 0 0 12 0V2Z"></path></svg>'
)
ICON_SHIELD = (  # 球队Top：盾徽
    f'<svg {_ICON_ATTRS}><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path></svg>'
)
ICON_HOME = (  # 今日：房子
    f'<svg {_ICON_ATTRS}><path d="M3 9.5 12 3l9 6.5V20a1.5 1.5 0 0 1-1.5 1.5h-15A1.5 1.5 0 0 1 3 20z"></path>'
    '<path d="M9.5 21.5v-8h5v8"></path></svg>'
)
ICON_ARCHIVE = (  # 归档：盒盖箱
    f'<svg {_ICON_ATTRS}><path d="M21 8v12a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V8"></path>'
    '<rect x="1.5" y="3" width="21" height="5" rx="1"></rect><path d="M10 12h4"></path></svg>'
)
ICON_DOC = (  # 索引：文件
    f'<svg {_ICON_ATTRS}><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>'
    '<path d="M14 2v6h6M9 13h6M9 17h6"></path></svg>'
)
ICON_CPU = (  # 机器可读：芯片
    f'<svg {_ICON_ATTRS}><rect x="4.5" y="4.5" width="15" height="15" rx="2"></rect>'
    '<rect x="9.5" y="9.5" width="5" height="5"></rect>'
    '<path d="M9.5 2v2.5M14.5 2v2.5M9.5 19.5V22M14.5 19.5V22M2 9.5h2.5M2 14.5h2.5M19.5 9.5H22M19.5 14.5H22"></path></svg>'
)
ICON_ACTIVITY = (  # 深度数据：心电折线
    f'<svg {_ICON_ATTRS}><path d="M22 12h-4l-3 9L9 3l-3 9H2"></path></svg>'
)
ICON_TARGET = (  # 方向：靶心
    f'<svg {_ICON_ATTRS}><circle cx="12" cy="12" r="9"></circle>'
    '<circle cx="12" cy="12" r="5"></circle><circle cx="12" cy="12" r="1.2"></circle></svg>'
)
ICON_HASH = (  # 比分：井号
    f'<svg {_ICON_ATTRS}><path d="M5 9h14M5 15h14M10 3 8 21M16 3l-2 18"></path></svg>'
)
ICON_TREND = (  # 半全场：趋势
    f'<svg {_ICON_ATTRS}><path d="M3 17l6-6 4 4 8-8"></path><path d="M15 7h6v6"></path></svg>'
)
ICON_CHECK = (  # 命中：对勾
    f'<svg {_ICON_ATTRS}><path d="M20 6 9 17l-5-5"></path></svg>'
)
ICON_CROSS = (  # 未中：叉
    f'<svg {_ICON_ATTRS}><path d="M18 6 6 18M6 6l12 12"></path></svg>'
)


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
    nav_extra_bottom = (
        f'<a class="v4-nav-item" href="{pre}days/{nav_day}.html">'
        '<span class="v4-nav-icon">📊</span><span class="v4-nav-lbl">当日</span></a>'
        if nav_day
        else ""
    )
    head_title = title if title.endswith(cfg.site_name) else f"{title} - {cfg.site_name}"
    return f"""<!DOCTYPE html>
<html lang="{cfg.language}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{C.esc(head_title)}</title>
<meta name="description" content="{C.esc(description)}">
<link rel="canonical" href="{C.esc(canonical)}">
<link rel="stylesheet" href="{pre}assets/style.css?v={_CSS_VER}">
<meta property="og:type" content="article">
<meta property="og:title" content="{C.esc(head_title)}">
<meta property="og:description" content="{C.esc(description)}">
<meta name="robots" content="index,follow">
{_jsonld(jsonld or [])}
</head>
<body>
<input type="checkbox" id="ss-toggle" class="ss-toggle" aria-hidden="true">
<header class="site"><div class="wrap">
  <div class="brand"><span class="brand-mark">M</span>{C.esc(cfg.site_name)}<span>{C.esc(cfg.site_tagline)}</span></div>
  <nav class="site">
    <a href="{home}">{ICON_SPORTS}赛事</a>
    <a href="{pre}data.html">{ICON_DATA}数据</a>
    <a href="{pre}features.html">{ICON_FUNCT}功能</a>
    <a href="{pre}me.html">{ICON_USER}我的</a>
    <label class="is-icon nav-search" for="ss-toggle" aria-label="搜索">{ICON_SEARCH}</label>
  </nav>
</div></header>
<div class="site-search"><div class="wrap">
  <form class="site-search-form" action="{pre}search.html" method="get">
    <input class="search-input" name="q" type="text" placeholder="输入关键字" required>
    <button class="search-btn" type="submit" aria-label="搜索">{ICON_SEARCH}</button>
  </form>
</div></div>
<main class="wrap">
{body}
</main>
<footer class="site"><div class="wrap">
  <p>{C.esc(cfg.site_name)} · {C.esc(cfg.site_tagline)}</p>
</div></footer>
<a class="back-top" id="back-top" href="#" aria-label="回顶部">{ICON_TOP}</a>
<nav class="v4-bottom-nav-global">
  <a class="v4-nav-item active" href="{home}">
    <span class="v4-nav-icon">{ICON_HOME}</span><span class="v4-nav-lbl">今日</span></a>
  <a class="v4-nav-item" href="{pre}days/">
    <span class="v4-nav-icon">{ICON_ARCHIVE}</span><span class="v4-nav-lbl">归档</span></a>
  {nav_extra_bottom}
  <a class="v4-nav-item" href="{pre}llms.txt">
    <span class="v4-nav-icon">{ICON_DOC}</span><span class="v4-nav-lbl">索引</span></a>
</nav>
<script>
(function () {{
  var btn = document.getElementById("back-top");
  if (!btn) return;
  var sync = function () {{
    btn.classList.toggle("show", window.scrollY > 480);
  }};
  window.addEventListener("scroll", sync, {{ passive: true }});
  btn.addEventListener("click", function (e) {{
    e.preventDefault();
    window.scrollTo({{ top: 0, behavior: "smooth" }});
  }});
  sync();
}})();
// data-goto 事件委托：联赛/球队内链在整卡 <a> 内部（HTML 不允许嵌套 a），
// 点击时阻止整卡默认跳转，改跳联赛/球队专题页。
document.addEventListener("click", function (e) {{
  var t = e.target.closest("[data-goto]");
  if (!t) return;
  e.preventDefault();
  e.stopPropagation();
  window.location.href = t.getAttribute("data-goto");
}});
// 时间行日期下拉：选中即跳转对应日期页（optgroup 按月分组，数量无上限）
document.addEventListener("change", function (e) {{
  var s = e.target.closest(".date-select");
  if (s && s.value) window.location.href = s.value;
}});
// AI 预测卡日期：下拉/‹›箭头只改隐藏 radio 的选中态，内容显隐仍走纯 CSS 规则
document.addEventListener("change", function (e) {{
  var s = e.target.closest(".ai-date-select");
  if (!s) return;
  var r = document.getElementById(s.value);
  if (r) r.checked = true;
  aiSyncArrows(s);
}});
function aiSyncArrows(s) {{
  document.querySelectorAll("[data-aid-step]").forEach(function (a) {{
    var i = s.selectedIndex + parseInt(a.getAttribute("data-aid-step"), 10);
    a.classList.toggle("off", i < 0 || i >= s.options.length);
  }});
}}
document.addEventListener("click", function (e) {{
  var a = e.target.closest("[data-aid-step]");
  if (!a) return;
  e.preventDefault();
  var s = document.querySelector("#ai-pred-card .ai-date-select");
  if (!s) return;
  var i = s.selectedIndex + parseInt(a.getAttribute("data-aid-step"), 10);
  if (i < 0 || i >= s.options.length) return;
  s.selectedIndex = i;
  var r = document.getElementById(s.options[i].value);
  if (r) r.checked = true;
  aiSyncArrows(s);
}});
document.querySelectorAll("#ai-pred-card .ai-date-select").forEach(aiSyncArrows);
</script>
</body>
</html>
"""


def write(cfg: Config, rel: str, content: str) -> Path:
    p = cfg.out_dir / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p
