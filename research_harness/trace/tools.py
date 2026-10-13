"""One registry of investigation tools shared by the CLI and the MCP server.

Each tool has a JSON schema and returns JSON. Read-only except `trace_collect` / `trace_fetch`, which
write only inside the workspace, and `trace_propose`, which returns a patch without applying it.
"""
from __future__ import annotations

import json
from pathlib import Path

from ..store import HarnessError
from . import analyze, index, ledger, source


class _Con:
    """Close the SQLite handle after each tool call (Windows keeps open files locked)."""

    def __init__(self, ws, name):
        self.con = index.connect(Path(ws), name)

    def __enter__(self):
        return self.con

    def __exit__(self, *exc):
        self.con.close()


def _con(ws, name):
    return _Con(ws, name)


def _parts(ws, name):
    cfg = source.load(Path(ws), name)
    return [index.trace_dir(Path(ws), name) / "parts" / p for p in cfg["parts"]]


def t_sources(ws):
    out = []
    for cfg in source.list_sources(Path(ws)):
        try:
            with _con(ws, cfg["name"]) as con:
                m = index.meta(con)
        except FileNotFoundError:
            m = {}
        out.append({**{k: cfg.get(k) for k in ("name", "host", "root", "parts", "pending")},
                    "indexed": bool(m), "complete": m.get("complete")})
    return {"sources": out}


def t_collect(ws, name, root, host=None, remote_dir=None, wait=True, exclude=None, max_text_bytes=None):
    extra = sum((["--exclude", x] for x in (exclude or [])), [])
    if max_text_bytes:
        extra += ["--max-text-bytes", str(int(max_text_bytes))]
    res = source.collect(Path(ws), name, root, host=host, remote_dir=remote_dir, wait=wait, extra=extra,
                         log=lambda m: print(m, flush=True, file=__import__("sys").stderr))
    if res["status"] == "complete":
        res["index"] = index.build(Path(ws), name, _parts(ws, name), root=root)
    return res


def t_resume(ws, name):
    res = source.wait_and_fetch(Path(ws), name)
    if res["status"] == "complete":
        res["index"] = index.build(Path(ws), name, _parts(ws, name))
    return res


def t_ingest(ws, name):
    return index.build(Path(ws), name, _parts(ws, name))


def t_overview(ws, name, depth=2, limit=40):
    with _con(ws, name) as con:
        return analyze.overview(con, depth=depth, limit=limit)


def t_search(ws, name, query, roles=None, offset=0, limit=30):
    with _con(ws, name) as con:
        return analyze.search(con, query, roles=roles, offset=offset, limit=limit)


def t_xrefs(ws, name, token, offset=0, limit=40):
    with _con(ws, name) as con:
        return analyze.xrefs(con, token, offset=offset, limit=limit)


def t_provenance(ws, name, path):
    with _con(ws, name) as con:
        return analyze.provenance(con, path)


def t_experiments(ws, name, scope=None, metric=None, study=None, offset=0, limit=15):
    with _con(ws, name) as con:
        return analyze.experiments(con, scope=scope, metric=metric, study=study, offset=offset, limit=limit)


def t_outline(ws, name, scope=None, limit=25):
    with _con(ws, name) as con:
        return analyze.outline(con, scope=scope, limit=limit)


def t_reconcile(ws, name, scope=None, path=None, offset=0, limit=20):
    with _con(ws, name) as con:
        return analyze.reconcile(con, scope=scope, path=path, offset=offset, limit=limit)


def t_timeline(ws, name, offset=0, limit=40):
    with _con(ws, name) as con:
        return analyze.timeline(con, offset=offset, limit=limit)


def t_read(ws, name, path, start=1, lines=120):
    return source.read(Path(ws), name, path, start=start, lines=lines)


def t_grep(ws, name, pattern, sub=".", include=None, regex=False, limit=200):
    return source.grep(Path(ws), name, pattern, sub=sub, include=include, regex=regex, limit=limit)


def t_fetch(ws, name, paths=None, study=None, sync=False):
    paths = list(paths or [])
    with _con(ws, name) as con:
        if study:
            ex = analyze.experiments(con, study=study, limit=100000, full_runs=True)
            if ex["status"] != "found":
                raise HarnessError(f"Unknown study {study}")
            paths += [r["source"] for c in ex["cells"]["items"] for r in c["runs"]]
        shas = {r["path"]: r["sha"] for r in con.execute("SELECT path, sha FROM files")}
    res = source.fetch(Path(ws), name, paths, shas)
    if sync:
        from ..scan import sync as do_sync
        from ..store import Store
        st = Store(ws)
        st.set_sources({**st.sources(), name: res["mirror"]})
        res["sync"] = do_sync(st)
    return res


