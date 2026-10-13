"""`labweft trace ...` and `labweft mcp`: CLI generated from the same tool registry the MCP server exposes."""
from __future__ import annotations

from .tools import TOOLS, call, t_collect, t_ingest, t_resume


def add_cli(sub) -> None:
    t = sub.add_parser("trace", help="REA-style investigation of a research project (local or over SSH)")
    ts = t.add_subparsers(dest="trace_command", required=True)
    c = ts.add_parser("collect", help="Run/resume the read-only probe next to the data and build the index")
    c.add_argument("workspace")
    c.add_argument("--source", required=True, help="short name for this source, e.g. myproject")
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
        p.add_argument("--format", choices=["json", "text"], default="json", dest="out_format",
                       help="text = compact indented outline for reading in a terminal or agent context")
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
    out = call(tool, payload)
    if getattr(args, "out_format", "json") == "text":
        hits = out.get("hits") if isinstance(out, dict) else None
        if isinstance(hits, list) and hits and all(isinstance(h, dict) and "path" in h for h in hits):
            # grep-style: one line per hit, so it can be piped into further filters
            for h in hits:
                print(f"{h['path']}:{h.get('line') or ''}: {h.get('text', '')}")
            rest = {k: v for k, v in out.items() if k != "hits"}
            print(compact(rest))
        else:
            print(compact(out))
        return None
    return out


def _scalar(v) -> str:
    if isinstance(v, float):
        return f"{v:.6g}"
    if isinstance(v, str):
        v = v.replace("\n", " ")
        return v if len(v) <= 240 else v[:237] + "..."
    return "null" if v is None else str(v)


def compact(obj, indent: int = 0) -> str:
    """Indented outline: dict keys as `key:`, short scalar lists inline, list items as `-` blocks. No data dropped
    beyond long strings (pagination already bounds lists)."""
    pad = "  " * indent
    lines = []
    if isinstance(obj, list) and obj and all(isinstance(x, dict) and set(x) == {"n", "text"} for x in obj):
        return "\n".join(f"{pad}{x['n']:>5}: {x['text']}" for x in obj)  # file lines read like a listing
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "_meta":
                continue
            if isinstance(v, (dict, list)) and v:
                if isinstance(v, list) and all(not isinstance(x, (dict, list)) for x in v) and len(v) <= 12:
                    lines.append(f"{pad}{k}: [{', '.join(_scalar(x) for x in v)}]")
                elif isinstance(v, dict) and all(not isinstance(x, (dict, list)) for x in v.values()) and len(v) <= 8:
                    lines.append(f"{pad}{k}: {{{', '.join(f'{a}={_scalar(b)}' for a, b in v.items())}}}")
                else:
                    lines.append(f"{pad}{k}:")
                    lines.append(compact(v, indent + 1))
            else:
                lines.append(f"{pad}{k}: {_scalar(v) if not isinstance(v, (dict, list)) else ('{}' if isinstance(v, dict) else '[]')}")
    elif isinstance(obj, list):
        for x in obj:
            if isinstance(x, dict):
                inner = compact(x, indent + 1).splitlines()
                if inner:
                    lines.append(pad + "- " + inner[0].lstrip())
                    lines.extend(inner[1:])
            else:
                lines.append(f"{pad}- {_scalar(x)}")
    else:
        lines.append(pad + _scalar(obj))
    return "\n".join(l for l in lines if l)
