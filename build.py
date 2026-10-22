#!/usr/bin/env python
"""Matlas 构建入口。

    python build.py                     构建 data/days 下全部交易日
    python build.py --strict            红线自检命中即退出非零
    python build.py --reference 2026-10-22
                                        额外拉第三方对照数据（需联网，默认关闭）

全程离线可跑：不联网、不依赖 CDN、不引第三方 JS。
"""

from __future__ import annotations

import argparse
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from matlas.config import Config, DEFAULT_BASE_URL  # noqa: E402
from matlas.pipeline import render, stamp  # noqa: E402
from matlas.rules import check_site, report  # noqa: E402
from matlas.source.base import LocalDirSource, merge_reference  # noqa: E402


def build(cfg: Config, *, strict: bool = False, reference_date: str | None = None) -> int:
    t0 = datetime.now(timezone.utc)

    source = LocalDirSource(cfg.days_dir)
    days = source.load_days()
    if not days:
        print(f"[!] {cfg.days_dir} 下没有交易日数据，先放一份符合契约的 JSON 进去。")
        print("    契约定义见 matlas/models.py，示例见 data/days/。")
        return 1

    for d in days:
        for m in d.matches:
            stamp(m)

    if reference_date:
        try:
            from matlas.source import qiuxiaoce as ref

            raw = ref.fetch_day(reference_date)
            for d in days:
                if d.date == reference_date:
                    merge_reference(d, raw, ref.REF_ATTRIBUTION)
            print(f"[i] 对照数据已并入 {reference_date}：{len(raw.get('matches', []))} 场")
            print(f"    {ref.REF_ATTRIBUTION}")
        except Exception as ex:  # noqa: BLE001
            print(f"[!] 对照源不可用，已跳过（不影响构建）：{ex}")

    stats = render(cfg, days, source)
    print(
        f"[✓] 生成完毕：{stats['days']} 个交易日 / {stats['matches']} 场 / "
        f"{stats['files']} 个文件 → {cfg.out_dir}"
    )

    violations = check_site(cfg.out_dir)
    print(report(violations))
    if violations and strict:
        print("[×] strict 模式下红线违规不允许发布。")
        return 2

    dt = (datetime.now(timezone.utc) - t0).total_seconds()
    print(f"[✓] 用时 {dt:.2f}s")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Matlas 静态站点构建器")
    ap.add_argument("--data", type=Path, default=ROOT / "data", help="数据目录")
    ap.add_argument("--out", type=Path, default=ROOT / "_site", help="输出目录")
    ap.add_argument("--base-url", default=DEFAULT_BASE_URL, help="站点根 URL，默认线上地址")
    ap.add_argument("--site-name", default="Matlas")
    ap.add_argument("--strict", action="store_true", help="红线违规时以非零码退出")
    ap.add_argument("--reference", metavar="YYYY-MM-DD", help="启用第三方对照源（需联网）")
    ns = ap.parse_args()

    cfg = Config(
        site_root=ROOT,
        out_dir=ns.out,
        data_dir=ns.data,
        base_url=ns.base_url.rstrip("/"),
        site_name=ns.site_name,
    )
    try:
        return build(cfg, strict=ns.strict, reference_date=ns.reference)
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
