"""Read-only analyses over a trace index, shaped like REA tools.

Every result carries `status` (found | not_found | unknown), `coverage` and `limitations`.
`not_found` is only returned when the underlying collection was exhaustive; otherwise absence is
`unknown`. Facts keep their authority (file | sibling | path-token | inferred) so the agent can tell
what was observed from what was guessed. Nothing here writes to the research store.
"""
from __future__ import annotations

import hashlib
import json
import os
import math
import posixpath
import re
import statistics
from collections import Counter, defaultdict

from .index import meta

PRIMARY_METRIC = re.compile(r"(success_rate|successes|success($|[_.%])|macro_sr|sr_percent|(^|[_.])sr($|[_.%])|accuracy|(^|[_.])acc($|[_.])|top1|(^|[_.])reward($|[_.])|(^|[_.])return($|[_.])|(^|[_.])score($|[_.])|fid|psnr|win_rate)", re.I)
DIAGNOSTIC_METRIC = re.compile(r"(pearson|spearman|corr|cosine|kendall|r2|slope|delta_|_delta|grad|norm|entropy|loss)", re.I)
SEED_KEY = re.compile(r"(^|[_.])(seed|train_seed|eval_seed|run_seed|manifest_seed|rep|replicate)s?$", re.I)
OUTCOME_KEY = re.compile(r"(^|[._])(metrics|topology|timing|solver_timing|stats|statistics|diagnostics|summary|results?|outputs?|episodes|eval|evaluation|counts?)[._]|(_sum|_mean|_avg|_count|_total|_ms|_s|_max|_min|_std|_rate|_fraction|_frac|_pct|_percent)$", re.I)
NOISE_KEY = re.compile(r"(return_code|returncode|exit_code|time|seconds|sec|wall|elapsed|duration|timestamp|created|mtime|pid|port|gpu|rank|host|path|dir|file|hash|sha|sha256|sha1|md5|digest|uuid|commit|date|log|stdout|stderr|cmd|command|url)($|[_.])", re.I)
DIGITS = re.compile(r"\d+")


def _coverage(con) -> dict:
    m = meta(con)
    counts = {r[0] or "?": r[1] for r in con.execute("SELECT status, COUNT(*) FROM files GROUP BY status")}
    status = "complete" if m.get("complete") else "partial"
    limits = []
    if counts.get("metadata_only"):
        limits.append(f"{counts['metadata_only']} binary/media/checkpoint files inventoried by metadata only")
    for key in ("too_large", "timeout", "error", "skipped"):
        if counts.get(key):
            limits.append(f"{counts[key]} files {key}")
    try:
        bulk = [json.loads(r[0]) for r in con.execute("SELECT reason FROM skips WHERE kind = 'bulk'")]
    except Exception:
        bulk = []
    if bulk:
        limits.append(f"{sum(b['files'] for b in bulk)} files in {len(bulk)} bulk binary directories (datasets/media) summarized, not listed")
    if not m.get("complete"):
        limits.append("collection stopped early (deadline/max-files) or a resumed base part is missing")
    return {"status": status, "inventory": sum(counts.values()), "by_status": counts, "limitations": limits,
            "root": m.get("root"), "host": m.get("host")}


def result(status: str, con, **payload) -> dict:
    cov = _coverage(con)
    if status == "not_found" and cov["status"] != "complete":
        status = "unknown"
    return {"status": status, **payload, "coverage": cov}


def page(items: list, offset: int, limit: int) -> dict:
    nxt = offset + limit if offset + limit < len(items) else None
    return {"total": len(items), "offset": offset, "next_offset": nxt, "items": items[offset: offset + limit]}


# ---------------------------------------------------------------- overview

def overview(con, depth: int = 2, limit: int = 40) -> dict:
    """Summary-first: what kinds of research artifacts live where, not just folder names."""
    groups: dict[str, Counter] = defaultdict(Counter)
    sizes: Counter = Counter()
    dates: dict[str, set] = defaultdict(set)
    titles: dict[str, list] = defaultdict(list)
    for r in con.execute("SELECT path, size, role, kind, status, title FROM files"):
        parts = r["path"].split("/")
        key = "/".join(parts[:depth]) if len(parts) > depth else ("/".join(parts[:-1]) or ".")
        groups[key][r["role"] or r["kind"] or "?"] += 1
        sizes[key] += r["size"] or 0
        if r["role"] == "report" and r["title"] and len(titles[key]) < 3:
            titles[key].append({"path": r["path"], "title": r["title"]})
    for r in con.execute("SELECT path, json FROM facts"):
        parts = r["path"].split("/")
        key = "/".join(parts[:depth]) if len(parts) > depth else ("/".join(parts[:-1]) or ".")
        for d in json.loads(r["json"]).get("dates", [])[:5]:
            dates[key].add(d)
    rows = []
    for key, c in groups.items():
        ds = sorted(dates[key])
        research = {k: v for k, v in c.items() if k in ("result", "result_table", "config", "train_script", "eval_script", "launcher", "log", "report")}
        rows.append({"area": key, "files": sum(c.values()), "bytes": sizes[key], "roles": dict(c.most_common(8)),
                     "evidence_density": round(sum(research.values()) / max(1, sum(c.values())), 3),
                     "date_span": [ds[0], ds[-1]] if ds else None, "reports": titles[key]})
    rows.sort(key=lambda x: (-x["evidence_density"] * math.log1p(x["files"]), x["area"]))
    roles = dict(con.execute("SELECT role, COUNT(*) FROM files WHERE role IS NOT NULL GROUP BY role").fetchall())
    return result("found", con, roles=roles, areas=page(rows, 0, limit))


# ---------------------------------------------------------------- search / xrefs

