"""HTTP layer: JSON API under /api, static files from web/."""
import json, mimetypes, re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import browse, config as C, items, spells, talents


def _flag(p, name):
    return p.get(name, "0") in ("1", "true", "yes")


class Handler(BaseHTTPRequestHandler):
    def _send(self, body, ctype="application/json", code=200):
        b = body if isinstance(body, bytes) else body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(b)
        except (BrokenPipeError, ConnectionResetError):
            pass                                              # the browser navigated away mid-response

    def _json(self, obj):
        self._send(json.dumps(obj), code=200 if obj is not None else 404)

    def _static(self, path):
        f = (C.WEB_DIR / (path.lstrip("/") or "index.html")).resolve()
        if C.WEB_DIR.resolve() not in f.parents or not f.is_file():
            return self._send("not found", "text/plain", 404)
        self._send(f.read_bytes(), mimetypes.guess_type(f.name)[0] or "application/octet-stream")

    def do_GET(self):
        u = urlparse(self.path)
        p = {k: v[0] for k, v in parse_qs(u.query).items()}
        sod = _flag(p, "sod")
        path = u.path
        if not path.startswith("/api/"):
            return self._static(path)
        if path == "/api/meta":
            return self._json(browse.meta())
        if path == "/api/search":
            return self._json(spells.search(p.get("q", ""), sod) + [dict(i, kind="item") for i in items.search(p.get("q", ""), sod)])
        if path == "/api/items":
            return self._json(items.tree(sod))
        if path == "/api/items/list":
            return self._json(items.listing(p.get("cls", ""), p.get("sub", ""), p.get("q", ""), int(p.get("offset", 0)),
                                            int(p.get("limit", 300)), sod))
        if path == "/api/browse":
            return self._json(browse.tree(sod))
        if path == "/api/browse/list":
            return self._json(browse.listing(p.get("cat", ""), p.get("sub", ""), p.get("q", ""),
                                             int(p.get("offset", 0)), int(p.get("limit", 300)), sod))
        if path == "/api/talents":
            return self._json(talents.index())
        m = re.fullmatch(r"/api/talents/(\d+)", path)
        if m:
            return self._json(talents.tree(m.group(1)))
        m = re.fullmatch(r"/api/item/(\d+)", path)
        if m:
            return self._json(items.item(m.group(1)))
        m = re.fullmatch(r"/api/itip/(\d+)", path)
        if m:
            it = items.item(m.group(1))
            return self._json(it and items.tip_from(it))
        m = re.fullmatch(r"/api/tip/(\d+)", path)
        if m:
            return self._json(spells.tip(m.group(1)))
        m = re.fullmatch(r"/api/spell/(\d+)", path)
        if m:
            return self._json(spells.spell(m.group(1), sod))
        self._send("not found", "text/plain", 404)

    def log_message(self, *args):
        pass


def serve(port=C.PORT):
    talents.spell_talents()                                   # build the talent trees once, so the first spell page is fast
    print(f"http://localhost:{port}")
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
