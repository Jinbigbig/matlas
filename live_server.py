"""matlas 本地实时数据服务（方案②）。

零第三方依赖，仅用 Python 标准库。两种运行方式共用同一套数据生成逻辑：

  1) HTTP 服务（方案②）：python live_server.py --port 8787
     前端 fetch http://<隧道域名>/api/live?date=YYYY-MM-DD

  2) 静态导出（方案③后门）：python live_server.py --export
     生成 data/live/<日期>.json + index.json，推到 gh-pages 后前端 fetch 同域 JSON。
     切换②→③时前端只改 LIVE_API_BASE 一个地址，无需重写逻辑。

数据源（全部 matlas 自采，不读 jinbet）：
  - 场次骨架（match_id / code / 简称队名）：matlas data/days/*.json
  - 实时盘口时序：data/odds_ticks.json（宿主任务采集）
  - 赛果比分：data/results_data.json（基线 + 赛程源实时兜底）
  - 开赛状态：data/fixtures.json（宿主任务采集）
  - 全玩法赔率：data/odds_full.json（宿主任务采集）
  - 比分直播：data/live_scores.json（体彩官方，补半场比分/细状态/比赛分钟）
  队名匹配沿用双向包含兜底，避免简称/全称对不上。
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
DATA = ROOT / "data"
DAYS_DIR = DATA / "days"
EXPORT_DIR = DATA / "live"
ODDS_TICKS = DATA / "odds_ticks.json"
RESULTS = DATA / "results_data.json"
FIXTURES = DATA / "fixtures.json"
ODDS_FULL = DATA / "odds_full.json"
LIVE_SCORES = DATA / "live_scores.json"  # 体彩官方比分直播

CACHE: dict[str, tuple[float, object]] = {}

try:
    import pg_store
except ImportError:  # 未随仓库部署时退回纯文件模式
    pg_store = None  # type: ignore[assignment]

_KEY_BY_PATH = {
    str(ODDS_TICKS): "odds_ticks",
    str(RESULTS): "results_data",
    str(FIXTURES): "fixtures",
}


def _key_for(path: Path) -> str | None:
    """数据源路径 → live_data 表 key；days 文件按日期命名。"""
    s = str(path)
    if s in _KEY_BY_PATH:
        return _KEY_BY_PATH[s]
    if path.parent == DAYS_DIR and path.stem.startswith("20"):
        return f"days/{path.stem}"
    return None


def _read(path: Path):
    """读数据源：优先 PostgreSQL（db_sync 已同步），库不可用回退文件。

    文件读取带 mtime 缓存；库读取由 pg_store 内部处理连接失败，
    返回 None 时自动落到文件，保证任何部署形态都能出数据。
    """
    key = _key_for(path)
    if key and pg_store is not None:
        data = pg_store.read(key)
        if data is not None:
            return data
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


def _fixture_row(fx_days: dict, date: str, code: str, home: str, away: str) -> dict:
    """从赛程源找对应场次行：优先竞彩编号，退回队名双向包含。"""
    rows = fx_days.get(date) or []
    if code:
        for r in rows:
            if r.get("code") == code:
                return r
    for r in rows:
        if _name_match(home, r.get("home")) and _name_match(away, r.get("away")):
            return r
    return {}


def _fixture_status(fx_days: dict, date: str, code: str, home: str, away: str) -> str:
    """从赛程源取开赛状态：优先竞彩编号，退回队名双向包含。"""
    return str(_fixture_row(fx_days, date, code, home, away).get("st") or "")


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
    full_src = ((_read(ODDS_FULL) or {}).get("data")) or {}
    # 体彩比分直播：key 为「日期|竞彩编号」，与 match_id 同源
    live_src = ((_read(LIVE_SCORES) or {}).get("matches")) or {}

    matches = []
    for match_id, code, home, away in skeleton:
        tk = _lookup(ticks_src, date, home, away) or []
        res = _lookup(results_src, date, home, away) or {}
        fx_row = _fixture_row(fx_days, date, code, home, away)
        ls = (live_src.get(f"{date}|{code}") if code else None) or {}
        # 全玩法赔率：key 为「日期_竞彩编号」，与 match_id 同源
        of = full_src.get(f"{date}_{code}") or {}

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
            # 体彩状态更细（进行中 / 已完成），优先采用；缺失回退赛程源
            "status": str(ls.get("status") or fx_row.get("st") or ""),
            # 赛后补录 results_data 优先；其次赛程源；最后体彩直播比分
            "score": (str(res.get("fullScore") or "").replace(":", "-")
                      or str(fx_row.get("score") or "")
                      or str(ls.get("score") or "").replace(":", "-")),
            "half": (str(res.get("halfScore") or "").replace(":", "-")
                     or str(ls.get("half") or "").replace(":", "-")),
            "odds": odds,
        }
        # 分钟数只在体彩判定「进行中」时才有意义：直播接口的 matchMinute
        # 会滞后于竞彩状态（已结束时仍回旧分钟），挂到已结束场次会自相矛盾。
        if ls.get("minute") and ls.get("status") == "进行中":
            item["minute"] = str(ls["minute"])
        if of:
            item["odds_full"] = of
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
                "postgres": bool(pg_store and pg_store.available()),
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
