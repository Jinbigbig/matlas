"""一条命令跑完实时链路：采集 → 赛果录入 → 页面重建 → 快照发布。

静态快照只维护 GH 一份（.publish → gh-pages）；CF 站靠 KV，KV 不可达时
前端跨域读 GH 那份兜底，两站不再各存一份（2026-11-22 架构红线）。

采集只写本地 data/*.json；页面读的是边缘 KV / GH 静态快照。此前要手动跑
collect_lottery.py 和 push_live_pages.py 两个脚本，漏掉任一步都会
「脚本跑了但页面没变」。

用法：
    python update_live.py                  # 采集 + 赛果录入 + 重建 + GH 快照发布
    python update_live.py --only live      # 只采比分直播
    python update_live.py --no-collect     # 跳过采集，重新出快照并发布
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

from ingest_finished_results import ingest as ingest_results  # noqa: E402
from cf_push import push_gh_snapshot  # noqa: E402
from push_live_pages import _load_dotenv, deploy  # noqa: E402

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


def rebuild_and_publish() -> bool:
    """有新增赛果时：import 回填命中 → 构建 → 发布两站页面（快照最后单独写）。"""
    for label, cmd in (
        ("import", [str(PY), str(ROOT / "import_jinbet.py")]),
        ("build", [str(PY), str(ROOT / "build.py"), "--strict"]),
    ):
        t0 = time.time()
        p = subprocess.run(cmd, cwd=str(ROOT))
        print(f"[update] {label}: exit={p.returncode}（{time.time() - t0:.0f}s）")
        if p.returncode != 0:
            return False
    # publish.sh 构建并发布 GH 页面（会清空 .publish，故快照须在其后写）。
    p = subprocess.run(["bash", str(ROOT / "publish.sh")], cwd=str(ROOT))
    print(f"[update] publish(GH 页面): exit={p.returncode}")
    if p.returncode != 0:
        return False
    # CF 页面 HTML 独立部署（与本页快照无关；CF 实时数据走 KV）。
    if not deploy():
        print("[update] CF 页面部署失败", file=sys.stderr)
        return False
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description="实时链路：采集 → 赛果录入 → 重建 → GH 快照")
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

    # 采集后有已结束场次就补录赛果，重建页面让四维命中标签上线。
    added = ingest_results()
    if added and not args.dry_run:
        if not rebuild_and_publish():
            print("[update] 赛果回填/页面发布失败，仍继续快照发布")

    # 唯一快照：只写 GH 那份。放在页面发布之后，避免被 publish.sh 的清空抹掉。
    if not push_gh_snapshot(args.days, publish=not args.dry_run):
        print("[update] 快照发布失败")
        return 1
    print(f"[update] 完成：{args.days} 天快照已上线 GH（{time.time() - t0:.0f}s）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
