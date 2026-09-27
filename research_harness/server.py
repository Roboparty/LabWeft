"""Read-only, loopback-only dashboard. No arbitrary filesystem or shell endpoint."""
from __future__ import annotations
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
from urllib.parse import urlparse, parse_qs
import webbrowser
from .store import Store, HarnessError, atomic_write, canonical
from .reasoning import compare, drift

STATIC = Path(__file__).parent / "static"


def presentation(store: Store) -> dict:
    state = store.load()
    return {**state, "comparison": compare(state), "drift": drift(state), "mode": "live"}


def export_html(store: Store, output: Path, *, include_evidence: bool = False) -> Path:
    data = presentation(store)
    data["mode"] = "snapshot"
    data["evidence_texts"] = {}
    if include_evidence:
        # Explicit opt-in: this copy may include private research text.
        referenced = {r["sha256"] for n in data["nodes"].values() for r in n.get("evidence", [])}
        total = 0
        for sha in sorted(referenced):
            try:
                text = store.read_blob(sha)
                if total + len(text.encode()) > 5 * 1024 * 1024:
                    continue
                data["evidence_texts"][sha] = text
                total += len(text.encode())
            except HarnessError:
                continue
    packed = canonical(data).replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    html = html.replace('<link rel="stylesheet" href="/app.css">', "<style>" + (STATIC / "app.css").read_text(encoding="utf-8") + "</style>")
    js = (STATIC / "app.js").read_text(encoding="utf-8")
    html = html.replace('<script src="/app.js" defer></script>', '<script id="snapshot-data" type="application/json">' + packed + '</script><script defer>' + js + '</script>')
    atomic_write(output, html)
    return output


def make_server(store: Store, port: int = 8787, token: str | None = None) -> ThreadingHTTPServer:
    access_token = token or secrets.token_urlsafe(32)
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args: object) -> None:
            # Never log the initial URL containing the bearer token.
            return

        def send_body(self, status: int, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            host = self.headers.get("Host", "")
            valid_hosts = {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}
            if host not in valid_hosts:
                self.send_body(403, b"Invalid host", "text/plain; charset=utf-8")
                return
            path = urlparse(self.path).path
            if self.headers.get("Sec-Fetch-Site") == "cross-site":
                self.send_body(403, b"Cross-site access blocked", "text/plain; charset=utf-8")
                return
            if path.startswith("/api/"):
                supplied = self.headers.get("X-Research-Token", "")
                if not hmac.compare_digest(supplied, access_token):
                    self.send_body(403, b"Open the private URL printed by labweft serve", "text/plain; charset=utf-8")
                    return
                try:
                    if path == "/api/state":
                        self.send_body(200, canonical(presentation(store)).encode(), "application/json; charset=utf-8")
                    elif path == "/api/evidence":
                        sha = parse_qs(urlparse(self.path).query).get("sha", [""])[0]
                        state = store.load()
                        known = {f.get("sha256") for f in state["files"].values()}
                        known |= {r["sha256"] for n in state["nodes"].values() for r in n.get("evidence", [])}
                        if sha not in known:
                            raise HarnessError("Unknown evidence hash")
                        self.send_body(200, store.read_blob(sha).encode(), "text/plain; charset=utf-8")
                    else:
                        self.send_body(404, b"Not found", "text/plain; charset=utf-8")
                except HarnessError as exc:
                    self.send_body(400, str(exc).encode(), "text/plain; charset=utf-8")
                return
            mapping = {"/": ("index.html", "text/html; charset=utf-8"),
                       "/app.css": ("app.css", "text/css; charset=utf-8"),
                       "/app.js": ("app.js", "application/javascript; charset=utf-8")}
            if path not in mapping:
                self.send_body(404, b"Not found", "text/plain; charset=utf-8")
                return
            name, kind = mapping[path]
            self.send_body(200, (STATIC / name).read_bytes(), kind)

        def do_POST(self) -> None:
            self.send_body(405, b"Read-only dashboard. Use the reviewed CLI workflow for writes.", "text/plain; charset=utf-8")

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.access_token = access_token
    return server


def serve(store: Store, port: int, open_browser: bool) -> None:
    store.load()
    server = make_server(store, port)
    url = f"http://127.0.0.1:{server.server_port}/?token={server.access_token}"
    print(f"LabWeft — local read-only dashboard\n{url}\nKeep this URL private. Ctrl+C stops the server.", flush=True)
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
