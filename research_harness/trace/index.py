"""Disposable SQLite cache built from probe parts. Never authoritative: rebuild from parts at will."""
from __future__ import annotations

import gzip
import json
import os
import posixpath
import re
import sqlite3
from pathlib import Path

SCHEMA_VERSION = 4
SCHEMA = """
CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE files(fid INTEGER PRIMARY KEY, path TEXT UNIQUE, dir TEXT, size INTEGER, mtime INTEGER, ext TEXT, kind TEXT,
                   status TEXT, reason TEXT, role TEXT, sha TEXT, title TEXT, part TEXT);
CREATE TABLE facts_t(fid INTEGER PRIMARY KEY, json TEXT);
CREATE TABLE metrics_t(fid INTEGER, locator TEXT, key TEXT, value REAL);
CREATE TABLE config_t(fid INTEGER, locator TEXT, key TEXT, value TEXT, num REAL, authority TEXT);
CREATE TABLE tokens_t(token TEXT, fid INTEGER, source TEXT);
CREATE TABLE refs_t(src INTEGER, raw TEXT, target TEXT, mode TEXT);
CREATE TABLE lines_t(fid INTEGER, line INTEGER, kind TEXT, text TEXT);
CREATE TABLE skips(path TEXT, kind TEXT, reason TEXT);
CREATE TABLE texts_t(fid INTEGER PRIMARY KEY, text TEXT);
CREATE VIEW texts AS SELECT f.path AS path, t.text AS text FROM texts_t t JOIN files f ON f.fid = t.fid;
CREATE VIEW facts AS SELECT f.path AS path, t.json AS json FROM facts_t t JOIN files f ON f.fid = t.fid;
CREATE VIEW metrics AS SELECT f.path AS path, t.locator AS locator, t.key AS key, t.value AS value FROM metrics_t t JOIN files f ON f.fid = t.fid;
CREATE VIEW config AS SELECT f.path AS path, t.locator AS locator, t.key AS key, t.value AS value, t.num AS num, t.authority AS authority
    FROM config_t t JOIN files f ON f.fid = t.fid;
CREATE VIEW tokens AS SELECT t.token AS token, f.path AS path, t.source AS source FROM tokens_t t JOIN files f ON f.fid = t.fid;
CREATE VIEW refs AS SELECT f.path AS src, t.raw AS raw, t.target AS target, t.mode AS mode FROM refs_t t JOIN files f ON f.fid = t.src;
CREATE VIEW lines AS SELECT f.path AS path, t.line AS line, t.kind AS kind, t.text AS text FROM lines_t t JOIN files f ON f.fid = t.fid;
CREATE INDEX files_dir ON files(dir);
CREATE INDEX files_role ON files(role);
CREATE INDEX metrics_key ON metrics_t(key);
CREATE INDEX metrics_value ON metrics_t(value);
CREATE INDEX metrics_fid ON metrics_t(fid);
CREATE INDEX config_fid ON config_t(fid);
CREATE INDEX config_num ON config_t(num);
CREATE INDEX tokens_token ON tokens_t(token);
CREATE INDEX refs_target ON refs_t(target);
CREATE INDEX refs_src ON refs_t(src);
CREATE INDEX lines_fid ON lines_t(fid);
CREATE INDEX skips_path ON skips(path);
"""


METRIC_NAME = re.compile(r"(sr|success|acc|loss|reward|return|score|fid|psnr|ssim|err|mse|mae|rate|time|fps|mem|dist|emd|rank|auc|f1)", re.I)


def trace_dir(workspace: Path, name: str) -> Path:
    return Path(workspace) / ".research" / "trace" / name


def read_parts(parts: list[Path]):
    """Yield (part, record) in order; later parts override earlier ones per path. Torn lines are skipped."""
    for part in parts:
        opener = gzip.open if str(part).endswith(".gz") else open
        with opener(part, "rt", encoding="utf-8") as fh:
            try:
                for line in fh:
                    try:
                        yield part.name, json.loads(line)
                    except ValueError:
                        continue
            except EOFError:
                continue  # truncated (interrupted) part: keep what was flushed