def search(con, query: str, roles: list[str] | None = None, offset: int = 0, limit: int = 30) -> dict:
    """Case-insensitive search; every whitespace-separated term must match (AND).

    Covers paths, titles, extracted numeric/heading/command lines, metric and config keys, and the full
    text of prose files (reports, READMEs, notes, launchers) kept by the probe.
    """
    terms = [t.lower() for t in query.split() if t.strip()] or [query.lower()]
    hits: dict[str, dict] = {}

    def add(path, where, text=None, line=None):
        h = hits.setdefault(path, {"path": path, "matches": []})
        if len(h["matches"]) < 5:
            h["matches"].append({k: v for k, v in (("in", where), ("line", line), ("text", text)) if v is not None})

    def where(cols):
        clause = " AND ".join("(" + " OR ".join(f"lower({c}) LIKE ?" for c in cols) + ")" for _ in terms)
        args = [f"%{t}%" for t in terms for _ in cols]
        return clause, args
    w, a = where(["path", "coalesce(title, '')"])
    for r in con.execute(f"SELECT path, title FROM files WHERE {w} LIMIT 3000", a):
        add(r["path"], "path/title", r["title"])
    w, a = where(["text"])
    for r in con.execute(f"SELECT path, line, kind, text FROM lines WHERE {w} LIMIT 5000", a):
        add(r["path"], r["kind"], r["text"], r["line"])
    w, a = where(["key"])
    for r in con.execute(f"SELECT DISTINCT path, key FROM metrics WHERE {w} LIMIT 3000", a):
        add(r["path"], "metric_key", r["key"])
    w, a = where(["key", "value"])
    for r in con.execute(f"SELECT DISTINCT path, key, value FROM config WHERE {w} LIMIT 3000", a):
        add(r["path"], "config", f"{r['key']}={r['value']}")
    try:
        w, a = where(["text"])
        for r in con.execute(f"SELECT path, text FROM texts WHERE {w} LIMIT 2000", a):
            lines = r["text"].splitlines()
            scored = []
            for i, line in enumerate(lines, 1):
                low = line.lower()
                n = sum(t in low for t in terms)
                if n:
                    scored.append((-n, i, line))
            for n, i, line in sorted(scored)[:3]:
                add(r["path"], "text" if -n == len(terms) else "text(partial line)", line.strip()[:300], i)
    except Exception:  # older index without prose text
        pass
    role_of = dict(con.execute("SELECT path, role FROM files").fetchall())
    items = [dict(h, role=role_of.get(h["path"])) for h in hits.values() if not roles or role_of.get(h["path"]) in roles]
    rank = {"report": 0, "page": 1, "result_table": 2, "result": 3, "config": 4}
    items.sort(key=lambda x: (rank.get(x["role"], 9), -len(x["matches"]), "::" in x["path"], x["path"]))
    # Identical bytes in several places (a report and its copy inside a bundle) are one hit with extra locations.
    sha_of = {r["path"]: r["sha"] for r in con.execute(
        f"SELECT path, sha FROM files WHERE path IN ({','.join('?' * len(items))})", [i["path"] for i in items])} if items else {}
    first: dict[str, dict] = {}
    merged = []
    for it in items:
        sha = sha_of.get(it["path"])
        if sha and sha in first:
            first[sha].setdefault("same_content_at", []).append(it["path"])
            continue
        if sha:
            first[sha] = it
        merged.append(it)
    items = merged
    return result("found" if items else "not_found", con, query=query, results=page(items, offset, limit),
                  limitations=["all terms must match within one file; binary and very large files are not searched; use `grep` for raw text on the source host"])


def xrefs(con, token: str, offset: int = 0, limit: int = 40) -> dict:
    """Who mentions a run id, checkpoint, directory or file — typed as writes / reads / mention / path."""
    t = token.lower().strip("/")
    base = posixpath.basename(t)
    rows = []
    seen = set()
    for r in con.execute("SELECT src, raw, target, mode FROM refs WHERE lower(raw) LIKE ? OR lower(target) LIKE ? LIMIT 20000", (f"%{t}%", f"%{t}%")):
        key = (r["src"], r["mode"], r["target"] or r["raw"])
        if key not in seen:
            seen.add(key)
            rows.append({"from": r["src"], "mode": r["mode"], "ref": r["raw"], "resolved": r["target"]})
    for r in con.execute("SELECT path, source FROM tokens WHERE token = ? OR token = ? LIMIT 20000", (t, base)):
        key = (r["path"], r["source"], t)
        if key not in seen and r["source"] != "ref":
            seen.add(key)
            rows.append({"from": r["path"], "mode": "path" if r["source"] == "path" else "content-token", "ref": token, "resolved": None})
    role_of = dict(con.execute("SELECT path, role FROM files").fetchall())
    for x in rows:
        x["role"] = role_of.get(x["from"])
    order = {"write": 0, "read": 1, "mention": 2, "content-token": 3, "path": 4}
    rows.sort(key=lambda x: (order.get(x["mode"], 9), x["from"]))
    by_mode = Counter(x["mode"] for x in rows)
    by_role = Counter(x["role"] for x in rows)
    return result("found" if rows else "not_found", con, token=token, by_mode=dict(by_mode), by_role=dict(by_role.most_common(12)),
                  refs=page(rows, offset, limit))


# ---------------------------------------------------------------- provenance

def provenance(con, path: str) -> dict:
    """Backward (who produced it) and forward (who consumes/cites it) around one artifact."""
    row = con.execute("SELECT * FROM files WHERE path = ?", (path,)).fetchone()
    if row is None:
        cands = [r[0] for r in con.execute("SELECT path FROM files WHERE path LIKE ? LIMIT 10", (f"%{path}%",))]
        return result("unknown", con, path=path, candidates=cands, limitations=["path not in inventory; pick a candidate"])
    d = row["dir"]
    ancestors = []
    while d:
        ancestors.append(d)
        d = posixpath.dirname(d)
    targets = [path] + ancestors
    q = ",".join("?" * len(targets))
    producers, consumers = [], []
    for r in con.execute(f"SELECT src, raw, target, mode FROM refs WHERE target IN ({q})", targets):
        item = {"file": r["src"], "via": r["mode"], "ref": r["raw"], "target": r["target"], "exact": r["target"] == path}
        (producers if r["mode"] == "write" else consumers).append(item)
    siblings = [dict(path=r["path"], role=r["role"], title=r["title"]) for r in
                con.execute("SELECT path, role, title FROM files WHERE dir = ? AND path != ? AND role IS NOT NULL ORDER BY role LIMIT 60", (row["dir"], path))]
    base = posixpath.basename(path)
    cmd_mentions = [dict(file=r["path"], line=r["line"], text=r["text"]) for r in
                    con.execute("SELECT path, line, text FROM lines WHERE kind = 'cmds' AND text LIKE ? LIMIT 20", (f"%{base}%",))] if len(base) > 6 else []
    consumers.sort(key=lambda x: (not x["exact"], x["file"]))
    producers.sort(key=lambda x: (not x["exact"], len(x["target"] or ""), x["file"]))
    status = "found" if producers or cmd_mentions else "unknown"
    lim = [] if producers else ["no launcher/log declares writing this path or its directories; producer is unknown, not absent"]
    return result(status, con, path=path, role=row["role"], sha256=row["sha"], producers=producers[:40], run_context=siblings,
                  consumers=consumers[:60], command_mentions=cmd_mentions, limitations=lim)


# ---------------------------------------------------------------- experiments (factor recovery)


CONTEXT_KEY = re.compile(r"(^|[_.\]])(task|tasks|env|environment|dataset|data|suite|benchmark|split|domain|scene|game|robot|embodiment)$", re.I)
KV_TOKEN = re.compile(r"^([A-Za-z]+?)(-?\d+(?:\.\d+)?(?:x\d+(?:\.\d+)?)*(?:e-?\d+)?|\d+p\d+)$")
SEED_COMPONENT = re.compile(r"^((?:eval|train|run)?_?seed)[_-]?(\d+)$", re.I)
TASK_WORDS = {"cube", "pusht", "reacher", "tworoom", "two_room", "wall", "maze", "hopper", "walker", "cheetah", "humanoid", "ant", "lift", "can", "square", "libero", "spatial", "goal", "object", "long", "carry", "lafan", "drawer", "stapler", "bell", "clickbell", "imagenet", "cifar", "galaxy10", "imagenette"}
SEED_HINT_KEYS = {"train", "eval", "e", "es", "ts", "run", "rep", "trial", "evalseed"}
NAME_SEED_KEYS = {"s", "seed", "sd", "es", "ts", "rs", "eval", "evalseed", "eseed", "tseed"}


