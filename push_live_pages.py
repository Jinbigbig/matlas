"""KV 配额耗尽时的手动通道：把实时数据写成静态快照并部署到 Pages。

CF 免费版 KV 每日写入上限 1000 次，用尽后 PUT 一律 429（code 10048），
当天再无办法写入。此脚本改走 Pages 部署：数据落成 data/live/*.json，
边缘函数读不到 KV 时自动回退读这些文件，前端无需改动。

用法：
    python push_live_pages.py               # 生成今天+明天的快照并部署
    python push_live_pages.py --dry-run     # 只生成文件，不部署
    python push_live_pages.py --days 3      # 推今天起 3 天

前提：_site 必须是最近一次 build.py 的产物（本脚本只覆盖 data/live/）。
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import live_server  # noqa: E402

SITE = ROOT / "_site"
OUT = SITE / "data" / "live"


def _load_dotenv() -> None:
    """读项目 .env 的 KEY=VALUE（不覆盖已有环境变量）。"""
    p = ROOT / ".env"
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


def _write(path: Path, obj) -> int:
    raw = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    path.write_text(raw, encoding="utf-8")
    return len(raw.encode("utf-8"))


def build_snapshot(days: int = 2) -> list[str]:
    if not (SITE / "index.html").exists():
        print("[pages] 缺少 _site/index.html，请先运行 build.py --strict", file=sys.stderr)
        return []
    OUT.mkdir(parents=True, exist_ok=True)
    today = dt.date.today()
    written: list[str] = []
    total = 0
    for i in range(days):
        d = (today + dt.timedelta(days=i)).isoformat()
        full = live_server.live_for(d, light=False)
        if not full:
            continue
        total += _write(OUT / f"{d}.json", full)
        light = live_server.live_for(d, light=True)
        if light:
            total += _write(OUT / f"light-{d}.json", light)
        written.append(d)
        live = sum(1 for m in full.get("matches") or [] if m.get("status") == "进行中")
        print(f"[pages] {d}: {len(full.get('matches') or [])} 场（进行中 {live}）")
    idx = {
        "updated": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "dates": live_server.available_dates(),
    }
    total += _write(OUT / "index.json", idx)
    print(f"[pages] 快照合计 {total / 1024:.0f} KB → {OUT.relative_to(ROOT)}")
    return written


def deploy() -> bool:
    token = os.environ.get("CF_API_TOKEN", "").strip()
    if not token:
        print("[pages] 缺少 CF_API_TOKEN", file=sys.stderr)
        return False
    env = dict(os.environ, CLOUDFLARE_API_TOKEN=token)
    # 代理会让 wrangler 上传失败，显式剔除
    for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
        env.pop(k, None)
    cmd = (f'npx wrangler pages deploy "{SITE}" --project-name matlas '
           f'--branch main --commit-dirty=true')
    print("[pages] 部署中…")
    p = subprocess.run(cmd, cwd=str(ROOT), env=env, shell=True)
    return p.returncode == 0


def main() -> int:
    ap = argparse.ArgumentParser(description="把实时数据快照部署到 Pages（绕过 KV 配额）")
    ap.add_argument("--days", type=int, default=2, help="推今天起 N 天（默认 2）")
    ap.add_argument("--dry-run", action="store_true", help="只生成文件，不部署")
    args = ap.parse_args()

    _load_dotenv()
    written = build_snapshot(args.days)
    if not written:
        return 1
    if args.dry_run:
        print("[pages] dry-run：未部署")
        return 0
    ok = deploy()
    print(f"[pages] {'完成' if ok else '部署失败'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