def norm_key(locator: str) -> str:
    """`$.cfg.optim.lr` -> `optim.lr`; list indices dropped so rows share a key."""
    key = re.sub(r"\[\d+\]", "", locator)
    key = key[2:] if key.startswith("$.") else key.lstrip("$")
    return key


def tail_index(paths) -> dict[str, list[str]]:
    """`a/b/c/d.json` -> keys `c/d.json` and `b/c/d.json`, to follow projects that were moved/renamed."""
    out: dict[str, list[str]] = {}
    for p in paths:
        parts = p.split("/")
        for k in (2, 3):
            if len(parts) > k:
                out.setdefault("/".join(parts[-k:]), []).append(p)
    return out


def resolve_ref(raw: str, root: str, inventory: set[str], by_base: dict[str, list[str]], tails: dict | None = None) -> str | None:
    ref = raw.strip().strip("'\"")
    if not ref:
        return None
    if ref.startswith(root + "/"):
        ref = ref[len(root) + 1:]
    ref = posixpath.normpath(ref).lstrip("./") if not ref.startswith("/") else ref
    if ref in inventory:
        return ref
    # Absolute paths from other mounts / hosts: match the longest suffix that exists in the inventory.
    parts = ref.strip("/").split("/")
    for i in range(1, len(parts)):
        cand = "/".join(parts[i:])
        if cand in inventory:
            return cand
    if tails is not None:
        for k in (3, 2):  # migrated absolute paths: match the longest unique tail
            if len(parts) >= k:
                hits = tails.get("/".join(parts[-k:]))
                if hits and len(set(hits)) == 1:
                    return hits[0]
    base = parts[-1]
    hits = by_base.get(base)
    if hits and len(hits) == 1:
        return hits[0]
    return None


def _first_meta(part: Path) -> dict:
    opener = gzip.open if str(part).endswith(".gz") else open
    try:
        with opener(part, "rt", encoding="utf-8") as fh:
            rec = json.loads(fh.readline())
            return rec if rec.get("t") == "meta" else {}
    except (OSError, EOFError, ValueError):
        return {}