def name_tokens(name: str) -> tuple[dict, list]:
    """`aw0.1_lw0.1_iso0.5x0.5_L5_rh1_s7` -> ({aw:0.1, lw:0.1, iso:0.5x0.5, L:5, rh:1, s:7}, tags)."""
    keyed, tags = {}, []
    for _ in range(2):  # `seed0.txt.json`
        name = re.sub(r"\.[A-Za-z][A-Za-z0-9]{0,4}$", "", name)
    m = SEED_COMPONENT.match(name)
    if m:
        return {m.group(1).lower().replace("__", "_"): m.group(2)}, []
    for tok in re.split(r"[_]+", name):
        if not tok:
            continue
        kv = KV_TOKEN.match(tok)
        if kv and not re.fullmatch(r"20\d{6}", tok):
            k, v = kv.group(1), kv.group(2).replace("p", ".") if re.fullmatch(r"\d+p\d+", kv.group(2)) else kv.group(2)
            if k in keyed and keyed[k] != v:
                k = k + "#2"
            keyed[k] = v
        elif "=" in tok:
            k, _, v = tok.partition("=")
            keyed[k] = v
        else:
            tags.append(tok.lower())
    return keyed, tags


def split_kv_list(value):
    """`num_candidates=64,noise_scale=0.5` -> {num_candidates: 64, noise_scale: 0.5} or None."""
    if not isinstance(value, str) or value.count("=") < 2:
        return None
    out = {}
    for part in re.split(r"[,;]\s*", value):
        if "=" not in part:
            return None
        k, _, v = part.partition("=")
        out[k.strip()] = v.strip()
    return out


def expand_names(units, keys_to_expand):
    """Replace opaque name-like factors by the hyperparameters encoded in them (authority: name-token)."""
    for key in keys_to_expand:
        parsed = []
        for u in units:
            raw = u["config"].get(key, (None, None))[0]
            if raw is None:
                parsed.append(({}, []))
                continue
            raw = str(raw)
            comps = [c for c in raw.split("/") if c]
            keyed, tags = {}, []
            # A path-valued setting is read by its file stem; a full run path by its last components.
            pick = comps[-1:] if "/" in raw and not key.startswith("path[") and not re.search(r"(source|run|name|dir|path)$", key) else comps[-4:]
            for comp in (pick if "/" in raw else [raw]):
                k, t = name_tokens(comp)
                for kk, vv in k.items():
                    keyed.setdefault(kk, vv)
                tags.extend(t)
            parsed.append((keyed, tags))
        all_tags = Counter(t for _, tags in parsed for t in set(tags))
        common = {t for t, n in all_tags.items() if n == len(units)}
        for u, (keyed, tags) in zip(units, parsed):
            auth = "name-token"
            u["config"].pop(key, None)
            for kk, vv in keyed.items():
                low = kk.lower()
                if low in ("s", "seed", "sd", "ts", "tseed"):
                    name = "seed"
                elif low in ("es", "eval", "evalseed", "eseed") or low.endswith("seed"):
                    name = "eval_seed" if low != "rs" else "seed"
                else:
                    name = f"{key}~{kk}"
                if low.endswith("seed") and low not in ("seed", "evalseed", "eseed", "tseed"):
                    name = low
                u["config"][name] = (vv, auth)
            var = sorted(t for t in dict.fromkeys(tags) if t not in common)
            tasks = [t for t in var if t in TASK_WORDS]
            if tasks:  # benchmark/task words are evaluation context, not a treatment level
                u["config"][f"{key}~task"] = ("+".join(tasks), "name-token")
                var = [t for t in var if t not in TASK_WORDS]
            if len(var) > 4:  # a prose-like file name is an identity, not a factor level
                u["config"][f"{key}~name"] = ("+".join(var), "identity")
                continue
            if var:
                u["config"][f"{key}~tags"] = ("+".join(var), auth)


def _template(path: str) -> str:
    return DIGITS.sub("#", posixpath.basename(path))


def _num(v):
    try:
        f = float(str(v).rstrip("%"))
        return f if math.isfinite(f) else None
    except (TypeError, ValueError):
        return None


def _units(con, scope: str | None):
    """Yield measurement units: one result file, or one row of a result table."""
    like = f"{scope.rstrip('/')}/%" if scope else "%"
    cfg_by_path: dict[str, dict] = defaultdict(dict)
    for r in con.execute("SELECT c.path, c.key, c.value, c.authority FROM config c JOIN files f ON f.path = c.path WHERE f.path LIKE ?", (like,)):
        cfg_by_path[r["path"]][r["key"]] = (json.loads(r["value"]), r["authority"])
    configs_in_dir: dict[str, list[str]] = defaultdict(list)
    for r in con.execute("SELECT path, dir FROM files WHERE role = 'config' AND path LIKE ?", (like,)):
        configs_in_dir[r["dir"]].append(r["path"])
    mets: dict[str, dict] = defaultdict(dict)
    for r in con.execute("SELECT m.path, m.locator, m.key, m.value FROM metrics m JOIN files f ON f.path = m.path WHERE f.role = 'result' AND f.path LIKE ?", (like,)):
        mets[r["path"]].setdefault(r["key"], (r["value"], r["locator"]))
    for path, metrics in mets.items():
        # Inside a result file, only settings count as factors; measured outputs (timings, counters,
        # episode diagnostics) vary per run because they are results, not because someone changed them.
        cfg = {k: v for k, v in cfg_by_path.get(path, {}).items() if v[1] != "file" or not OUTCOME_KEY.search(k)}
        d = posixpath.dirname(path)
        for cp in configs_in_dir.get(d, []):
            for k, (v, _) in cfg_by_path.get(cp, {}).items():
                cfg.setdefault(k, (v, "sibling"))
        yield {"source": path, "family": (posixpath.dirname(posixpath.dirname(path)), _template(path), tuple(sorted(metrics))[:40]),
               "metrics": metrics, "config": cfg, "path": path, "locator": None}
    for r in con.execute("SELECT f.path, x.json FROM files f JOIN facts x ON x.path = f.path WHERE f.role = 'result_table' AND f.path LIKE ?", (like,)):
        facts = json.loads(r["json"])
        t = facts.get("table") or {}
        rows = t.get("rows") or []
        prefix = facts.get("table_locator", "$")
        for i, row in enumerate(rows):
            metrics = {c: (_num(row.get(c)), (f"{prefix}[{i}].{c}" if t.get("source") != "csv" else f"row:{i + 2},col:{c}"))
                       for c in t.get("metric_cols", []) if _num(row.get(c)) is not None}
            if not metrics:
                continue
            cfg = {c: (row.get(c), "file") for c in t.get("factor_cols", []) + t.get("seed_cols", []) if row.get(c) not in (None, "")}
            yield {"source": r["path"], "family": (r["path"], "rows", tuple(sorted(t.get("metric_cols", [])))[:40]),
                   "metrics": metrics, "config": cfg, "path": r["path"], "locator": f"{prefix}[{i}]" if t.get("source") != "csv" else f"row:{i + 2}",
                   "rows_complete": t.get("rows_complete", True)}


def _path_factors(units):
    """Directory components that differ between units of one family become candidate factors (authority: path)."""
    split = [u["path"].split("/") for u in units]
    depth = min(len(s) for s in split)
    out = []
    if all(len(s) == len(split[0]) for s in split):
        for i in range(depth - 1):
            vals = {s[i] for s in split}
            if 1 < len(vals) <= max(2, len(units)):
                out.append(i)
    return out


