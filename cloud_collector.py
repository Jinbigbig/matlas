"""本地云采集器：常驻循环调度 matlas 自己的采集脚本，喂给本机实时服务。

定位：这台机器是「本地云」——采集、计算、服务都在本机闭环，不读 jinbet。
全部脚本在 scripts/collectors/，按数据时效性分层跑：
  对阵上下文 5 分钟 / 天气·情报·阵容 30 分钟 / 伤停·裁判·积分榜 60 分钟。
体彩源（盘口/赛程/全玩法赔率）因容器内 HTTP 567 走宿主侧 collect_lottery.py 任务。
每个脚本独立进程 + 超时 + 异常隔离，单个失败不影响其它；单点运行锁防多开。

用法：
  python cloud_collector.py            # 常驻循环
  python cloud_collector.py --once     # 每类跑一次即退出（自检/手工补采）
  python cloud_collector.py --only odds_ticks   # 只跑某一类一次
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
COLLECTORS = ROOT / "scripts" / "collectors"
PY = Path(sys.executable)
LOCK = ROOT / "data" / ".cloud_collector.lock"
LOG = ROOT / "data" / "cloud_collector.log"
SYNC_AFTER_RUN = os.environ.get("MATLAS_SYNC_AFTER_RUN", "1") not in ("0", "false", "no")
# 容器内 PID 命名空间隔离：主进程恒为 1，文件锁会误判"已在运行"。
# Compose 已保证单实例，容器模式跳过文件锁；宿主直跑仍保留。
SKIP_LOCK = os.environ.get("MATLAS_SKIP_LOCK", "0") not in ("0", "false", "no")
_sync_pending = False

# 频率分层（秒）：脚本按数据变化速度分组，避免高频抓冷数据。
# 体彩源（盘口时序/赛程赛果/全玩法赔率）容器出口被 HTTP 567 拒，走宿主侧
# collect_lottery.py 任务；这里只调度公开网页源与对阵上下文生成。
TASKS: dict[int, list[tuple[str, str]]] = {
    300: [("对阵上下文", "_context")],  # 特殊标签：调用 make_today_context.py
    1800: [
        ("天气", "_fetch_weather.py"),
        ("赛前情报", "_fetch_intel.py"),
        ("首发阵容", "_fetch_lineups.py"),
        ("比赛时间", "_fetch_match_times.py"),
    ],
    3600: [
        ("伤停", "_fetch_injuries.py"),
        ("伤停补充", "_fetch_injuries_extra.py"),
        ("港马会", "_fetch_hkjc.py"),
        ("红彩", "_fetch_hongcai.py"),
        ("裁判", "_fetch_referee.py"),
        ("体彩积分榜", "_fetch_sporttery_standings.py"),
        ("联赛资料", "_fetch_league_data.py"),
    ],
}

# 单脚本超时（秒）：留足慢脚本余量，卡死则杀掉继续。
TIMEOUT = 180


def _mark_sync() -> None:
    """标记本轮有采集写入，稍后统一入库，避免每个脚本各连一次库。"""
    global _sync_pending
    if SYNC_AFTER_RUN:
        _sync_pending = True


def _flush_sync() -> None:
    """把变化的 JSON 增量写进 PostgreSQL；失败不影响采集循环。"""
    global _sync_pending
    if not _sync_pending:
        return
    _sync_pending = False
    try:
        import db_sync
        result = db_sync.sync_once()
        if result.get("written"):
            log(f"入库 {result['written']} 项（ PostgreSQL ）")
    except Exception as e:  # noqa: BLE001
        log(f"入库跳过：{type(e).__name__}: {e}")


def log(msg: str) -> None:
    stamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{stamp}] {msg}"
    try:
        print(line, flush=True)
    except UnicodeEncodeError:
        print(line.encode("gbk", errors="replace").decode("gbk"), flush=True)
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def run_task(label: str, script: str) -> None:
    # 全部脚本在 scripts/collectors/；cwd=ROOT，脚本内相对路径（scripts/matches_data.json 等）基于此。
    name = "make_today_context.py" if script == "_context" else script
    path = COLLECTORS / name
    if not path.exists():
        log(f"跳过 {label}：脚本不存在 {path}")
        return
    t0 = time.time()
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    try:
        p = subprocess.run(
            [str(PY), str(path)], cwd=str(ROOT), timeout=TIMEOUT,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env,
        )
        secs = time.time() - t0
        out = (p.stdout or b"").decode("utf-8", errors="replace").strip()
        if p.returncode == 0:
            tail = out.splitlines()[-1:] or [""]
            log(f"完成 {label}（{secs:.0f}s）：{tail[0][:120]}")
            _mark_sync()
        else:
            log(f"失败 {label}（{secs:.0f}s，exit={p.returncode}）：{out[-200:]}")
    except subprocess.TimeoutExpired:
        log(f"超时 {label}（>{TIMEOUT}s），已终止")
    except Exception as e:  # noqa: BLE001
        log(f"异常 {label}：{type(e).__name__}: {e}")


def acquire_lock() -> bool:
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    if LOCK.exists():
        try:
            pid = int(LOCK.read_text(encoding="utf-8").strip())
            import os
            if os.name == "nt":
                out = subprocess.run(
                    ["tasklist", "/FI", f"PID eq {pid}"],
                    capture_output=True, text=True, timeout=5,
                ).stdout
                if str(pid) in out:
                    return False
            elif Path(f"/proc/{pid}").exists():
                return False
        except (ValueError, OSError, subprocess.SubprocessError):
            pass
    LOCK.write_text(str(__import__("os").getpid()), encoding="utf-8")
    return True


def release_lock() -> None:
    try:
        LOCK.unlink(missing_ok=True)
    except OSError:
        pass


def once(only: str | None = None) -> None:
    if only:
        for group in TASKS.values():
            for label, script in group:
                if only in script or only == label:
                    run_task(label, script)
        return
    for interval in sorted(TASKS):
        for label, script in TASKS[interval]:
            run_task(label, script)
    _flush_sync()


def loop() -> None:
    if not SKIP_LOCK and not acquire_lock():
        log("已有采集器在运行，退出")
        return
    log(f"本地云采集器启动：collectors={COLLECTORS}，python={PY}")
    next_run = {interval: 0.0 for interval in TASKS}
    try:
        while True:
            now = time.time()
            for interval in sorted(TASKS):
                if now >= next_run[interval]:
                    for label, script in TASKS[interval]:
                        run_task(label, script)
                    next_run[interval] = time.time() + interval
            _flush_sync()
            time.sleep(5)
    except KeyboardInterrupt:
        log("采集器收到中断，退出")
    finally:
        release_lock()


def main() -> None:
    ap = argparse.ArgumentParser(description="本地云采集器")
    ap.add_argument("--once", action="store_true", help="每类跑一次即退出")
    ap.add_argument("--only", help="只跑指定脚本/标签一次，如 odds_ticks")
    args = ap.parse_args()
    if args.once or args.only:
        once(args.only)
    else:
        loop()


if __name__ == "__main__":
    main()
