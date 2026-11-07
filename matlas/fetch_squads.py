"""球员情报抓取：从球小策球员数据中心拉各联赛球员评分，落盘为本地缓存。

数据口径（2026-11-07 实测确认）：
- 榜单页 `https://www.qiuxiaoce.com/player-rankings/` 是服务端渲染，内嵌
  `ABV2_DC = {apiUrl, ajaxUrl, nonce}`；联赛切换走 admin-ajax 的
  `abv2_dc_rankings`，参数 `league_id / metric / limit(<=100) / offset`。
- nonce 与 WordPress 会话绑定，**每次运行都要先抓榜单页取新的**，写死会 403。
- 返回字段即「第三代球员全息评分」里对外公开的 6 项：
  OTI 进攻威胁 / DII 防守参与 / GIM 比赛影响力 / 状态评分(0-10 EWMA) /
  稳定度 / 疲劳负荷。文档宣传的「硬仗属性」「缺阵影响」**并未在接口出现**。

输出：`data/squads/<league_id>.json`
    {"league_id","league_name","updated_at","fetched_at","players":[...]}

用法：
    python -m matlas.fetch_squads            # 只抓当前 days 数据用到的联赛
    python -m matlas.fetch_squads --all      # 抓全部 51 个联赛
    python -m matlas.fetch_squads --force    # 忽略当日缓存，强制重抓
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "data" / "squads"
SITE = "https://www.qiuxiaoce.com"
RANK_URL = f"{SITE}/player-rankings/"
AJAX_URL = f"{SITE}/wp-admin/admin-ajax.php"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

# 球小策联赛 ID → 站内联赛名。站内命名与之不同的一律走别名。
LEAGUES: dict[str, str] = {
    "英超": "39", "西甲": "140", "意甲": "135", "德甲": "78", "法甲": "61",
    "欧冠": "2", "欧协": "848", "英冠": "40", "西乙": "141", "德乙": "79",
    "意乙": "136", "法乙": "62", "葡超": "94", "荷甲": "88", "比甲": "144",
    "苏超": "179", "瑞士超": "207", "希腊超": "197", "阿甲": "128", "巴甲": "71",
    "美职联": "253", "墨超": "262", "沙特联": "307", "日职联": "98", "澳超": "188",
    "英甲": "41", "葡甲": "95", "荷乙": "89", "比乙": "145", "波兰超": "106",
    "捷甲": "345", "罗甲": "283", "丹麦超": "119", "瑞典超": "113", "挪超": "103",
    "芬超": "244", "爱超": "357", "智利甲": "265", "世俱杯": "15",
    "U21欧预赛": "850", "英锦赛": "46", "友谊赛": "10", "中超": "169",
    "南俱杯": "11", "巴乙": "72", "巴西杯": "73", "德国杯": "81",
    "欧国联": "5", "英乙": "42", "解放者杯": "13", "韩K联": "292",
}

# 站内叫法与球小策不一致的别名
ALIAS = {
    "欧协联": "欧协",
    "瑞超": "瑞典超",
    "欧罗巴": "",        # 球小策无欧联杯独立榜，跳过
    "亚冠精英": "",
    "亚冠乙": "",
}

PAGE = 100          # 接口 limit 上限
SLEEP = 0.4         # 限流 30 次/分钟，留余量


def _get(url: str, *, referer: str = "") -> str:
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept-Language": "zh-CN,zh;q=0.9",
        **({"Referer": referer} if referer else {}),
    })
    with urllib.request.urlopen(req, timeout=40) as r:
        return r.read().decode("utf-8", "replace")


def _post_nonce(nonce: str, data: dict) -> dict:
    body = urllib.parse.urlencode({**data, "nonce": nonce}).encode()
    req = urllib.request.Request(AJAX_URL, data=body, headers={
        "User-Agent": UA,
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": RANK_URL,
        "Origin": SITE,
    })
    with urllib.request.urlopen(req, timeout=40) as r:
        raw = r.read().decode("utf-8", "replace")
    if raw.strip() == "-1":
        raise RuntimeError("nonce 失效（返回 -1）")
    return json.loads(raw)


def grab_nonce() -> str:
    """榜单页内嵌 ABV2_DC.nonce。必须每次现取 —— 写死会在几小时后 403。"""
    html = _get(RANK_URL)
    m = re.search(r'ABV2_DC\s*=\s*(\{.*?\});', html, re.S)
    if not m:
        raise RuntimeError("榜单页没有 ABV2_DC 配置，页面结构可能已改")
    cfg = json.loads(m.group(1))
    nonce = cfg.get("nonce") or ""
    if not nonce:
        raise RuntimeError("ABV2_DC 里没有 nonce")
    return nonce


def fetch_league(nonce: str, league_id: str, name: str) -> dict:
    players: list[dict] = []
    offset = 0
    total = None
    while True:
        res = _post_nonce(nonce, {
            "action": "abv2_dc_rankings",
            "league_id": league_id,
            "metric": "overall",
            "limit": PAGE,
            "offset": offset,
        })
        if not res.get("success"):
            raise RuntimeError(f"联赛 {name}({league_id}) 返回失败: {res}")
        data = res["data"]
        batch = data.get("players") or []
        players.extend(batch)
        pg = data.get("pagination") or {}
        total = pg.get("total")
        offset += len(batch)
        if not batch or not pg.get("has_more"):
            break
        time.sleep(SLEEP)
    updated = max((p.get("updated_at") or "" for p in players), default="")
    return {
        "league_id": league_id,
        "league_name": name,
        "updated_at": updated,
        "fetched_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total": total if total is not None else len(players),
        "players": players,
    }


def _wanted_leagues() -> list[tuple[str, str]]:
    """当前 days 数据里出现过的联赛 → [(id, 球小策联赛名)]。"""
    seen: set[str] = set()
    for f in sorted((ROOT / "data" / "days").glob("*.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        for m in d.get("matches") or []:
            comp = (m.get("competition") or "").strip()
            if comp:
                seen.add(comp)
    out = []
    for comp in sorted(seen):
        key = ALIAS.get(comp, comp)
        lid = LEAGUES.get(key) if key else None
        if lid:
            out.append((lid, key))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="抓全部联赛")
    ap.add_argument("--force", action="store_true", help="忽略当日缓存")
    args = ap.parse_args(argv)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    targets = ([(v, k) for k, v in LEAGUES.items()] if args.all else _wanted_leagues())
    if not targets:
        print("[squads] 没有可抓的联赛（days 数据为空？）")
        return 0

    today = time.strftime("%Y-%m-%d")
    print(f"[squads] 目标联赛 {len(targets)} 个")
    nonce = grab_nonce()
    print(f"[squads] nonce={nonce[:8]}…")

    ok = skip = fail = 0
    for lid, name in targets:
        dst = OUT_DIR / f"{lid}.json"
        if dst.exists() and not args.force:
            try:
                old = json.loads(dst.read_text(encoding="utf-8"))
                if (old.get("fetched_at") or "")[:10] == today and old.get("players"):
                    skip += 1
                    print(f"  · {name}({lid}) 当日已抓，跳过 {len(old['players'])} 人")
                    continue
            except Exception:
                pass
        try:
            d = fetch_league(nonce, lid, name)
            dst.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
            ok += 1
            print(f"  ✓ {name}({lid}) {len(d['players'])} 人，更新于 {d['updated_at'][:16]}")
        except Exception as e:  # 单联赛失败不阻断整批
            if "nonce 失效" in str(e):
                print("  ! nonce 失效，重新获取后重试一次")
                try:
                    nonce = grab_nonce()
                    d = fetch_league(nonce, lid, name)
                    dst.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
                    ok += 1
                    print(f"  ✓ {name}({lid}) {len(d['players'])} 人")
                    continue
                except Exception as e2:
                    e = e2
            fail += 1
            print(f"  ✗ {name}({lid}) {e}")
        time.sleep(SLEEP)

    print(f"[squads] 完成：新抓 {ok} / 跳过 {skip} / 失败 {fail}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
