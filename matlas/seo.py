"""GEO 基建：llms.txt / robots.txt / sitemap.xml / sitemap-today.xml。

与 jinbet 最大的差别不在预测本身，而在「能不能被 AI 检索到」。
这一层全部是静态文本文件，零成本，长期复利。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

from .config import Config
from .models import Day, Match, SCHEMA_VERSION


def _url(cfg: Config, path: str) -> str:
    return f"{cfg.base_url.rstrip('/')}/{path.lstrip('/')}"


# ---------------------------------------------------------------- llms.txt


def write_llms(cfg: Config, days: list[Day], latest: Day | None) -> Path:
    """写给 LLM 读的站点上下文。刻意保持可机读的短句结构，不写营销话术。"""
    total = sum(len(d.matches) for d in days)
    comps = sorted({m.competition for d in days for m in d.matches if m.competition})
    today_line = ""
    if latest:
        refs = "\n".join(
            f"- [{m.home.name} vs {m.away.name} · {m.competition}]({_url(cfg, f'matches/{m.match_id}.html')})"
            f"　{m.code}　{m.kickoff}"
            for m in latest.matches[:40]
        )
        today_line = f"\n## 最新一日（{latest.date}，共 {len(latest.matches)} 场）\n\n{refs}\n"

    text = f"""# {cfg.site_name}

> {cfg.site_tagline}。{cfg.site_desc}

## 站点性质

- 定位：逐场公开足球赛事的**结构化量化数据**与赛前结论，面向数据分析与技术交流。
- 不构成任何投注建议，不提供购买方案，不做准确率承诺。
- 结论在赛前生成并固化；赛后只回填真实赛果，**不修改任何已发布结论**。
- 每篇单场页面内嵌「结论指纹」（覆盖赛前全部结论字段的 SHA-256 前 12 位），
  赛后回填后指纹不变，可用于验证结论未被事后调整。

## 数据契约

产出遵循统一 schema v{SCHEMA_VERSION}，字段为：

- `info`：编号、赛事、对阵、开球时间、场地
- `home` / `away`：队名、所属联赛、国家、名次、积分、场次、战绩、进失、近况
- `odds`：胜平负、让球、进球数盘口与其去水概率
- `metrics_home` / `metrics_away`：六维战力（进攻 / 防守 / 控制 / 状态 / 阵容 / 战意）
- `momentum`：0–90 分钟进球威胁度曲线
- `forecasts`：方向 / 比分 / 进球 / 半全场 四类结论及各自概率与次选
- `result`：赛后半场与全场比分，及四个维度是否命中

任一维度缺失时对应区块自动省略，不做补白。

## 覆盖范围

归档 {len(days)} 个交易日、共 {total} 场；涉及赛事：{'、'.join(comps) if comps else '—'}。
{today_line}
## 归档

- [全部交易日索引]({_url(cfg, 'days/')})
- 单场页面路径：`matches/<match_id>.html`
- 每日归档路径：`days/<YYYY-MM-DD>.html`

## 免责

{cfg.disclaimer}
"""
    return _w(cfg, "llms.txt", text)


# ---------------------------------------------------------------- robots


def write_robots(cfg: Config) -> Path:
    base = cfg.base_url.rstrip("/")
    return _w(cfg, "robots.txt", f"""User-agent: *
Allow: /

# LLM 上下文发现
Allow: /llms.txt

Sitemap: {base}/sitemap.xml
Sitemap: {base}/sitemap-today.xml
""")


# ---------------------------------------------------------------- sitemap


def write_sitemaps(cfg: Config, days: list[Day]) -> tuple[Path, Path]:
    today = datetime.now(timezone.utc).date().isoformat()

    def urlset(entries: list[tuple[str, str]]) -> str:
        body = "\n".join(
            f"  <url><loc>{quote(loc, safe=':/?#=&')}</loc><lastmod>{last}</lastmod></url>"
            for loc, last in entries
        )
        return (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            f"{body}\n</urlset>\n"
        )

    all_entries: list[tuple[str, str]] = [(_url(cfg, "/"), today)]
    today_entries: list[tuple[str, str]] = [(_url(cfg, "/"), today)]

    latest = max(days, key=lambda d: d.date) if days else None
    for d in sorted(days, key=lambda x: x.date):
        all_entries.append((_url(cfg, f"days/{d.date}.html"), d.date))
        for m in d.matches:
            last = (m.result.settled_at[:10] if (m.result and m.result.settled_at) else d.date)
            entry = (_url(cfg, f"matches/{m.match_id}.html"), last)
            all_entries.append(entry)
            if latest and d.date == latest.date:
                today_entries.append(entry)

    return (
        _w(cfg, "sitemap.xml", urlset(all_entries)),
        _w(cfg, "sitemap-today.xml", urlset(today_entries)),
    )


# ---------------------------------------------------------------- 数据快照


def write_dataset(cfg: Config, days: list[Day]) -> Path:
    """把全部结构化结论导出成单个 JSON，方便第三方核验与二次分析。"""
    out_dir = cfg.out_dir / "data"
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": SCHEMA_VERSION,
        "site": cfg.site_name,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "days": [
            {"date": d.date, "matches": [m.to_dict() for m in d.matches]}
            for d in sorted(days, key=lambda x: x.date)
        ],
    }
    p = out_dir / "dataset.json"
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")

    # 逐日快照：便于 diff 出「哪一天的结论被改过」
    daily = out_dir / "days"
    daily.mkdir(exist_ok=True)
    for d in days:
        (daily / f"{d.date}.json").write_text(
            json.dumps({"date": d.date, "matches": [m.to_dict() for m in d.matches]},
                       ensure_ascii=False, indent=1),
            encoding="utf-8",
        )
    return p


def _w(cfg: Config, rel: str, text: str) -> Path:
    p = cfg.out_dir / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p