def _stats(values):
    vals = [v for v in values if v is not None]
    if not vals:
        return None
    # plain float math: statistics.stdev uses exact Fractions and dominated reconcile's run time
    n = len(vals)
    mean = math.fsum(vals) / n
    s = {"n": n, "mean": round(mean, 6)}
    if n > 1:
        ss = math.fsum((v - mean) ** 2 for v in vals)
        s["sd_sample"] = round(math.sqrt(ss / (n - 1)), 6)
        s["sd_population"] = round(math.sqrt(ss / n), 6)
    return s


def is_primary(key: str) -> bool:
    return bool(PRIMARY_METRIC.search(key or "")) and not DIAGNOSTIC_METRIC.search(key or "")


def _primary(metric_keys, counts):
    ranked = sorted(metric_keys, key=lambda k: (not is_primary(k), bool(NOISE_KEY.search(k)), -counts[k], len(k), k))
    return ranked[0] if ranked else None


def experiments(con, scope: str | None = None, metric: str | None = None, min_units: int = 2, offset: int = 0, limit: int = 15,
                study: str | None = None, _keep_cells: bool = False, full_runs: bool = False) -> dict:
    families: dict[tuple, list] = defaultdict(list)
    for u in _units(con, scope):
        families[u["family"]].append(u)
    studies = []
    for fam, units in families.items():
        if len(units) < min_units:
            continue
        # merge path-derived factors (only for file units; rows share one file)
        if fam[1] != "rows":
            for i in _path_factors(units):
                for u in units:
                    u["config"][f"path[{i}]"] = (u["path"].split("/")[i], "path")
        # Decompose composite values the way a person reads them: k=v lists and encoded run names.
        for u in units:
            for k, (v, auth) in list(u["config"].items()):
                kv = split_kv_list(v)
                if kv:
                    u["config"].pop(k)
                    for kk, vv in kv.items():
                        u["config"][f"{k}.{kk}"] = (vv, auth)
        for _ in range(2):
            keys = set()
            for u in units:
                keys.update(u["config"])
            opaque = []
            for k in keys:
                vals = {str(u["config"].get(k, (None,))[0]) for u in units}
                # A categorical column with few levels (e.g. direct / actor_cem300x30 / guarded_a128x3) is one
                # factor as the author named it; only id-like columns and run-name paths are decomposed.
                many = len(vals) > 12 or len(vals) >= max(4, len(units) // 2)
                if len(vals) > 1 and not SEED_KEY.search(k.split(".")[-1]) and "~" not in k and (
                        k.startswith("path[") or (many and any(("_" in v or "/" in v) and re.search(r"\d", v) for v in vals))):
                    opaque.append(k)
            if not opaque:
                break
            expand_names(units, opaque)
        keys = set()
        for u in units:
            keys.update(u["config"])
        varying, constant = {}, {}
        for k in keys:
            vals = [json.dumps(u["config"].get(k, (None,))[0], sort_keys=True, ensure_ascii=False, default=str) for u in units]
            distinct = set(vals)
            if len(distinct) > 1:
                varying[k] = distinct
            elif vals and vals[0] != "null":
                constant[k] = json.loads(vals[0])
        def seedlike(k):
            leaf = k.split(".")[-1].split("~")[-1].lower()
            if SEED_KEY.search(leaf) or leaf in ("seed", "s"):
                return True
            if leaf not in SEED_HINT_KEYS:
                return False
            vals = set()
            for v in varying[k]:
                try:
                    vals.add(int(json.loads(v)))
                except (TypeError, ValueError):
                    return False
            return vals <= {0, 1, 2, 3, 4, 42, 123, 1234} or (min(vals) >= 1000 and max(vals) - min(vals) < 100) or (
                vals - {0, 1, 2, 3, 4, 42} and all(v in (0, 42) or 3000 <= v < 3100 for v in vals))
        seed_keys = sorted(k for k in varying if seedlike(k))
        id_like = sorted(k for k in varying if k not in seed_keys and (len(varying[k]) == len(units) and len(units) > 6
                         or NOISE_KEY.search(k.split(".")[-1].split("~")[-1]) or k.endswith("~name")))
        factors = sorted(k for k in varying if k not in seed_keys and k not in id_like)
        # Aliased factors (identical partition of units, e.g. `rh` in the path and `rh` in the run name) are one factor.
        aliases = {}
        part_of = {}
        for k in sorted(factors, key=lambda k: ({"file": 0, "sibling": 1, "name-token": 2, "path-token": 3, "path": 4}.get(
                Counter(u["config"].get(k, (None, "absent"))[1] for u in units).most_common(1)[0][0], 5), len(k), k)):
            sig = tuple(json.dumps(u["config"].get(k, (None,))[0], sort_keys=True, default=str) for u in units)
            canon = {}
            norm = tuple(canon.setdefault(v, len(canon)) for v in sig)
            if norm in part_of:
                aliases.setdefault(part_of[norm], []).append(k)
            else:
                part_of[norm] = k
        factors = sorted(part_of.values())
        # Display names: `path[3]~lw` -> `lw` when unambiguous; the authority field keeps where it came from.
        short = {}
        for k in factors:
            cand = k.split("~", 1)[1] if "~" in k else k
            short[k] = cand if sum(1 for j in factors if (j.split("~", 1)[1] if "~" in j else j) == cand) == 1 else k
        for u in units:
            for k in factors:
                if short[k] != k and k in u["config"]:
                    u["config"][short[k]] = u["config"].pop(k)
        aliases = {short[k]: sorted({a.split("~", 1)[1] if "~" in a else a for a in v}) for k, v in aliases.items()}
        varying = {short.get(k, k): v for k, v in varying.items()}
        factors = sorted(short[k] for k in factors)
        mcount = Counter(k for u in units for k in u["metrics"])
        pm = metric if metric and metric in mcount else _primary(list(mcount), mcount)
        cells: dict[str, dict] = {}
        for u in units:
            levels = {k: u["config"].get(k, (None, None))[0] for k in factors}  # aliases share levels
            cid = json.dumps(levels, sort_keys=True, ensure_ascii=False, default=str)
            c = cells.setdefault(cid, {"levels": levels, "runs": []})
            v = u["metrics"].get(pm, (None, None))
            c["runs"].append({"source": u["source"], "locator": v[1] or u["locator"], "seed": {k: u["config"].get(k, (None,))[0] for k in seed_keys},
                              "value": v[0]})
        cell_list = []
        for cid, c in cells.items():
            c["stats"] = _stats([r["value"] for r in c["runs"]])
            c["id"] = "cell-" + hashlib.sha256(cid.encode()).hexdigest()[:10]
            cell_list.append(c)
        # controlled comparisons: cells differing in exactly one factor
        axes: Counter = Counter()
        pairs = defaultdict(list)
        for i in range(len(cell_list)):
            for j in range(i + 1, len(cell_list)):
                diff = [k for k in factors if cell_list[i]["levels"].get(k) != cell_list[j]["levels"].get(k)]
                if len(diff) == 1:
                    axes[diff[0]] += 1
                    if len(pairs[diff[0]]) < 6:
                        pairs[diff[0]].append([cell_list[i]["id"], cell_list[j]["id"]])
        context = [k for k in factors if CONTEXT_KEY.search(k.split("~")[-1]) or k.endswith("~tags") and all(
            str(l).strip('"') in TASK_WORDS for l in varying[k] for l in [json.loads(l)] if l)]
        authority = {k: Counter(u["config"].get(k, (None, "absent"))[1] for u in units).most_common(1)[0][0] for k in factors}
        sid = "study-" + hashlib.sha256(json.dumps([fam[0], fam[1], list(fam[2])], default=str).encode()).hexdigest()[:10]
        rep = Counter(len(c["runs"]) for c in cell_list)
        studies.append({
            "id": sid, "source": fam[0] if fam[1] == "rows" else posixpath.join(fam[0], "**", fam[1]),
            "unit": "table_row" if fam[1] == "rows" else "result_file", "units": len(units), "primary_metric": pm,
            "metrics": [k for k, _ in mcount.most_common(12)],
            "factors": [{"key": k, "levels": len(varying[k]), "authority": authority[k], "role": "context" if k in context else "treatment",
                         "aliases": aliases.get(k, []), "example_levels": sorted(varying[k])[:6]} for k in factors],
            "replicate_keys": seed_keys, "identity_keys": id_like[:10],
            "controlled_axes": [{"factor": k, "pairs": n, "role": "context" if k in context else "treatment", "example_pairs": pairs[k]}
                                for k, n in axes.most_common()],
            "_signature": hashlib.sha256(json.dumps(sorted(round(r["value"], 6) for c in cell_list for r in c["runs"] if r["value"] is not None)).encode()).hexdigest(),
            "cells": len(cell_list), "replicates_per_cell": dict(rep),
            "constant_config": dict(list(sorted(constant.items()))[:25]),
            "rows_complete": all(u.get("rows_complete", True) for u in units),
            "_cells": cell_list,
        })
    # Twins: the same measurements exported twice (CSV + JSON, copies) are one study with two sources.
    by_sig: dict[str, dict] = {}
    deduped = []
    for s in studies:
        twin = by_sig.get(s["_signature"])
        if twin and twin["units"] == s["units"]:
            twin.setdefault("twin_sources", []).append(s["source"])
            continue
        by_sig[s["_signature"]] = s
        deduped.append(s)
    studies = deduped
    for s in studies:
        s.pop("_signature", None)
    # Rank: studies with controlled axes and replicates read like real experiments.
    def score(s):
        return (any(a["role"] == "treatment" for a in s["controlled_axes"]), is_primary(s["primary_metric"]), min(3, max(s["replicates_per_cell"] or {1: 0})), math.log1p(s["units"]))
    studies.sort(key=score, reverse=True)
    if study:
        hit = [s for s in studies if s["id"] == study]
        if not hit:
            return result("not_found", con, study=study)
        s = dict(hit[0])
        cells = sorted(s.pop("_cells"), key=lambda c: -(c["stats"] or {}).get("mean", -1e18))
        if not full_runs:
            for c in cells:
                c["runs_total"] = len(c["runs"])
                c["runs"] = c["runs"][:12]
        return result("found", con, study=s, cells=page(cells, offset, limit))
    items = []
    for s in studies:
        s = dict(s)
        cells = s["_cells"] if _keep_cells else s.pop("_cells")
        best = sorted([c for c in cells if c["stats"]], key=lambda c: -c["stats"]["mean"])[:3]
        s["top_cells"] = [{"id": c["id"], "levels": c["levels"], "stats": c["stats"]} for c in best]
        items.append(s)
    return result("found" if items else "not_found", con, scope=scope, studies=page(items, offset, limit),
                  limitations=["factors come from configs, table columns and differing path components; path-derived factors are inferred",
                               "cells pool units with identical factor levels; check identity_keys before treating units as independent seeds"])


# ---------------------------------------------------------------- reconcile (report numbers vs result files)

NUM_TOKEN = re.compile(r"(?<![\w.])[-+]?\d+\.\d+(?![\d.])")
PM = re.compile(r"([-+]?\d+(?:\.\d+)?)\s*(?:±|\+/-|\\pm|\+-)\s*(\d+(?:\.\d+)?)")


def _candidates(con, x: float, decimals: int):
    tol = 0.5 * 10 ** (-decimals) + 1e-12
    out = []
    for scale in (1.0, 0.01, 100.0):
        target = x * scale
        t = tol * scale
        for r in con.execute("SELECT path, locator, key, value FROM metrics WHERE value BETWEEN ? AND ? LIMIT 50", (target - t, target + t)):
            out.append({"path": r["path"], "locator": r["locator"], "key": r["key"], "value": r["value"], "scale": scale})
        if out:
            break
    return out


DECLARED_EXTERNAL = re.compile(r"(retained|reported in|from the paper|paper value|original paper|quoted|citing|baseline from|保留|原论文|论文值|引用|沿用|历史值|官方报告)", re.I)
ISO_TIME = re.compile(r"\d{4}-\d{2}-\d{2}[T ][\d:.]+(?:[+-]\d{2}:?\d{2}|Z)?|\b\d{1,2}:\d{2}(?::\d{2}(?:\.\d+)?)?\b")


def _cell_stats_cache_path(con, scope):
    try:
        db = next(r[2] for r in con.execute("PRAGMA database_list") if r[1] == "main")
        st = os.stat(db)
    except (StopIteration, OSError):
        return None
    tag = hashlib.sha256(f"{st.st_size}:{int(st.st_mtime)}:{scope}:{CELL_STATS_VERSION}".encode()).hexdigest()[:16]
    return os.path.join(os.path.dirname(db), f"cell_stats-{tag}.json")


CELL_STATS_VERSION = "6"


def _cell_stats(con, scope):
    """All recoverable cell aggregates; minutes on a 500k-file index, so cached on disk next to the index and
    invalidated whenever the index file changes."""
    cache = getattr(con, "_lw_cells", None)
    if cache is not None and cache[0] == scope:
        return cache[1]
    cpath = _cell_stats_cache_path(con, scope)
    if cpath and os.path.exists(cpath):
        try:
            with open(cpath, encoding="utf-8") as fh:
                out = [tuple(x) for x in json.load(fh)]
            try:
                con._lw_cells = (scope, out)
            except AttributeError:
                pass
            return out
        except (OSError, ValueError):
            pass
    out = _cell_stats_compute(con, scope)
    if cpath:
        try:
            tmp = cpath + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(out, fh, ensure_ascii=False, default=str)
            os.replace(tmp, cpath)
        except OSError:
            pass  # read-only workspace: just recompute next time
    return out


def _cell_stats_compute(con, scope):
    out = []
    ex = experiments(con, scope=scope, limit=100000, _keep_cells=True)
    def add(vals, sid, cid, src, run, how, unit=None, levels=None):
        st = _stats(vals)
        if st and st["n"] > 1:
            # `unit` names what the n replicates are (e.g. train_seed 3072/3073/3074) so an answer can state it
            out.append((st["mean"], st.get("sd_sample"), st.get("sd_population"), st["n"], sid, cid + how, src, run["source"],
                        run["locator"], {"replicate_unit": unit, "levels": levels}))

    def ids(values):
        out = set()
        for v in values:
            try:
                v = json.loads(v) if isinstance(v, str) else v
            except ValueError:
                pass
            if v is not None and not isinstance(v, (dict, list)):
                out.add(v)
        return sorted(out, key=lambda x: (str(type(x)), x))

    for s in ex["studies"]["items"]:
        cells = s.get("_cells", [])
        for c in cells:
            flat_unit = {k: ids(json.dumps(r["seed"].get(k), default=str) for r in c["runs"]) for k in s["replicate_keys"]}
            add([r["value"] for r in c["runs"]], s["id"], c["id"], s["source"], c["runs"][0], "",
                {"pooled": flat_unit} if flat_unit else None, c["levels"])
            # Hierarchical: average within one replicate key (e.g. eval seeds), then spread across the other (train seeds).
            for k in s["replicate_keys"]:
                groups = defaultdict(list)
                for r in c["runs"]:
                    if r["value"] is not None:
                        groups[json.dumps(r["seed"].get(k), default=str)].append(r["value"])
                if 1 < len(groups) < len(c["runs"]):
                    add([statistics.fmean(v) for v in groups.values()], s["id"], c["id"], s["source"], c["runs"][0], f"|mean-of-{k}",
                        {"spread_across": k, "values": ids(groups), "averaged_within": [x for x in s["replicate_keys"] if x != k]},
                        c["levels"])
        # Marginal: pool cells that differ only in one factor (a report row that averages over tasks or variants).
        for f in s["factors"]:
            pooled = defaultdict(list)
            for c in cells:
                key = json.dumps({k: v for k, v in c["levels"].items() if k != f["key"]}, sort_keys=True, default=str)
                pooled[key].append(c)
            for key, group in pooled.items():
                if len(group) > 1:
                    per_cell = [c["stats"]["mean"] for c in group if c["stats"]]
                    shared = {k: v for k, v in group[0]["levels"].items() if k != f["key"]}
                    add(per_cell, s["id"], group[0]["id"], s["source"], group[0]["runs"][0], f"|macro-over-{f['key']}",
                        {"spread_across": f"cells of {f['key']}", "values": [c["levels"].get(f["key"]) for c in group]}, shared)
                    # The usual paper convention: per training seed, average over the pooled factor (e.g. tasks),
                    # then report mean ± SD across those seeds.
                    for k in s["replicate_keys"]:
                        per_seed = defaultdict(lambda: defaultdict(list))
                        for c in group:
                            lvl = json.dumps(c["levels"].get(f["key"]), default=str)
                            for r in c["runs"]:
                                if r["value"] is not None:
                                    per_seed[json.dumps(r["seed"].get(k), default=str)][lvl].append(r["value"])
                        complete = [lv for lv in per_seed.values() if len(lv) == len(group)]
                        if len(complete) > 1:
                            keys_complete = [kk for kk, lv in per_seed.items() if len(lv) == len(group)]
                            add([statistics.fmean(statistics.fmean(v) for v in lv.values()) for lv in complete], s["id"],
                                group[0]["id"], s["source"], group[0]["runs"][0], f"|macro-over-{f['key']}-per-{k}",
                                {"spread_across": k, "values": ids(keys_complete), "macro_over": f["key"],
                                 "macro_levels": [c["levels"].get(f["key"]) for c in group],
                                 "averaged_within": [x for x in s["replicate_keys"] if x != k]}, shared)
    try:
        con._lw_cells = (scope, out)
    except AttributeError:
        pass
    return out


def _cells_near(cells, x, tol):
    """Cells whose mean lies within tol of x (bisect on a mean-sorted copy cached on the list object's id)."""
    import bisect
    key = id(cells)
    cache = _CELL_SORT.get(key)
    if cache is None or cache[0] is not cells:
        order = sorted(cells, key=lambda c: c[0])
        cache = (cells, [c[0] for c in order], order)
        _CELL_SORT.clear()
        _CELL_SORT[key] = cache
    _, means, order = cache
    lo = bisect.bisect_left(means, x - tol - 1e-9)
    hi = bisect.bisect_right(means, x + tol + 1e-9)
    return order[lo:hi]


_CELL_SORT: dict = {}


def _close(a, b, decimals):
    return b is not None and abs(a - b) <= 0.5 * 10 ** (-decimals) + 1e-9


def _area(path, depth=2):
    return "/".join(path.split("/")[:depth])


def _sibling_sd(con, a: str, b: str, max_files: int = 300):
    """Fallback for a printed `mean ± sd`: find stored values equal to the mean, then, in those files, sibling numbers
    under one parent (a per-seed list or dict such as `macro_by_train_seed`) whose mean and sample/population SD
    reproduce the printed pair. Index-only (value and fid indexes)."""
    da = len(a.split(".")[1]) if "." in a else 0
    db = len(b.split(".")[1]) if "." in b else 0
    x = float(a)
    ranked = {}
    for scale in (1.0, 0.01, 100.0):
        tol = 0.5 * 10 ** (-da) * scale + 1e-12
        rows = con.execute("SELECT fid, locator FROM metrics_t WHERE value BETWEEN ? AND ? LIMIT 5000",
                           (x * scale - tol, x * scale + tol)).fetchall() + con.execute(
            "SELECT fid, locator FROM config_t WHERE num BETWEEN ? AND ? LIMIT 2000", (x * scale - tol, x * scale + tol)).fetchall()
        for fid, loc in rows:
            # a stored aggregate named like a mean is the best place to find its per-unit siblings
            score = 0 if re.search(r"(mean|macro|avg|average)", loc.rsplit(".", 1)[-1], re.I) else 1
            ranked[fid] = min(ranked.get(fid, 9), score)
    fids = sorted(ranked, key=lambda f: (ranked[f], f))
    hits = []
    for fid in fids[:max_files]:
        groups = defaultdict(list)
        # keys such as `macro_by_train_seed` are stored as settings (they name a seed), so look in both tables
        rows = con.execute("SELECT locator, value FROM metrics_t WHERE fid = ?", (fid,)).fetchall() + con.execute(
            "SELECT locator, num FROM config_t WHERE fid = ? AND num IS NOT NULL", (fid,)).fetchall()
        for loc, val in rows:
            m = re.match(r"^(.*?)(\[\d+\]|\.[^.\[\]]+)$", loc)
            if m:
                groups[m.group(1)].append((loc, val))
        for parent, items in groups.items():
            vals = [v for _, v in items]
            if not 2 <= len(vals) <= 12 or any(v is None for v in vals):
                continue
            m = math.fsum(vals) / len(vals)
            if not any(_close(x, m * sc, da) for sc in (1.0, 100.0, 0.01)):
                continue
            st = _stats(vals)
            for scale in (1.0, 100.0, 0.01):
                if st and _close(x, st["mean"] * scale, da):
                    conv = ("sample" if st.get("sd_sample") is not None and _close(float(b), st["sd_sample"] * scale, db) else
                            "population" if st.get("sd_population") is not None and _close(float(b), st["sd_population"] * scale, db) else None)
                    if conv:
                        path = con.execute("SELECT path FROM files WHERE fid = ?", (fid,)).fetchone()[0]
                        hits.append({"source": path, "locator": parent, "n": st["n"], "sd": conv, "per_unit_values": [round(v * scale, 4) for v in vals],
                                     "sd_values": {"sample_sd": round(st["sd_sample"] * scale, 4), "population_sd": round(st["sd_population"] * scale, 4)},
                                     "replicate_unit": {"from": "sibling values under " + parent, "keys": [l.rsplit(".", 1)[-1] if not l.endswith("]") else l[l.rfind("[") :] for l, _ in items]}})
                    break
    return hits


def reconcile(con, scope: str | None = None, path: str | None = None, offset: int = 0, limit: int = 20, min_decimals: int = 2) -> dict:
    """Trace every number printed in a report back to stored values, recomputed aggregates or same-line arithmetic.

    States: sourced (≤5 raw values in the report's own area print identically), derived (mean±sd of a recovered
    cell — with SD convention — or a difference of two numbers on the same line), ambiguous (many coincidental
    matches), unsourced (nothing collected prints this value).
    """
    like = path if path else (f"{scope.rstrip('/')}/%" if scope else "%")
    op = "=" if path else "LIKE"
    cells = _cell_stats(con, None)
    docs = []
    for d in con.execute(f"SELECT DISTINCT l.path FROM lines l JOIN files f ON f.path = l.path WHERE f.role = 'report' AND f.ext IN ('.md', '.markdown', '.tex', '.rst', '.html') AND l.kind = 'numbers' AND l.path {op} ?", (like,)):
        nums = []
        area = _area(d["path"])
        for r in con.execute("SELECT line, text FROM lines WHERE path = ? AND kind = 'numbers' ORDER BY line", (d["path"],)):
            text = ISO_TIME.sub(" ", r["text"])
            consumed = set()
            for m in PM.finditer(text):
                a, b = m.group(1), m.group(2)
                da = len(a.split(".")[1]) if "." in a else 0
                db = len(b.split(".")[1]) if "." in b else 0
                hits = []
                for scale in (1.0, 100.0, 0.01):
                    for mean, sds, sdp, n, sid, cid, ssrc, rsrc, rloc, extra in _cells_near(cells, float(a) / scale, 0.5 * 10 ** (-da) / scale):
                        if not _close(float(a), mean * scale, da):
                            continue
                        conv, approx = None, False
                        for name_, v in (("sample", sds), ("population", sdp)):
                            if v is not None and _close(float(b), v * scale, db):
                                conv = name_
                                break
                        if conv is None:
                            # authors often take the SD of already-rounded per-seed means: allow one unit in the last digit
                            for name_, v in (("sample", sds), ("population", sdp)):
                                if v is not None and abs(float(b) - v * scale) <= 10 ** (-db) + 1e-9:
                                    conv, approx = name_, True
                                    break
                        if conv:
                            # spell out the other convention so a reader can state both
                            alt = {"sample_sd": round(sds * scale, 4) if sds is not None else None,
                                   "population_sd": round(sdp * scale, 4) if sdp is not None else None}
                            hit = {"study": sid, "cell": cid, "n": n, "sd": conv, "sd_values": alt, "source": ssrc,
                                   "example_run": rsrc, "locator": rloc, **{k: v for k, v in extra.items() if v}}
                            if approx:
                                hit["sd_rounding"] = "printed SD is off by one unit in the last digit: consistent with an SD of rounded per-seed means"
                            hits.append(hit)
                exact = [h for h in hits if "sd_rounding" not in h]
                hits = exact or hits
                if not hits:
                    hits = _sibling_sd(con, a, b)
                # a report at the project root or one level down summarises the whole project: every area is local
                local = [h for h in hits if d["path"].count("/") <= 1 or _area(h["source"]) == area]
                if local:
                    state = "derived" if len(local) <= 5 else "ambiguous"
                elif hits:
                    # only matched in another part of the project: a lead, not a source (could be a coincidence)
                    state = "derived_elsewhere" if len(hits) <= 5 else "ambiguous"
                    local = hits
                else:
                    state = "declared_external" if DECLARED_EXTERNAL.search(r["text"]) else "unsourced"
                nums.append({"line": r["line"], "number": m.group(0), "kind": "mean±sd", "state": state, "sources": local[:3],
                             "n_sources": len(local), "sd_conventions": sorted({h["sd"] for h in local}), "context": r["text"][:160]})
                consumed.update({m.start(1), m.start(2)})
            tokens = [(mm.start(), mm.group(0)) for mm in NUM_TOKEN.finditer(text)]
            values = [float(t) for _, t in tokens]
            for pos, tok in tokens:
                if any(abs(pos - c) <= 1 for c in consumed):
                    continue
                dec = len(tok.split(".")[1])
                if dec < min_decimals:
                    continue
                x = float(tok)
                if re.fullmatch(r"20\d\d\.\d+", tok):
                    continue
                cands = [c for c in _candidates(con, x, dec) if c["path"] != d["path"]]
                local = [c for c in cands if _area(c["path"]) == area]
                use = local if local else cands
                diff = next(([p, q] for i, p in enumerate(values) for q in values[i + 1:]
                             if p != x and q != x and (_close(x, p - q, dec) or _close(x, q - p, dec))), None)
                if not use and not diff and DECLARED_EXTERNAL.search(r["text"]):
                    state = "declared_external"  # the report itself says this value is retained/quoted, not recomputed here
                elif 0 < len(use) <= 5:
                    state = "sourced"
                elif diff:
                    state = "derived"
                else:
                    state = "ambiguous" if use else "unsourced"
                item = {"line": r["line"], "number": tok, "kind": "difference" if state == "derived" else "value", "state": state,
                        "sources": use[:3], "n_sources": len(use), "local": bool(local), "context": r["text"][:160]}
                if diff and state == "derived":
                    item["operands"] = diff
                nums.append(item)
        if nums:
            c = Counter(n["state"] for n in nums)
            entry = {"report": d["path"], "numbers": len(nums), "by_state": dict(c),
                     "traced_ratio": round((c["sourced"] + c["derived"] + c["derived_elsewhere"] + c["declared_external"]) / len(nums), 3), "_nums": nums}
            # Only unambiguous matches decide a convention (n_sources <= 5 and exactly one convention fits).
            conv = defaultdict(list)
            for n in nums:
                if n["state"] in ("derived", "derived_elsewhere") and len(n.get("sd_conventions", [])) == 1:
                    conv[n["sd_conventions"][0]].append(f"line {n['line']}: {n['number']}")
            if len(conv) > 1:
                entry["mixed_sd_conventions"] = {k: v[:4] for k, v in conv.items()}
                entry["warning"] = ("this report prints sample-SD and population-SD values side by side; "
                                    "the ± values are not comparable across those rows")
            docs.append(entry)
    docs.sort(key=lambda x: (x["traced_ratio"], -x["numbers"]))
    if path:
        if not docs:
            return result("unknown", con, path=path, limitations=["no numeric lines extracted for this report"])
        doc = docs[0]
        nums = doc.pop("_nums")
        # Summarise untraceable numbers by table row label: "the Pure-CEM rows have no raw data here" reads better
        # than 25 separate misses.
        rows = defaultdict(list)
        for n in nums:
            if n["state"] == "unsourced":
                cells = [c.strip(" *`") for c in n["context"].strip().strip("|").split("|")]
                label = " | ".join(c for c in cells if c and not NUM_TOKEN.search(c))[:120] or f"line {n['line']}"
                rows[label].append(n["number"])
        doc["unsourced_by_row"] = [{"row": k, "count": len(v), "numbers": v[:6]} for k, v in sorted(rows.items(), key=lambda kv: -len(kv[1]))]
        return result("found", con, report=doc, numbers=page(nums, offset, limit),
                      limitations=["value matches are coincidences at printed precision (also x100 / /100) until the locator is read",
                                   "unsourced can mean the source was not collected (binary, too large, another project) or was computed elsewhere"])
    for d in docs:
        nums = d.pop("_nums")
        d["unsourced_examples"] = [n for n in nums if n["state"] == "unsourced"][:3]
        d["sd_conventions"] = sorted({c for n in nums for c in n.get("sd_conventions", [])})
    total = Counter()
    for d in docs:
        total.update(d["by_state"])
    return result("found" if docs else "not_found", con, totals=dict(total), reports=page(docs, offset, limit))


# ---------------------------------------------------------------- timeline

def timeline(con, depth: int = 3, offset: int = 0, limit: int = 40) -> dict:
    events: dict[tuple, dict] = {}
    date_in_path = re.compile(r"(20\d{2})[-_]?(0[1-9]|1[0-2])[-_]?(0[1-9]|[12]\d|3[01])")
    for r in con.execute("SELECT path, role, title, mtime FROM files"):
        parts = r["path"].split("/")
        for i, comp in enumerate(parts[:-1][:depth + 2]):
            m = date_in_path.search(comp)
            if m:
                area = "/".join(parts[: i + 1])
                key = ("-".join(m.groups()), area)
                e = events.setdefault(key, {"date": key[0], "area": area, "authority": "path-date", "files": 0, "roles": Counter(), "reports": []})
                e["files"] += 1
                e["roles"][r["role"] or "binary"] += 1
                if r["role"] == "report" and len(e["reports"]) < 3:
                    e["reports"].append({"path": r["path"], "title": r["title"]})
                break
    items = []
    for e in sorted(events.values(), key=lambda e: (e["date"], e["area"])):
        e["roles"] = dict(e["roles"].most_common(6))
        items.append(e)
    return result("found" if items else "unknown", con, events=page(items, offset, limit),
                  limitations=["dates come from directory names; content dates and mtimes are not treated as research events"])


# ---------------------------------------------------------------- research outline proposal

def _location_role(path: str) -> str:
    p = "/".join(path.lower().replace("/**/", "/").split("/")[-4:])  # the nearest folders say what a file is for
    if re.search(r"(legacy|archive|quarantine|old|backup|deprecated)", p):
        return "historical copy"
    if re.search(r"(picture|figure|fig|plot|tsne|visual)", p):
        return "figure data"
    if re.search(r"(collected|raw|runs?/|cells/|eval_seed|per_eval|all_\d+_seed)", p):
        return "raw results"
    if re.search(r"(summary|final|table|paper|report|closeout|aggregate)", p):
        return "summary"
    return "raw results"


def outline(con, scope: str | None = None, limit: int = 25) -> dict:
    """Human-style decomposition proposal, independent of folder layout.

    An *experiment* is identified by what was varied (treatment factors) and what was measured (primary
    metric family). The same experiment found in several folders (raw results, summary tables, figure
    data, legacy copies) is one experiment with several evidence locations. Reports whose text names the
    factor levels are attached as the authors' own framing. Proposal only: the agent reads and decides.
    """
    ex = experiments(con, scope=scope, limit=100000)
    groups: dict[tuple, dict] = {}
    for s in ex["studies"]["items"]:
        if not PRIMARY_METRIC.search(s["primary_metric"] or ""):
            continue
        treat = sorted(f["key"] for f in s["factors"] if f["role"] == "treatment" and f["authority"] != "absent")
        reps = max((int(k) for k in s["replicates_per_cell"]), default=0)
        if not treat or (not s["controlled_axes"] and reps < 2):
            continue
        metric_family = re.sub(r"^(rows\.|table:|metrics\.)", "", s["primary_metric"])
        metric_family = "success" if re.search(r"succ|sr", metric_family, re.I) else metric_family
        key = (tuple(treat), metric_family)
        g = groups.setdefault(key, {"experiment": f"How do {', '.join(treat)} affect {metric_family}?",
                                    "treatment_factors": treat, "metric": metric_family, "context": set(), "levels": defaultdict(set),
                                    "locations": [], "units": 0})
        g["units"] += s["units"]
        g["context"].update(f["key"] for f in s["factors"] if f["role"] == "context")
        for f in s["factors"]:
            if f["key"] in treat:
                g["levels"][f["key"]].update(f["example_levels"])
        g["locations"].append({"study": s["id"], "source": s["source"], "role": _location_role(s["source"]), "unit": s["unit"],
                               "units": s["units"], "cells": s["cells"], "replicates_per_cell": s["replicates_per_cell"],
                               "primary_metric": s["primary_metric"], "top_cells": s["top_cells"][:2],
                               "twin_sources": s.get("twin_sources", [])})
    items = []
    for g in groups.values():
        levels = sorted({str(v).strip('"') for vs in g["levels"].values() for v in vs if v not in ("null",) and len(str(v)) >= 3})
        framing = []
        if levels:
            like = [f"%{lv}%" for lv in levels[:6]]
            q = " OR ".join(["l.text LIKE ?"] * len(like))
            hits = Counter()
            distinct: dict[str, set] = defaultdict(set)
            first = {}
            for r in con.execute(f"SELECT l.path, l.line, l.text FROM lines l JOIN files f ON f.path = l.path WHERE f.role = 'report' AND ({q}) LIMIT 6000", like):
                hits[r["path"]] += 1
                distinct[r["path"]].update(lv for lv in levels[:6] if lv in r["text"])
                first.setdefault(r["path"], (r["line"], r["text"][:160]))
            seen_names = set()
            # A report that names more of the compared levels is about this experiment; copies are listed once.
            for p in sorted(hits, key=lambda p: (-len(distinct[p]), -hits[p], p)):
                sig = (posixpath.basename(p), hits[p])
                if sig in seen_names:
                    continue
                seen_names.add(sig)
                framing.append({"report": p, "levels_named": sorted(distinct[p]), "mentions": hits[p], "line": first[p][0], "text": first[p][1]})
                if len(framing) >= 5:
                    break
        locs = sorted(g["locations"], key=lambda x: (["summary", "raw results", "figure data", "historical copy"].index(x["role"]), -x["units"]))
        items.append({"experiment": g["experiment"], "treatment_factors": g["treatment_factors"], "metric": g["metric"],
                      "evaluated_across": sorted(g["context"]), "levels": {k: sorted(v)[:8] for k, v in g["levels"].items()},
                      "evidence_locations": len(locs), "units": g["units"],
                      "location_roles": dict(Counter(l["role"] for l in locs)), "locations": locs[:8], "author_framing": framing})
    items.sort(key=lambda x: (-(x["evidence_locations"] > 1), -min(3, len(x["treatment_factors"])), -x["units"]))
    return result("found" if items else "unknown", con, experiments=page(items, 0, limit),
                  limitations=["groups are by treatment-factor names and metric family; same names can still mean different protocols — read the protocol/report before merging",
                               "location roles (summary/raw/figure/historical) are guessed from path words; verify",
                               "experiments without controlled pairs or replicates are omitted"])
