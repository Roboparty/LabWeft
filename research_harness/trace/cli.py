"""`labweft trace ...` and `labweft mcp`: CLI generated from the same tool registry the MCP server exposes."""
from __future__ import annotations

from .tools import TOOLS, call, t_collect, t_ingest, t_resume


def add_cli(sub) -> None:
    t = sub.add_parser("trace", help="REA-style investigation of a research project (local or over SSH)")
    ts = t.add_subparsers(dest="trace_command", required=True)
    c = ts.add_parser("collect", help="Run/resume the read-only probe next to the data and build the index")
    c.add_argument("workspace")
    c.add_argument("--source", required=True, help="short name for this source, e.g. INTACT")
    c.add_argument("--root", required=True, help="absolute folder on the host")
    c.add_argument("--host", help="SSH alias; omit for a local folder")
    c.add_argument("--remote-dir", help="writable scratch dir on the host (default ~/.labweft-trace)")
    c.add_argument("--no-wait", action="store_true")
    c.add_argument("--exclude", action="append", default=[])
    c.add_argument("--max-text-bytes", type=int)
    r = ts.add_parser("resume", help="Wait for a detached remote probe, download its part and rebuild the index")
    r.add_argument("workspace")
    r.add_argument("--source", required=True)
    g = ts.add_parser("ingest", help="Rebuild the disposable index from collected parts")
    g.add_argument("workspace")
    g.add_argument("--source", required=True)
    for name, (_, desc, props, req) in TOOLS.items():
        p = ts.add_parser(name.removeprefix("trace_"), help=desc)
        p.add_argument("workspace")
        for key, schema in props.items():
            if key == "workspace":
                continue
            flag = "--" + key.replace("_", "-")
            if schema.get("type") == "integer":
                p.add_argument(flag, type=int, dest=key)
            elif schema.get("type") == "boolean":
                p.add_argument(flag, action="store_true", dest=key)
            elif schema.get("type") == "array":
                p.add_argument(flag, action="append", dest=key)
            else:
                p.add_argument(flag, dest=key, required=key in req)
    m = sub.add_parser("mcp", help="Serve the trace tools over stdio MCP")
    m.add_argument("workspace", nargs="?")


def dispatch(args):
    if args.command == "mcp":
        from .mcp import serve
        serve(args.workspace)
        return None
    cmd = args.trace_command
    if cmd == "collect":
        return t_collect(args.workspace, args.source, args.root, host=args.host, remote_dir=args.remote_dir,
                         wait=not args.no_wait, exclude=args.exclude, max_text_bytes=args.max_text_bytes)
    if cmd == "resume":
        return t_resume(args.workspace, args.source)
    if cmd == "ingest":
        return t_ingest(args.workspace, args.source)
    tool = "trace_" + cmd
    _, _, props, _ = TOOLS[tool]
    payload = {k: getattr(args, k) for k in props if getattr(args, k, None) not in (None, False)}
    payload["workspace"] = args.workspace
    return call(tool, payload)
