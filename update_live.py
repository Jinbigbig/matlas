"""一条命令跑完实时链路：采集 → 快照 → 部署。

采集只写本地 data/*.json，页面读的是边缘上的 /api/live，必须把
_site/data/live/*.json 重新生成并部署，线上才会变。此前要手动跑
collect_lottery.py 和 push_live_pages.py 两个脚本，漏掉任一步都会
「脚本跑了但页面没变」。

用法：
    python update_live.py                  # 采集（盘口/赛程/比分）+ 快照 + 部署
    python update_live.py --only live      # 只采比分直播
    python update_live.py --no-collect     # 跳过采集，重新出快照并部署
    python update_live.py --dry-run        # 采集 + 快照，不部署
    python update_live.py --days 3         # 快照推今天起 3 天
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from push_live_pages import _load_dotenv, build_snapshot, deploy  # noqa: E402

PY = Path(sys.executable)
COLLECT_ITEMS = ("ticks", "fixtures", "live")


def collect(only: str) -> bool:
    """调宿主体彩源采集入口（含 fixtures 后的对阵上下文重建）。"""
    cmd = [str(PY), str(ROOT / "scripts" / "collect_lottery.py")]
    if only != "all":
        cmd += ["--only", only]
    t0 = time.time()
    p = subprocess.run(cmd, cwd=str(ROOT))
    print(f"[update] 采集 {only}: exit={p.returncode}（{time.time() - t0:.0f}s）")
    return p.returncode == 0


def main() -> int:
    ap = argparse.ArgumentParser(description="实时链路：采集 → 快照 → 部署")
    ap.add_argument("--only", choices=list(COLLECT_ITEMS) + ["all"], default="all")
    ap.add_argument("--no-collect", action="store_true", help="跳过采集")
    ap.add_argument("--dry-run", action="store_true", help="只生成快照，不部署")
    ap.add_argument("--days", type=int, default=2, help="快照推今天起 N 天（默认 2）")
    args = ap.parse_args()

    _load_dotenv()
    t0 = time.time()

    if not args.no_collect:
        if not collect(args.only):
            print("[update] 采集失败，终止（未部署，线上保持上一版）")
            return 1

    written = build_snapshot(args.days)
    if not written:
        print("[update] 快照为空，终止")
        return 1
    if args.dry_run:
        print(f"[update] dry-run：快照已生成，未部署（{time.time() - t0:.0f}s）")
        return 0

    if not deploy():
        print("[update] 部署失败")
        return 1
    print(f"[update] 完成：{len(written)} 天快照已上线（{time.time() - t0:.0f}s）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
