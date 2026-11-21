"""宿主侧体彩源采集入口：盘口时序 + 赛程赛果，写 matlas/data/。

容器内访问体彩接口 webapi.sporttery.cn 一律 HTTP 567（出口 IP 被拒），
故这两个脚本由宿主计划任务调度（走 127.0.0.1:65053 代理）。
全玩法赔率仍由 scripts/fetch_odds_full.py 单独任务采集。

用法：python scripts/collect_lottery.py [--only ticks|fixtures]
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COLLECTORS = ROOT / "scripts" / "collectors"
PY = Path(sys.executable)
TASKS = {
    "ticks": ("盘口时序", "_fetch_odds_ticks.py"),
    "fixtures": ("赛程赛果", "_fetch_fixtures.py"),
}


def run(key: str) -> bool:
    label, name = TASKS[key]
    path = COLLECTORS / name
    if not path.exists():
        print(f"[lottery] 脚本缺失 {path}")
        return False
    try:
        p = subprocess.run(
            [str(PY), str(path)], cwd=str(ROOT), timeout=180,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )
        out = (p.stdout or b"").decode("utf-8", errors="replace").strip()
        tail = out.splitlines()[-1:] or [""]
        print(f"[lottery] {label}: exit={p.returncode} {tail[0][:120]}")
        return p.returncode == 0
    except subprocess.TimeoutExpired:
        print(f"[lottery] {label}: 超时")
        return False
    except Exception as e:  # noqa: BLE001
        print(f"[lottery] {label}: 异常 {type(e).__name__}: {e}")
        return False


def main() -> int:
    ap = argparse.ArgumentParser(description="matlas 宿主体彩源采集")
    ap.add_argument("--only", choices=list(TASKS) + ["all"], default="all")
    args = ap.parse_args()
    keys = list(TASKS) if args.only == "all" else [args.only]
    ok = 0
    for k in keys:
        if run(k):
            ok += 1
    # 赛程更新后重建当日对阵上下文，供容器侧网页源脚本读取
    if "fixtures" in keys:
        run_ctx = subprocess.run(
            [str(PY), str(COLLECTORS / "make_today_context.py")],
            cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )
        print("[lottery] 上下文: " + (run_ctx.stdout or b"").decode("utf-8", errors="replace").strip()[-120:])
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
