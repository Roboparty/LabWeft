"""Read-only, loopback-only dashboard. No arbitrary filesystem or shell endpoint."""
from __future__ import annotations
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import secrets
from urllib.parse import urlparse, parse_qs
import webbrowser
from .store import Store, HarnessError, atomic_write, canonical
from .reasoning import compare, drift
from .organization import organization

STATIC = Path(__file__).parent / "static"


def presentation(store: Store) -> dict:
    state = store.load()
    return {**state, "comparison": compare(state), "drift": drift(state), "organization": organization(state), "mode": "live"}


def export_html(store: Store, output: Path, *, include_evidence: bool = False,
                site_links: list[dict] | None = None) -> Path:
    data = presentation(store)
    data["mode"] = "snapshot"
    if site_links is not None:
        if not isinstance(site_links, list) or len(site_links) > 50:
            raise HarnessError("Invalid project links")
        ids = set()
        for entry in site_links:
            if not isinstance(entry, dict) or set(entry) != {"id", "name", "href"}:
                raise HarnessError("Invalid project link")
            if any(not isinstance(entry[key], str) or not entry[key].strip() for key in entry):
                raise HarnessError("Empty project link field")
            if entry["id"] in ids or not re.fullmatch(r"[A-Za-z0-9._/-]+\.html", entry["href"]) or entry["href"].startswith("/") or "//" in entry["href"]:
                raise HarnessError("Unsafe or duplicate project link")
            ids.add(entry["id"])
        if data["project"]["id"] not in ids:
            raise HarnessError("Project links must include the current project")
        data["site_links"] = site_links
    data["evidence_texts"] = {}
    if include_evidence:
        # Explicit opt-in: this copy may include private research text.
        # The source browser lists every indexed file, not only files attached to
        # semantic nodes. Include their text blobs as well so View is truthful.
        referenced = {f["sha256"] for f in data["files"].values()
                      if f.get("snapshot") == "text_snapshot" and f.get("sha256")}
        referenced |= {r["sha256"] for n in data["nodes"].values()
                       for r in n.get("evidence", [])}
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


def export_site(workspaces: list[Path], output_dir: Path, *, include_evidence: bool = False) -> dict:
    """Write separate private snapshots with a shared top project switcher."""
    if not 1 <= len(workspaces) <= 50:
        raise HarnessError("Export site needs 1–50 workspaces")
    projects = []
    used_ids, used_slugs = set(), set()
    for workspace in workspaces:
        store = Store(workspace)
        project = store.load()["project"]
        if project["id"] in used_ids:
            raise HarnessError("Duplicate workspace in export site")
        used_ids.add(project["id"])
        slug = re.sub(r"[^a-z0-9]+", "-", project["name"].lower()).strip("-") or "project"
        if slug in used_slugs:
            slug += "-" + project["id"][-8:]
        used_slugs.add(slug)
        projects.append({"store": store, "id": project["id"], "name": project["name"], "slug": slug})
    output_dir = output_dir.expanduser().resolve()
    links = [{"id": item["id"], "name": item["name"], "href": item["slug"] + ".html"} for item in projects]
    for item in projects:
        export_html(item["store"], output_dir / "projects" / (item["slug"] + ".html"),
                    include_evidence=include_evidence, site_links=links)
    index_links = [{**link, "href": "projects/" + link["href"]} for link in links]
    export_html(projects[0]["store"], output_dir / "index.html",
                include_evidence=include_evidence, site_links=index_links)
    return {"index": str(output_dir / "index.html"),
            "projects": [{"id": item["id"], "name": item["name"],
                          "page": str(output_dir / "projects" / (item["slug"] + ".html"))}
                         for item in projects],
            "privacy": "Private snapshots, not uploaded. Review embedded sources before sharing."}


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