def build(workspace: Path, name: str, parts: list[Path], root: str | None = None) -> dict:
    # A full scan (no resume input) supersedes everything before it; incremental parts layer on top.
    for i in range(len(parts) - 1, -1, -1):
        if _first_meta(parts[i]).get("resume_parts", 0) == 0:
            parts = parts[i:]
            break
    out = trace_dir(workspace, name)
    out.mkdir(parents=True, exist_ok=True)
    db_path = out / "index.sqlite"
    tmp = out / "index.sqlite.tmp"
    if tmp.exists():
        tmp.unlink()
    records: dict[str, dict] = {}
    skips, metas, ends = [], [], []
    for part, rec in read_parts(parts):
        t = rec.get("t")
        if t == "file":
            rec["part"] = part
            records[rec["p"]] = rec
        elif t == "same":
            records.setdefault(rec["p"], {"t": "file", "p": rec["p"], "st": "unchanged_missing_base"})
        elif t == "skip":
            skips.append(rec)
        elif t == "bulk":  # summarized bulk binary directory (dataset images etc.)
            skips.append({"p": rec["p"], "kind": "bulk", "r": json.dumps({"files": rec["n"], "exts": rec.get("exts")})})
        elif t == "meta":
            metas.append(rec)
        elif t == "end":
            ends.append(rec)
    root = root or (metas[-1]["root"] if metas else "")
    con = sqlite3.connect(tmp)
    con.executescript(SCHEMA)
    inventory = set(records)
    by_base: dict[str, list[str]] = {}
    for p in inventory:
        by_base.setdefault(posixpath.basename(p), []).append(p)
    dirs = set()
    for p in inventory:
        d = posixpath.dirname(p)
        while d and d not in dirs:
            dirs.add(d)
            d = posixpath.dirname(d)
    known = inventory | dirs  # computed once; per-ref unions made large projects quadratic
    tails = tail_index(known)
    rows_files, rows_facts, rows_metrics, rows_config, rows_tokens, rows_refs, rows_lines = [], [], [], [], [], [], []
    rows_texts = []
    for fid, (p, r) in enumerate(sorted(records.items()), 1):
        f = r.get("f") or {}
        table = f.get("table") or {}
        if table.get("rows") and not any(METRIC_NAME.search(c) for c in table.get("metric_cols", [])) \
                and not table.get("factor_cols") and not table.get("seed_cols"):
            # Coordinates/embeddings/raw arrays: keep the schema, not the bytes.
            table["rows"] = table["rows"][:5]
            table["rows_complete"] = False
            table["rows_truncated_reason"] = "unnamed numeric table"
        tok_seen = set()

        def tok(t, src):
            if (t, src) not in tok_seen:
                tok_seen.add((t, src))
                rows_tokens.append((t, fid, src))
        rows_files.append((fid, p, posixpath.dirname(p), r.get("s"), r.get("m"), r.get("ext"), r.get("k"), r.get("st"), r.get("r"),
                           r.get("role"), r.get("h"), f.get("title"), r.get("part")))
        for comp in p.split("/"):
            tok(comp.lower(), "path")
        if not f:
            continue
        t = f.get("table")
        if t and any(c.startswith("\ufeff") for c in t.get("columns", [])):  # parts from probe < v3
            fix = lambda c: c.lstrip("\ufeff")
            for k in ("columns", "metric_cols", "factor_cols", "seed_cols"):
                t[k] = [fix(c) for c in t.get(k, [])]
            t["col_kinds"] = {fix(c): v for c, v in t.get("col_kinds", {}).items()}
            t["rows"] = [{fix(c): v for c, v in r.items()} for r in t.get("rows", [])]
        if isinstance(f.get("text"), str):
            rows_texts.append((fid, f.pop("text")))
        rows_facts.append((fid, json.dumps(f, ensure_ascii=False)))
        for loc, key, val in f.get("metrics", []):
            rows_metrics.append((fid, loc, norm_key(loc), float(val)))
        prefix = f.get("table_locator", "$")
        for i, row in enumerate(table.get("rows") or []):
            for col in table.get("metric_cols", []):
                v = row.get(col)
                try:
                    v = float(str(v).rstrip("%")) if v is not None else None
                except ValueError:
                    v = None
                if v is not None and v == v and abs(v) != float("inf"):
                    loc = (f"{prefix}[{i}].{col}" if table.get("source") != "csv" else f"row:{i + 2},col:{col}")
                    rows_metrics.append((fid, loc, "table:" + col, v))
        for loc, val in (f.get("config") or {}).items():
            num = float(val) if isinstance(val, (int, float)) and not isinstance(val, bool) else None
            rows_config.append((fid, loc, norm_key(loc), json.dumps(val, ensure_ascii=False), num, "file"))
        for key, val in (f.get("path_config") or {}).items():
            try:
                num = float(val)
            except ValueError:
                num = None
            rows_config.append((fid, "path-token", key, json.dumps(val), num, "path-token"))
        for tok_ in f.get("ids", []):
            tok(tok_.lower(), "content")
        for mode in ("writes", "reads"):
            for raw in f.get(mode, []):
                tgt = resolve_ref(raw, root, known, by_base, tails)
                rows_refs.append((fid, raw, tgt, mode[:-1]))
        for raw in f.get("refs", []):
            tgt = resolve_ref(raw, root, known, by_base, tails)
            rows_refs.append((fid, raw, tgt, "mention"))
            tok(posixpath.basename(raw.rstrip("/")).lower(), "ref")
        for kind in ("numbers", "outline", "cmds"):
            for line, text in f.get(kind, []):
                rows_lines.append((fid, line, kind, text))
    con.executemany("INSERT INTO files VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", rows_files)
    con.executemany("INSERT INTO facts_t VALUES (?,?)", rows_facts)
    con.executemany("INSERT INTO metrics_t VALUES (?,?,?,?)", rows_metrics)
    con.executemany("INSERT INTO config_t VALUES (?,?,?,?,?,?)", rows_config)
    con.executemany("INSERT INTO tokens_t VALUES (?,?,?)", rows_tokens)
    con.executemany("INSERT INTO refs_t VALUES (?,?,?,?)", rows_refs)
    con.executemany("INSERT INTO lines_t VALUES (?,?,?,?)", rows_lines)
    con.executemany("INSERT INTO texts_t VALUES (?,?)", rows_texts)
    last = {(s.get("p"), s.get("kind")): s for s in skips}  # later parts win (a rescan may add a symlink target)
    con.executemany("INSERT INTO skips VALUES (?,?,?)", [(s.get("p"), s.get("kind"), str(s.get("r"))) for s in last.values()])
    complete = bool(ends) and all(e["stats"].get("complete") for e in ends) and not any(r.get("st") == "unchanged_missing_base" for r in records.values())
    meta = {"schema_version": SCHEMA_VERSION, "name": name, "root": root, "host": metas[-1].get("host") if metas else None,
            "parts": [p.name for p in parts], "probe_versions": sorted({m.get("probe_version") for m in metas}),
            "complete": complete, "end_stats": [e["stats"] for e in ends]}
    con.executemany("INSERT INTO meta VALUES (?,?)", [(k, json.dumps(v, ensure_ascii=False)) for k, v in meta.items()])
    con.commit()
    con.close()
    os.replace(tmp, db_path)
    return {"index": str(db_path), "files": len(records), "facts": len(rows_facts), "metrics": len(rows_metrics),
            "config": len(rows_config), "refs": len(rows_refs), "resolved_refs": sum(1 for r in rows_refs if r[2]), "complete": complete}


