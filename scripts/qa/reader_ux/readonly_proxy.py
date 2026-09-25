"""READ-ONLY local proxy to the production Fanfic API, for visual QA of a local build.

- Only GET/HEAD are forwarded. Every write (POST/PUT/PATCH/DELETE) gets 405 and is
  logged, so QA can never mutate production (listen counts, progress, comments...).
- No Authorization / Cookie headers are forwarded upstream.
- CORS is answered locally for http://localhost:<port> origins only.
- Transient upstream 502/503/504 are retried twice.
- Catalog reads are cached for 4h (in the temp dir, never in the repo): upstream
  `/api/novels/{id}` was measured at 180s+ during a degraded period. Signed audio
  URLs (`/api/audio/...`) are never cached — they expire.

Port: some low ports are reserved on this Windows machine (8765 fails with
WinError 10013); 38123 works.
"""
import sys
import tempfile
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

UPSTREAM = "https://fas-prod-api.onrender.com"
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 38123
LOG = []
CACHE = {}
CACHE_FILE = Path(tempfile.gettempdir()) / "reader_ux_qa_proxy_cache.json"


def _load_cache():
    import base64
    try:
        raw = __import__("json").loads(CACHE_FILE.read_text(encoding="utf-8"))
        for k, (ts, st, ct, b64) in raw.items():
            CACHE[k] = (ts, st, ct, base64.b64decode(b64))
    except Exception:
        pass


def _save_cache():
    import base64
    try:
        CACHE_FILE.write_text(__import__("json").dumps(
            {k: (v[0], v[1], v[2], base64.b64encode(v[3]).decode()) for k, v in CACHE.items()}), encoding="utf-8")
    except Exception:
        pass


class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _cors(self):
        origin = self.headers.get("Origin", "")
        if origin.startswith("http://localhost:") or origin.startswith("http://127.0.0.1:"):
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Allow-Methods", "GET, HEAD, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _refuse(self):
        body = b'{"detail":"read-only QA proxy: writes are disabled"}'
        sys.stderr.write(f"[proxy] REFUSED {self.command} {self.path}\n")
        self.send_response(405)
        self._cors()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    do_POST = do_PUT = do_PATCH = do_DELETE = _refuse

    def _send_cached(self, status, ct, data):
        self.send_response(status)
        if ct:
            self.send_header("Content-Type", ct)
        self._cors()
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _forward(self, head=False):
        url = UPSTREAM + self.path
        # QA-only cache for slow catalog reads (upstream /api/novels/{id} can take
        # 10-180s). Signed audio URLs are NOT cached (they expire).
        cacheable = not head and not self.path.startswith("/api/audio/")
        hit = CACHE.get(self.path) if cacheable else None
        if hit and time.time() - hit[0] < 4 * 3600:
            return self._send_cached(hit[1], hit[2], hit[3])
        last = None
        for i in range(3):
            try:
                req = urllib.request.Request(url, method="HEAD" if head else "GET",
                                             headers={"User-Agent": "fanfic-local-qa-proxy",
                                                      "Accept": self.headers.get("Accept", "*/*")})
                with urllib.request.urlopen(req, timeout=240) as r:
                    data = b"" if head else r.read()
                    if cacheable and r.status == 200:
                        CACHE[self.path] = (time.time(), r.status, r.headers.get("Content-Type"), data)
                        _save_cache()
                    self.send_response(r.status)
                    ct = r.headers.get("Content-Type")
                    if ct:
                        self.send_header("Content-Type", ct)
                    self._cors()
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    if not head:
                        self.wfile.write(data)
                    return
            except urllib.error.HTTPError as e:
                if e.code in (502, 503, 504) and i < 2:
                    time.sleep(1.5 * (i + 1))
                    continue
                data = e.read()
                self.send_response(e.code)
                self._cors()
                self.send_header("Content-Type", e.headers.get("Content-Type", "application/json"))
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return
            except Exception as e:  # noqa
                last = e
                time.sleep(1.0)
        body = f'{{"detail":"proxy upstream error: {last}"}}'.encode()
        self.send_response(502)
        self._cors()
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self._forward()

    def do_HEAD(self):
        self._forward(head=True)

    def log_message(self, fmt, *args):
        sys.stderr.write("[proxy] " + (fmt % args) + "\n")


if __name__ == "__main__":
    _load_cache()
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), H)
    sys.stderr.write(f"[proxy] read-only proxy on http://localhost:{PORT} -> {UPSTREAM}\n")
    srv.serve_forever()
