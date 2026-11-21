"""matlas 本地实时数据服务（方案②）。

零第三方依赖，仅用 Python 标准库。两种运行方式共用同一套数据生成逻辑：

  1) HTTP 服务（方案②）：python live_server.py --port 8787
     前端 fetch http://<隧道域名>/api/live?date=YYYY-MM-DD

  2) 静态导出（方案③后门）：python live_server.py --export
     生成 data/live/<日期>.json + index.json，推到 gh-pages 后前端 fetch 同域 JSON。
     切换②→③时前端只改 LIVE_API_BASE 一个地址，无需重写逻辑。

数据源（混合源）：
  - 场次骨架（match_id / code / 简称队名）：matlas data/days/*.json
  - 实时盘口时序：jinbet odds_ticks.json
  - 赛果比分：jinbet results_data.json
  - 开赛状态：jinbet fixtures.json
  队名匹配沿用 import_jinbet.py 的双向包含兜底，避免简称/全称对不上。
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent
DAYS_DIR = ROOT / "data" / "days"
EXPORT_DIR = ROOT / "data" / "live"
JINBET = Path("C:/Users/Jin/jinbet")
ODDS_TICKS = JINBET / "odds_ticks.json"
RESULTS = JINBET / "results_data.json"
FIXTURES = JINBET / "fixtures.json"

CACHE: dict[str, tuple[float, object]] = {}


def _read(path: Path):
    """读 JSON，带 mtime 缓存：文件没变就不重复解析。"""
    try:
        mt = path.stat().st_mtime
    except OSError:
        return None
    hit = CACHE.get(str(path))
    if hit and hit[0] == mt:
        return hit[1]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = None
    CACHE[str(path)] = (mt, data)
    return data


def _name_match(a: str | None, b: str | None) -> bool:
    """队名双向包含匹配（竞彩简称 ↔ 原始全/简称），与 import_jinbet 同口径。"""
    return bool(a and b and len(a) >= 2 and len(b) >= 2 and (a in b or b in a))


def _lookup(src: dict, date: str, home: str, away: str):
    """按 日期_主_客 取原始记录：精确命中优先，再按队名双向包含兜底。"""
    if not src:
        return None
    hit = src.get(f"{date}_{home}_{away}")
    if hit is not None:
        return hit
    prefix = date + "_"
    for key, val in src.items():
        if not str(key).startswith(prefix):
            continue
        parts = str(key)[len(prefix):].split("_")
        if len(parts) != 2:
            continue
        if _name_match(home, parts[0]) and _name_match(away, parts[1]):
            return val
    return None


def _fixture_status(fx_days: dict, date: str, code: str, home: str, away: str) -> str:
    """从赛程源取开赛状态：优先竞彩编号，退回队名双向包含。"""
    rows = fx_days.get(date) or []
    if code:
        for r in rows:
            if r.get("code") == code:
                return str(r.get("st") or "")
    for r in rows:
        if _name_match(home, r.get("home")) and _name_match(away, r.get("away")):
            return str(r.get("st") or "")
    return ""


def _tick_num(v):
    try:
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _trend_html(tk: list) -> str:
    """服务端出图：复用 pages._odds_trend 生成完整赔率变化片段（双 SVG + 表格）。

    画图规则与静态站完全共用一份代码，前端拿到直接替换 DOM，零重画逻辑。
    """
    if not tk:
        return ""
    try:
        from types import SimpleNamespace
        from matlas.render import pages
        return pages._odds_trend(SimpleNamespace(extras={"odds_ticks": tk}))
    except Exception:
        return ""


def _skeleton(date: str, day: dict | None, fx_rows: list[dict]) -> list[tuple[str, str, str, str]]:
    """统一场次骨架 → [(match_id, code, home, away)]。

    优先 data/days（含 match_id、分析数据）；当日未 import 时用 fixtures 兜底，
    使「今天有赛程但还没 import」时实时接口仍有数据（本地云自采集后常态）。
    """
    out: list[tuple[str, str, str, str]] = []
    if day:
        for m in day.get("matches") or []:
            out.append((
                str(m.get("match_id") or ""),
                str(m.get("code") or ""),
                str((m.get("home") or {}).get("name") or ""),
                str((m.get("away") or {}).get("name") or ""),
            ))
        return out
    for r in fx_rows:
        fid = str(r.get("fid") or r.get("mid") or "")
        mid = f"fx-{fid}" if fid else f"fx-{r.get('home')}-{r.get('away')}"
        out.append((mid, str(r.get("code") or ""),
                    str(r.get("home") or ""), str(r.get("away") or "")))
    return out


def live_for(date: str, *, light: bool = False) -> dict | None:
    """生成某日的实时数据（HTTP 与静态导出共用）。

    light=True 供比赛列表用：只回比分/状态/盘口数字，去掉体积大的 trend_html，
    避免整页 12 天各拉一份完整曲线。
    """
    day = _read(DAYS_DIR / f"{date}.json")
    fx_days = ((_read(FIXTURES) or {}).get("days")) or {}
    fx_rows = fx_days.get(date) or []
    if not day and not fx_rows:
        return None

    skeleton = _skeleton(date, day, fx_rows)
    if not skeleton:
        return None

    ticks_src = ((_read(ODDS_TICKS) or {}).get("ticks")) or {}
    results_src = _read(RESULTS) or {}

    matches = []
    for match_id, code, home, away in skeleton:
        tk = _lookup(ticks_src, date, home, away) or []
        res = _lookup(results_src, date, home, away) or {}

        # 最新盘口（胜平负 + 让球首档），供前端替换表头数字
        odds = {}
        if tk:
            last = tk[-1]
            for src_k, dst_k in (("胜", "home"), ("平", "draw"), ("负", "away")):
                v = _tick_num(last.get(src_k))
                if v is not None:
                    odds[dst_k] = v
            rq = (last.get("让球") or [None])[0] or {}
            hcp = _tick_num(rq.get("handicap"))
            if hcp is not None:
                odds["handicap"] = hcp

        item = {
            "match_id": match_id,
            "code": code,
            "home": home,
            "away": away,
            "status": _fixture_status(fx_days, date, code, home, away),
            "score": str(res.get("fullScore") or "").replace(":", "-"),
            "half": str(res.get("halfScore") or "").replace(":", "-"),
            "odds": odds,
        }
        if not light:
            item["odds_ticks"] = tk
            item["trend_html"] = _trend_html(tk)
        matches.append(item)

    return {
        "date": date,
        "updated": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "matches": matches,
    }


def available_dates() -> list[str]:
    if not DAYS_DIR.exists():
        return []
    return sorted(p.stem for p in DAYS_DIR.glob("20??-??-??.json"))


def export_all() -> list[str]:
    """方案③后门：把实时数据导出成静态 JSON。"""
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    dates = available_dates()
    written = []
    for date in dates:
        obj = live_for(date)
        if not obj:
            continue
        (EXPORT_DIR / f"{date}.json").write_text(
            json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
        )
        written.append(date)
    idx = {"updated": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "dates": written}
    (EXPORT_DIR / "index.json").write_text(
        json.dumps(idx, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    return written


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, obj, *, cache: str = "no-store"):
        body = json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Cache-Control", cache)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urlparse(self.path)
        qs = parse_qs(u.query)
        if u.path == "/api/health":
            return self._send(200, {
                "ok": True,
                "now": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "dates": len(available_dates()),
            })
        if u.path == "/api/live":
            date = (qs.get("date") or [""])[0]
            if not date:
                dates = available_dates()
                date = dates[-1] if dates else ""
            light = (qs.get("light") or [""])[0] in ("1", "true", "yes")
            obj = live_for(date, light=light)
            return self._send(200, obj) if obj else self._send(404, {"error": f"no data for {date}"})
        if u.path.startswith("/api/live/"):
            mid = u.path.rsplit("/", 1)[-1]
            date = mid[:10] if len(mid) >= 10 else ""
            obj = live_for(date)
            if obj:
                hit = next((m for m in obj["matches"] if m["match_id"] == mid), None)
                if hit:
                    return self._send(200, {"date": date, "match": hit})
            return self._send(404, {"error": f"no match {mid}"})
        if u.path == "/api/dates":
            return self._send(200, {"dates": available_dates()})
        return self._send(404, {"error": "not found"})

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.end_headers()

    def log_message(self, fmt, *args):
        sys.stderr.write("[live] %s - %s\n" % (self.address_string(), fmt % args))


def main() -> int:
    ap = argparse.ArgumentParser(description="matlas 本地实时数据服务")
    ap.add_argument("--port", type=int, default=8787)
    ap.add_argument("--bind", default="127.0.0.1")
    ap.add_argument("--export", action="store_true", help="导出静态 JSON 到 data/live（方案③后门）")
    args = ap.parse_args()

    if args.export:
        dates = export_all()
        print(f"[live] exported {len(dates)} days -> {EXPORT_DIR}")
        return 0

    srv = ThreadingHTTPServer((args.bind, args.port), Handler)
    print(f"[live] serving http://{args.bind}:{args.port}  ({len(available_dates())} days)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n[live] stopped")
    finally:
        srv.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
