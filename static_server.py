"""本地云静态站点服务：零依赖、gzip 压缩、no-store。

用法：python static_server.py [port] [root]
默认：8788 / <项目>/_site
"""
from __future__ import annotations

import gzip
import mimetypes
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

COMPRESSIBLE = {
    "text/html",
    "text/css",
    "text/javascript",
    "application/javascript",
    "application/x-javascript",
    "application/json",
    "application/xml",
    "text/xml",
    "text/plain",
    "image/svg+xml",
    "application/manifest+json",
}
_CACHE: dict[str, tuple[float, bytes]] = {}
_MIN_GZIP = 512


class Handler(SimpleHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def __init__(self, *args, root: Path, **kwargs):
        super().__init__(*args, directory=str(root), **kwargs)

    def do_GET(self) -> None:
        self._serve(False)

    def do_HEAD(self) -> None:
        self._serve(True)

    def _serve(self, head: bool) -> None:
        try:
            path = Path(self.translate_path(self.path))
        except Exception:
            self.send_error(400, "Bad Request")
            return
        if path.is_dir():
            path = path / "index.html"
        if not path.is_file():
            self.send_error(404, "Not Found")
            return

        ctype = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        base_type = ctype.split(";", 1)[0].strip().lower()
        raw = path.read_bytes()
        try:
            mtime = path.stat().st_mtime
        except OSError:
            mtime = 0.0

        gz = (
            base_type in COMPRESSIBLE
            and len(raw) >= _MIN_GZIP
            and "gzip" in self.headers.get("Accept-Encoding", "").lower()
        )
        if gz:
            key = str(path)
            cached = _CACHE.get(key)
            if cached and cached[0] == mtime:
                body = cached[1]
            else:
                body = gzip.compress(raw, compresslevel=6)
                _CACHE[key] = (mtime, body)
        else:
            body = raw

        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        if gz:
            self.send_header("Content-Encoding", "gzip")
            self.send_header("Vary", "Accept-Encoding")
        self.end_headers()
        if not head:
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

    def log_message(self, fmt: str, *args) -> None:
        return


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8788
    root = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(__file__).resolve().parent / "_site"
    root = root.resolve()
    server = ThreadingHTTPServer(
        ("0.0.0.0", port),
        lambda *a, **k: Handler(*a, root=root, **k),
    )
    print(f"static server {port} -> {root}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
