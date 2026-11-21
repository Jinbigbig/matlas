"""一条命令跑完实时链路：采集 → 快照 → 部署（CF + GH 两站）。

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
import datetime as dt
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from push_live_pages import OUT, _load_dotenv, build_snapshot, deploy  # noqa: E402

PY = Path(sys.executable)
COLLECT_ITEMS = ("ticks", "fixtures", "live")
GH_SITE = ROOT / "_site_gh"
PUB = ROOT / ".publish"


def collect(only: str) -> bool:
    """调宿主体彩源采集入口（含 fixtures 后的对阵上下文重建）。"""
    cmd = [str(PY), str(ROOT / "scripts" / "collect_lottery.py")]
    if only != "all":
        cmd += ["--only", only]
    t0 = time.time()
    p = subprocess.run(cmd, cwd=str(ROOT))
    print(f"[update] 采集 {only}: exit={p.returncode}（{time.time() - t0:.0f}s）")
    return p.returncode == 0


def _git(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(PUB)] + args, cwd=str(ROOT),
                          capture_output=True, text=True)


def sync_gh() -> bool:
    """把刚写好的快照同步到 GH 产物并推送；失败只告警，不影响 CF 已上线。"""
    if not OUT.is_dir():
        return False
    dests = []
    if GH_SITE.is_dir():
        dests.append(GH_SITE / "data" / "live")
    if (PUB / ".git").exists():
        dests.append(PUB / "data" / "live")
    if not dests:
        print("[update] 未找到 GH 产物目录，跳过同步")
        return False
    copied = 0
    for dest in dests:
        dest.mkdir(parents=True, exist_ok=True)
        for f in sorted(OUT.glob("*.json")):
            shutil.copy2(f, dest / f.name)
            copied += 1
    print(f"[update] GH 快照已同步 {copied} 个文件")
    if not (PUB / ".git").exists():
        return True
    br = _git(["rev-parse", "--abbrev-ref", "HEAD"])
    if br.returncode or br.stdout.strip() != "gh-pages":
        print("[update] .publish 不在 gh-pages，跳过推送", file=sys.stderr)
        return False
    _git(["add", "-A", "data/live"])
    if _git(["diff", "--cached", "--quiet"]).returncode == 0:
        print("[update] GH 快照无变化，跳过提交")
        return True
    name = _git(["config", "user.name"]).stdout.strip()
    email = _git(["config", "user.email"]).stdout.strip()
    msg = f"site: 实时快照同步 {dt.datetime.now():%Y-%m-%d %H:%M}"
    cmd = ["-c", f"user.name={name}", "-c", f"user.email={email}",
           "commit", "-q", "-m", msg, "--only", "--", "data/live"]
    c = _git(cmd)
    if c.returncode:
        print(f"[update] GH 提交失败：{c.stderr.strip()[:200]}", file=sys.stderr)
        return False
    p = _git(["push", "origin", "gh-pages"])
    if p.returncode:
        print(f"[update] GH 推送失败：{p.stderr.strip()[:200]}", file=sys.stderr)
        return False
    print(f"[update] GH 已发布：{msg}")
    return True


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
    sync_gh()
    print(f"[update] 完成：{len(written)} 天快照已上线（{time.time() - t0:.0f}s）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