def connect(workspace: Path, name: str) -> sqlite3.Connection:
    db = trace_dir(workspace, name) / "index.sqlite"
    if not db.exists():
        raise FileNotFoundError(f"No trace index for {name!r}; run `labweft trace collect` or `trace ingest` first")
    _upgrade(db)
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:  # big sorts spill to disk: keep them next to the index, not on a (possibly full) system drive
        con.execute(f"PRAGMA temp_store_directory = '{str(db.parent).replace(chr(39), chr(39) * 2)}'")
    except sqlite3.Error:
        pass
    return con


def _upgrade(db: Path) -> None:
    """Indexes added after an index file was built (existence checks on `skips` scanned every row per lookup)."""
    try:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        have = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type = 'index'")}
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        con.close()
        if "skips" in tables and "skips_path" not in have:
            con = sqlite3.connect(db)
            con.execute("CREATE INDEX IF NOT EXISTS skips_path ON skips(path)")
            con.commit()
            con.close()
    except sqlite3.Error:
        pass  # a read-only or busy index still works, only slower


def fid_range(con: sqlite3.Connection, prefix: str) -> tuple[int, int] | None:
    """File ids are assigned in sorted-path order, so everything under `prefix/` is one contiguous id range.
    Child tables (metrics_t, config_t, refs_t, lines_t, texts_t) are indexed by fid: query them by range, never by
    a LIKE on the joined path (a full scan of millions of rows)."""
    p = prefix.strip("/") + "/"
    row = con.execute("SELECT MIN(fid), MAX(fid) FROM files WHERE path >= ? AND path < ?", (p, p[:-1] + "0")).fetchone()
    return (row[0], row[1]) if row and row[0] is not None else None


def meta(con: sqlite3.Connection) -> dict:
    return {r["key"]: json.loads(r["value"]) for r in con.execute("SELECT key, value FROM meta")}
