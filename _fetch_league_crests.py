"""补齐联赛徽标素材（一次性工具，不属于每日数据流水线）。

来源与队徽同源口径（竞彩参考站）：
  A. /league-topic/ 索引页：每张联赛卡的 <img class="la-logo">
  B. /bi-sai-lie-biao/ 比赛列表页：<div class="ms-league" title="联赛名"> 内的 <img>

素材落到 assets/logo/competitions/{leagues|cups}/{id}.png，id 与来源一致，
便于长期对照。**本脚本不改任何源码**：matlas/logos.py 的 LEAGUE_CREST 映射
由人工维护，跑完脚本后按输出的建议手工补即可。站内联赛名与参考站差异较大
（如「欧罗巴」↔「欧联」「瑞超」↔「瑞典超」），NAME_MAP 只做名称对照，
是否启用某个联赛徽标仍以 LEAGUE_CREST 为准。

用法：
    python _fetch_league_crests.py            # 抓素材 + 报告覆盖情况
    python _fetch_league_crests.py --check   # 不抓取，只报告覆盖情况
"""
from __future__ import annotations

import json
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "assets/logo/competitions"
LOGOS_PY = ROOT / "matlas/logos.py"
WP = "https://www.qiuxiaoce.com/wp-content/"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
      "Referer": "https://www.qiuxiaoce.com/"}

# 本站联赛名 → 参考站联赛名
NAME_MAP = {
    "亚冠乙": "亚冠2", "亚冠精英": "亚冠", "巴甲": "巴甲", "巴西杯": "巴西杯",
    "德乙": "德乙", "德国杯": "德国杯", "德甲": "德甲", "意甲": "意甲", "挪超": "挪超",
    "日职乙": "日职乙", "日职联": "日职联", "欧冠": "欧冠", "欧国联": "欧国联",
    "欧罗巴": "欧联", "沙特联": "沙特联", "法乙": "法乙", "法甲": "法甲", "澳超": "澳超",
    "瑞超": "瑞典超", "美职联": "美职联", "芬超": "芬超", "英冠": "英冠",
    "英联杯": "英联杯", "英超": "英超", "英锦标赛": "英锦赛", "荷乙": "荷乙",
    "荷兰杯": "荷兰杯", "荷甲": "荷甲", "葡超": "葡超", "西甲": "西甲",
    "韩K联": "韩K联",
}


def get(url: str) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def parse() -> dict[str, tuple[str, str]]:
    """参考站联赛名 → (leagues|cups, id)。"""
    by_name: dict[str, tuple[str, str]] = {}

    topic = get("https://www.qiuxiaoce.com/league-topic/").decode("utf-8", "ignore")
    for blk in re.split(r'<a href="https://www\.qiuxiaoce\.com/league-topic/', topic)[1:]:
        nm = re.search(r'class="la-name">([^<]*)<', blk)
        im = re.search(r'<img src="([^"]+)" class="la-logo"', blk)
        if not (nm and im):
            continue
        src = im.group(1)
        m = re.search(r"/(leagues|cups)/(\d+)\.png", src)
        if m:
            by_name.setdefault(nm.group(1), (m.group(1), m.group(2)))
            continue
        m = re.search(r"/[a-zA-Z0-9_.-]*?(\d+)(?:-150x150)?\.png$", src)
        if m:
            by_name.setdefault(nm.group(1), ("leagues", m.group(1)))

    listing = get("https://www.qiuxiaoce.com/bi-sai-lie-biao/").decode("utf-8", "ignore")
    for m in re.finditer(
            r'class="ms-league" title="([^"]+)"[^>]*>\s*<img[^>]*'
            r'src="https://www\.qiuxiaoce\.com/wp-content/logo/competitions/(leagues|cups)/(\d+)\.png"',
            listing):
        by_name.setdefault(m.group(1), (m.group(2), m.group(3)))
    return by_name


def candidates(kind: str, ident: str) -> list[str]:
    """同一徽标在参考站可能有多个落点，逐个试。"""
    return [
        f"{WP}logo/competitions/{kind}/{ident}.png",
        f"{WP}uploads/2026/01/{ident}.png",
        f"{WP}uploads/2026/01/{ident}-150x150.png",
        f"{WP}uploads/2026/01/league_logo_{ident}.png",
        f"{WP}uploads/2026/01/league_logo_{ident}-150x150.png",
    ]


def download(by_name: dict[str, tuple[str, str]]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for nm, (kind, ident) in sorted(by_name.items()):
        dest = OUT / kind / f"{ident}.png"
        if dest.exists() and dest.stat().st_size > 0:
            continue
        for url in candidates(kind, ident):
            try:
                blob = get(url)
            except Exception:
                continue
            if blob[:4] == b"\x89PNG":
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(blob)
                print(f"  下载 {kind}/{ident}.png  {nm}")
                break


def report(by_name: dict[str, tuple[str, str]]) -> None:
    src = LOGOS_PY.read_text(encoding="utf-8")
    block = re.search(r"LEAGUE_CREST: dict\[str, str\] = \{(.*?)\n\}", src, re.S)
    active = dict(re.findall(r'"([^"]+)": "([^"]+)"', block.group(1))) if block else {}
    print(f"当前启用映射 {len(active)} 条，参考站解析 {len(by_name)} 个联赛")

    missing = []
    for ours, theirs in NAME_MAP.items():
        got = by_name.get(theirs)
        rel = f"{got[0]}/{got[1]}" if got else None
        if not rel or not (OUT / f"{rel}.png").exists():
            missing.append((ours, theirs, rel))
        elif ours not in active:
            print(f"  可新增：{ours} -> {rel}")
    if missing:
        print("上游无图或未收录（沿用首字占位圆）：" +
              "、".join(ours for ours, _, _ in missing))


if __name__ == "__main__":
    check_only = "--check" in sys.argv
    parsed = parse()
    print(f"参考站联赛 {len(parsed)} 个")
    if not check_only:
        download(parsed)
    report(parsed)