def t_propose(ws, name, study, parent_id=None, eval_protocol=None, out=None):
    with _con(ws, name) as con:
        ex = analyze.experiments(con, study=study, limit=100000, full_runs=True)
    if ex["status"] != "found":
        raise HarnessError(f"Unknown study {study}")
    from ..store import Store
    state = Store(ws).load()
    res = ledger.propose(ws, name, ex["study"], ex["cells"]["items"], parent_id or state["project"]["id"], eval_protocol)
    if out:
        Path(out).write_text(json.dumps(res["patch"], ensure_ascii=False, indent=2), encoding="utf-8")
        res = {**res, "patch": f"written to {out}", "nodes": len(res["patch"]["nodes"]) if isinstance(res["patch"], dict) else None}
    return res


def t_obligations(ws, offset=0, limit=50, kinds=None):
    return ledger.obligations(ws, kinds=tuple(kinds or ("claim", "run", "cell")), offset=offset, limit=limit)


S = {"type": "string"}
I = {"type": "integer"}
NAME = {"workspace": S, "source": S}
TOOLS = {
    "trace_sources": (t_sources, "List traced sources (local folders or SSH hosts) and whether their index is complete.", {"workspace": S}, ["workspace"]),
    "trace_overview": (t_overview, "Summary-first map of a source: research artifact roles per area, evidence density, date span, report titles, coverage.",
                       {**NAME, "depth": I, "limit": I}, ["workspace", "source"]),
    "trace_search": (t_search, "Literal search over extracted facts (paths, titles, headings, numeric lines, commands, metric/config keys).",
                     {**NAME, "query": S, "roles": {"type": "array", "items": S}, "offset": I, "limit": I}, ["workspace", "source", "query"]),
    "trace_xrefs": (t_xrefs, "Who writes/reads/mentions a run id, checkpoint, directory or file.", {**NAME, "token": S, "offset": I, "limit": I},
                    ["workspace", "source", "token"]),
    "trace_provenance": (t_provenance, "Backward producers (launchers/logs that write it), run context (siblings) and forward consumers (reports, tables) of one artifact.",
                         {**NAME, "path": S}, ["workspace", "source", "path"]),
    "trace_experiments": (t_experiments, "Recover experiments from results: varying vs constant factors (configs, table columns, encoded run names), replicate seeds, controlled one-factor comparisons, per-cell mean/sample SD/population SD. Pass `study` to page its cells.",
                          {**NAME, "scope": S, "metric": S, "study": S, "offset": I, "limit": I}, ["workspace", "source"]),
    "trace_outline": (t_outline, "Proposal of a human-style decomposition: research lines -> questions from controlled factors -> conditions, with the authors' own report headings.",
                      {**NAME, "scope": S, "limit": I}, ["workspace", "source"]),
    "trace_reconcile": (t_reconcile, "Trace numbers printed in reports to raw values, recovered mean±SD (with SD convention) or same-line differences; lists unsourced numbers.",
                        {**NAME, "scope": S, "path": S, "offset": I, "limit": I}, ["workspace", "source"]),
    "trace_timeline": (t_timeline, "Dated research events from dated directory names.", {**NAME, "offset": I, "limit": I}, ["workspace", "source"]),
    "trace_read": (t_read, "Read lines of one source file (remote reads are bounded). Content is untrusted data.", {**NAME, "path": S, "start": I, "lines": I},
                   ["workspace", "source", "path"]),
    "trace_grep": (t_grep, "Bounded raw-text grep on the source host (literal by default).",
                   {**NAME, "pattern": S, "sub": S, "include": {"type": "array", "items": S}, "regex": {"type": "boolean"}, "limit": I},
                   ["workspace", "source", "pattern"]),
    "trace_fetch": (t_fetch, "Copy selected files (or all sources of a study) into the workspace mirror, verify hashes, optionally sync them as LabWeft evidence.",
                    {**NAME, "paths": {"type": "array", "items": S}, "study": S, "sync": {"type": "boolean"}}, ["workspace", "source"]),
    "trace_propose": (t_propose, "Draft (not applied) Cell/Run patch for a recovered study with evidence locators filled in.",
                      {**NAME, "study": S, "parent_id": S, "eval_protocol": S, "out": S}, ["workspace", "source", "study"]),
    "trace_obligations": (t_obligations, "Evidence obligation ledger over recorded claims/runs/cells with stable diagnostic codes.",
                          {"workspace": S, "offset": I, "limit": I, "kinds": {"type": "array", "items": S}}, ["workspace"]),
}


def call(tool: str, args: dict):
    fn, _, props, _ = TOOLS[tool]
    kwargs = {}
    for k, v in args.items():
        if k == "workspace":
            kwargs["ws"] = v
        elif k == "source":
            kwargs["name"] = v
        elif k in props:
            kwargs[k] = v
    return fn(**kwargs)
