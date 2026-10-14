"""Navigation and validity instruments: list the index like a folder, flag studies the authors marked unusable,
and find likely producers of a result the way a person would (scripts in the same study that name it)."""
from __future__ import annotations

import json
import posixpath
import re
from collections import Counter, defaultdict

from .analyze import page, result
from .index import fid_range

SCRIPT_ROLES = ("train_script", "eval_script", "script", "launcher", "module", "plot_script")
PATH_FLAG = re.compile(r"(do[_-]?not[_-]?use|donotuse|incomplete|deprecated|obsolete|superseded|invalid|broken|quarantine|"
                       r"abandon(?:ed)?|(?:^|[_.-])failed(?:$|[_.-])|(?:^|[_.-])killed(?:$|[_.-])|(?:^|[_.-])partial(?:$|[_.-])|"
                       r"(?:^|[_.-])wip(?:$|[_.-])|(?:^|[_.-])old(?:$|[_.-])|backup|(?:^|[_.-])bak(?:$|[_.-]))", re.I)
TEXT_FLAG = re.compile(r"(do not use|don't use|must not be (?:used|cited)|not be cited|superseded|replaced by|deprecated|\binvalid(?:ated)?\b|"
                       r"\bincomplete\b|abandoned|\bkilled\b|(?-i:SIGTERM|SIGKILL|\bOOM\b)|不要使用|勿用|不可(?:引用|使用)|不能(?:引用|使用)|作废|废弃|已被?(?:替代|取代)|"
                       r"取代|替代|无效|未完成|中断|不完整)", re.I)
CLAIM_KEYS = re.compile(r"(^|[_.])(status|state|complete|completed|n_cells|cells|control_cells|n_jobs|jobs|expected_jobs|total)$", re.I)


def ls(con, path: str = "", offset: int = 0, limit: int = 60) -> dict:
    """Immediate children of a directory in the index: sub-folders with file counts by role, then files."""
    base = path.strip("/")
    prefix = base + "/" if base else ""
    dirs: dict[str, Counter] = defaultdict(Counter)
    files = []
    q = "SELECT path, size, role, kind, status, title FROM files" + (" WHERE path LIKE ?" if base else "")
    for r in con.execute(q, ((prefix + "%",) if base else ())):
        rest = r["path"][len(prefix):]
        head = rest.split("/", 1)[0]
        if "::" in head:  # archive members group under their bundle
            dirs[head.split("::", 1)[0] + "::"][r["role"] or r["kind"] or "?"] += 1
        elif "/" in rest:
            dirs[head][r["role"] or r["kind"] or "?"] += 1
        else:
            files.append({"name": rest, "role": r["role"] or r["kind"], "size": r["size"], "status": r["status"],
                          "title": (r["title"] or "")[:100] or None})
    if not dirs and not files:
        near = [r[0] for r in con.execute("SELECT DISTINCT dir FROM files WHERE dir LIKE ? LIMIT 10", (f"%{base.split('/')[-1]}%",))]
        return result("not_found", con, path=path, did_you_mean=near)
    entries = [{"dir": name + "/", "files": sum(c.values()), "roles": dict(c.most_common(5)),
                "flag": bool(PATH_FLAG.search(name))} for name, c in sorted(dirs.items())]
    entries += sorted(files, key=lambda f: f["name"])
    return result("found", con, path=prefix or "/", entries=page(entries, offset, limit))


def _text_of(con, path):
    row = con.execute("SELECT json FROM facts WHERE path = ?", (path,)).fetchone()
    if not row:
        return None
    return json.loads(row["json"]).get("text")


def _exists(con, path: str) -> bool:
    """File or directory present in the inventory (index range scan; `LIKE` on an OR would scan every row)."""
    p = path.rstrip("/")
    if con.execute("SELECT 1 FROM files WHERE path = ?", (p,)).fetchone():
        return True
    return con.execute("SELECT 1 FROM files WHERE path >= ? AND path < ? LIMIT 1", (p + "/", p + "0")).fetchone() is not None


def validity(con, scope: str | None = None, offset: int = 0, limit: int = 30) -> dict:
    """Areas the authors marked unusable/incomplete/superseded (by name or in text), plus internal contradictions:
    a flagged folder whose own audit says complete, or an audit that claims N cells while few result files exist."""
    like = f"{scope.rstrip('/')}/%" if scope else "%"
    areas: dict[str, dict] = {}
    all_dirs = [d for (d,) in con.execute("SELECT DISTINCT dir FROM files WHERE path LIKE ?", (like,))]
    for d in all_dirs:
        parts = d.split("/")
        for i, comp in enumerate(parts):
            if PATH_FLAG.search(comp):
                area = "/".join(parts[: i + 1])
                areas.setdefault(area, {"area": area, "path_marker": PATH_FLAG.search(comp).group(0), "text_evidence": [],
                                        "contradictions": []})
                break
    # Text markers inside reports, wherever they are (with the line, so the agent can read the sentence).
    mentions = []
    for r in con.execute("SELECT l.path, l.line, l.text FROM lines l JOIN files f ON f.path = l.path "
                         "WHERE f.role = 'report' AND l.path LIKE ? AND l.kind IN ('outline', 'numbers')", (like,)):
        m = TEXT_FLAG.search(r["text"])
        if m:
            mentions.append({"path": r["path"], "line": r["line"], "marker": m.group(0), "text": r["text"][:200]})
    for r in con.execute("SELECT f.path, x.json FROM files f JOIN facts x ON x.path = f.path WHERE f.role = 'report' AND f.path LIKE ?", (like,)):
        text = json.loads(r["json"]).get("text")
        if not text:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            m = TEXT_FLAG.search(line)
            if m and len(mentions) < 2000:
                mentions.append({"path": r["path"], "line": i, "marker": m.group(0), "text": line.strip()[:200]})
    seen = set()
    uniq = []
    for m in mentions:
        k = (m["path"], m["line"])
        if k not in seen:
            seen.add(k)
            uniq.append(m)
    for area, info in areas.items():
        rng = fid_range(con, area) or (0, -1)
        info["files"] = rng[1] - rng[0] + 1 if rng[1] >= rng[0] else 0
        info["result_files"] = con.execute("SELECT COUNT(*) FROM files WHERE fid BETWEEN ? AND ? AND role IN ('result', 'result_table')",
                                           rng).fetchone()[0]
        info["text_evidence"] = [m for m in uniq if m["path"].startswith(area + "/")][:5]
        # contradictions: own audit/status files that claim completion or a count
        for r in con.execute("SELECT f.path, c.key, c.value, c.num FROM config_t c JOIN files f ON f.fid = c.fid "
                             "WHERE c.fid BETWEEN ? AND ?", rng):
            leaf = r["key"].split(".")[-1]
            if not CLAIM_KEYS.search(leaf):
                continue
            val = json.loads(r["value"])
            if isinstance(val, str) and val.lower() in ("complete", "completed", "done", "finished", "success", "ok"):
                info["contradictions"].append({"kind": "flagged-but-claims-complete", "path": r["path"], "key": r["key"], "value": val})
            elif r["num"] is not None and r["num"] > max(4, 2 * info["result_files"]) and leaf.lower() in ("n_cells", "cells", "control_cells", "n_jobs", "expected_jobs"):
                info["contradictions"].append({"kind": "claims-more-results-than-indexed", "path": r["path"], "key": r["key"],
                                               "claimed": r["num"], "result_files_indexed": info["result_files"]})
        for r in con.execute("SELECT f.path, x.json FROM facts_t x JOIN files f ON f.fid = x.fid "
                             "WHERE x.fid BETWEEN ? AND ? AND x.json LIKE '%\"declared\"%'", rng):
            for loc, val in json.loads(r["json"]).get("declared", {}).items():
                if (isinstance(val, str) and val.lower() in ("complete", "completed", "done", "finished", "success", "ok", "valid", "pass", "passed")) or val is True:
                    info["contradictions"].append({"kind": "flagged-but-declares-complete", "path": r["path"], "key": loc, "value": val})
        for r in con.execute("SELECT f.path, m.key, m.value FROM metrics_t m JOIN files f ON f.fid = m.fid "
                             "WHERE m.fid BETWEEN ? AND ?", rng):
            leaf = r["key"].split(".")[-1].lower()
            if leaf in ("n_cells", "cells", "control_cells", "probe_cells", "n_jobs", "expected_jobs") and r["value"] > max(4, 2 * info["result_files"]):
                info["contradictions"].append({"kind": "claims-more-results-than-indexed", "path": r["path"], "key": r["key"],
                                               "claimed": r["value"], "result_files_indexed": info["result_files"]})
        missing = []
        for r in con.execute("SELECT DISTINCT f.path AS src, t.raw FROM refs_t t JOIN files f ON f.fid = t.src "
                             "WHERE t.src BETWEEN ? AND ? AND t.mode = 'mention'", rng):
            raw = r["raw"].strip("`'\" ")
            segs = [x for x in raw.strip("/").split("/") if x]
            if raw.startswith(("/", "http", "~")) or "*" in raw or len(missing) >= 6 or posixpath.basename(r["src"]).startswith("."):
                continue
            # a path, not prose like `0/1/42` or `pixels/action/state`: a named first segment plus an extension or a known folder word
            if not segs or not re.search(r"[A-Za-z]{3}", segs[0]) or not (
                    re.search(r"\.[A-Za-z0-9]{1,5}$", segs[-1]) or raw.endswith("/") or
                    segs[0].lower() in ("results", "runs", "logs", "cells", "probes", "checkpoints", "ckpt", "outputs", "data", "summary", "evals")):
                continue
            cand = posixpath.normpath(posixpath.join(posixpath.dirname(r["src"]), raw))
            if not _exists(con, cand):
                missing.append({"cited_in": r["src"], "path": raw})
        # authors usually write paths in backticks: `results/cells/` — check those relative to the citing document
        try:
            doc_rows = con.execute("SELECT f.path, t.text FROM texts_t t JOIN files f ON f.fid = t.fid WHERE t.fid BETWEEN ? AND ?",
                                   rng).fetchall()
        except Exception:
            doc_rows = []
        for r in doc_rows:
            if posixpath.basename(r["path"]).startswith("."):
                continue
            for raw in re.findall(r"`([^`\s]+/[^`\s]*)`", r["text"] or ""):
                if raw.startswith(("/", "http", "~")) or "*" in raw or "{" in raw or len(missing) >= 8 or \
                        not re.search(r"[A-Za-z]{3}", raw.split("/")[0]):
                    continue
                cand = posixpath.normpath(posixpath.join(posixpath.dirname(r["path"]), raw))
                alt = posixpath.normpath(posixpath.join(area, raw))
                if not any(_exists(con, c) for c in (cand, alt)):
                    item = {"cited_in": r["path"], "path": raw}
                    if item not in missing:
                        missing.append(item)
        if missing:
            info["contradictions"].append({"kind": "referenced-but-missing", "items": missing})
        info["contradictions"] = info["contradictions"][:8]
    # For each flagged study, the authors' usable alternatives: unflagged sibling studies that share its name stem
    # (e.g. `mechanism_multitask_..._incomplete_do_not_use` -> `mechanism_rawgoal_7local_5goal_20260911`).
    for area, info in areas.items():
        base = posixpath.basename(area)
        stem = PATH_FLAG.sub("", base)
        words = {w for w in re.split(r"[_\-.]+", stem.lower()) if len(w) >= 4 and not w.isdigit()}
        parent = posixpath.dirname(area)
        alts = []
        siblings = {(d[len(parent) + 1:] if parent else d).split("/")[0] for d in all_dirs
                    if (not parent or d.startswith(parent + "/")) and not d.startswith(area)}
        for name in sorted(siblings):
            if not name or PATH_FLAG.search(name) or name in [a["study"] for a in alts]:
                continue
            shared = words & {w for w in re.split(r"[_\-.]+", name.lower()) if len(w) >= 4}
            if len(shared) >= max(1, len(words) // 3):
                full = (parent + "/" + name) if parent else name
                rng2 = fid_range(con, full) or (0, -1)
                n_res = con.execute("SELECT COUNT(*) FROM files WHERE fid BETWEEN ? AND ? AND role IN ('result', 'result_table')",
                                    rng2).fetchone()[0]
                alts.append({"study": name, "path": full, "shared_terms": sorted(shared), "result_files": n_res})
        alts.sort(key=lambda a: (-len(a["shared_terms"]), -a["result_files"]))
        if alts:
            info["unflagged_alternatives"] = alts[:4]
    items = sorted(areas.values(), key=lambda a: (-len(a["contradictions"]), a["area"]))
    loose = [m for m in uniq if not any(m["path"].startswith(a + "/") for a in areas)]
    # Divergent copies: the same document (same file name and title) saved in several places with different content.
    # One of them is stale; a reader citing the wrong copy cites a superseded number.
    by_doc = defaultdict(list)
    for r in con.execute("SELECT path, sha, size, mtime, title FROM files WHERE role = 'report' AND path LIKE ? AND title IS NOT NULL", (like,)):
        base = posixpath.basename(r["path"].split("::")[-1])
        if KEY_DOC.search(base) and not base.startswith(".") and (r["title"] or "").strip():
            by_doc[(base, r["title"].strip().lower())].append(dict(r))
    divergent = []
    for (base, _), copies in by_doc.items():
        shas = {c["sha"] for c in copies if c["sha"]}
        if len(shas) > 1 and len(copies) <= 12:
            copies.sort(key=lambda c: -(c["mtime"] or 0))
            divergent.append({"document": base, "versions": len(shas),
                              "copies": [{"path": c["path"], "size": c["size"], "mtime": c["mtime"],
                                          "newest": i == 0} for i, c in enumerate(copies[:6])]})
    divergent.sort(key=lambda g: (-g["versions"], g["document"]))
    # Key documents (README/FINAL/STATUS/...) citing files that are not in the folder at all.
    missing_cited = []
    docs = con.execute("SELECT t.path, t.text FROM texts t JOIN files f ON f.path = t.path WHERE f.role = 'report' AND t.path LIKE ? "
                       "AND t.path NOT LIKE '%::%'", (like,)).fetchall()
    for r in sorted(docs, key=lambda r: r["path"].count("/")):
        base = posixpath.basename(r["path"])
        if not KEY_DOC.search(base) or base.startswith(".") or len(missing_cited) >= 25:
            continue
        for raw in dict.fromkeys(re.findall(r"`([^`\s]+\.(?:csv|json|jsonl|md|pt|npz|txt|yaml|tar\.gz|tgz|py))`", r["text"] or "")):
            if raw.startswith(("/", "http", "~")) or any(ch in raw for ch in "*{<>$"):
                continue  # absolute paths, globs and templates such as evaluations/<run>/ are not citations of one file
            here = posixpath.normpath(posixpath.join(posixpath.dirname(r["path"]), raw))
            if _exists(con, here) or _exists(con, raw):
                continue
            # bare file names may legitimately live anywhere in the project
            if "/" not in raw and con.execute("SELECT 1 FROM files WHERE path LIKE ? LIMIT 1", ("%/" + raw,)).fetchone():
                continue
            missing_cited.append({"cited_in": r["path"], "path": raw})
    return result("found" if items or loose or divergent or missing_cited else "not_found", con, flagged_areas=page(items, offset, limit),
                  report_statements=page(loose, 0, 40), divergent_copies=page(divergent, 0, 15),
                  cited_but_missing=page(missing_cited, 0, 25),
                  limitations=["markers are words chosen by the authors; read the cited line before treating a study as invalid",
                               "a flagged name without a written reason is a warning, not a verdict"])


def producers(con, path: str, max_up: int = 7, limit: int = 12) -> dict:
    """Rank scripts/launchers in the same study (ancestor dirs) by how many of the result's own path tokens they name,
    and collect `host`-like fields from nearby manifests. Authority: inferred (static text match)."""
    parts = path.split("/")
    tokens = set()
    for comp in parts[:-1][-4:] + [posixpath.splitext(parts[-1])[0]]:
        tokens.add(comp.lower())
        tokens.update(t.lower() for t in re.split(r"[_\-.]", comp) if len(t) >= 3 and not t.isdigit())
    tokens = {t for t in tokens if len(t) >= 3}
    cands = []
    dirs = ["/".join(parts[:i]) for i in range(len(parts) - 1, max(0, len(parts) - 1 - max_up), -1)]
    for d in dirs:
        for r in con.execute(f"SELECT f.path, f.role, x.json FROM files f LEFT JOIN facts x ON x.path = f.path WHERE f.dir = ? "
                             f"AND f.role IN ({','.join('?' * len(SCRIPT_ROLES))})", (d, *SCRIPT_ROLES)):
            facts = json.loads(r["json"]) if r["json"] else {}
            hay = " ".join([facts.get("text") or "", " ".join(facts.get("refs", [])), " ".join(facts.get("ids", [])),
                            " ".join(c[1] for c in facts.get("cmds", []))]).lower()
            hits = sorted(t for t in tokens if t in hay)
            if hits:
                cands.append({"file": r["path"], "role": r["role"], "matched_tokens": hits, "distance": len(parts) - 1 - d.count("/") - 1})
    reader = re.compile(r"(aggregat|collect|plot|summar|report|analy|figure|table|stats?|compare|audit|check|monitor|watch)", re.I)
    for c in cands:
        c["looks_like"] = "consumer (aggregates/plots results)" if reader.search(posixpath.basename(c["file"])) else "producer (runs/launches)"
    cands.sort(key=lambda c: (c["looks_like"].startswith("consumer"), -len(c["matched_tokens"]), c["distance"], c["file"]))
    hosts = []
    host_key = re.compile(r"(^|[._])(host|hostname|machine|node|node_name|server|cluster)$", re.I)
    for d in dirs:
        for r in con.execute("SELECT f.path, x.json FROM files f JOIN facts x ON x.path = f.path WHERE f.dir = ?", (d,)):
            facts = json.loads(r["json"])
            for loc, val in list((facts.get("declared") or {}).items()) + list((facts.get("config") or {}).items()):
                if host_key.search(loc) and isinstance(val, str) and len(hosts) < 6:
                    hosts.append({"path": r["path"], "key": loc, "value": val})
        if hosts:
            break
    return {"inferred_producers": cands[:limit], "host_fields": hosts, "tokens": sorted(tokens)[:20]}


KEY_DOC = re.compile(r"(readme|final|status|summary|provenance|handoff|protocol|results?|report|overview|项目卡片|交接|总结|结果)", re.I)


def brief(con, scope: str | None = None, limit: int = 25) -> dict:
    """One-call orientation, the way a person starts: the authors' key documents (full paths, shallow first),
    the folder layout, flagged/unusable studies and the strongest recovered experiments."""
    like = f"{scope.rstrip('/')}/%" if scope else "%"
    docs = []
    for r in con.execute("SELECT path, title, size, mtime FROM files WHERE role = 'report' AND path LIKE ? AND path NOT LIKE '%::%'", (like,)):
        base = posixpath.basename(r["path"])
        if not KEY_DOC.search(base) or base.startswith("."):
            continue
        depth = r["path"].count("/")
        vendored = bool(re.search(r"(^|/)(code|repositories|working-snapshots|runtime|third_party|vendor|site-packages|node_modules)/", r["path"]))
        docs.append({"path": r["path"], "title": r["title"], "depth": depth, "vendored_code": vendored, "mtime": r["mtime"]})
    docs.sort(key=lambda d: (d["vendored_code"], d["depth"], -(d["mtime"] or 0)))
    seen_titles = set()
    key_docs = []
    for d in docs:
        t = (d["title"] or "").strip().lower()
        if t and t in seen_titles:
            continue
        seen_titles.add(t)
        key_docs.append({k: d[k] for k in ("path", "title")})
        if len(key_docs) >= limit:
            break
    root = ls(con, scope or "", limit=40)
    flags = validity(con, scope=scope, limit=10)
    flagged = [{"area": a["area"], "marker": a["path_marker"], "contradictions": [c["kind"] for c in a["contradictions"]]}
               for a in flags["flagged_areas"]["items"]]
    return result("found", con, key_documents=key_docs, layout=root.get("entries", {}).get("items", []), flagged_studies=flagged,
                  next=["trace read --path <key document>", "trace outline / trace experiments --scope <area>",
                        "trace reconcile --path <report>", "trace validity --scope <area>"])


HOST_TOKEN = re.compile(r"^(?:h(?:20|200)?[-_]?\d{1,3}|h20[-_]\d|h200[-_]\d|4090[-_]\d+(?:[-_]\d+)?|"
                        r"5090[-_]?d?[-_]\d+|(?:a100|h100|pro6000)[-_]?\d+|node\d+|gpu\d{2,})$", re.I)


def host_hints(path: str) -> list[dict]:
    """Host names encoded in the layout (`collected/h204/`, `queues/final/rp6.jsonl`). Authority: path-token (inferred)."""
    out = []
    for comp in path.split("/"):
        stem = posixpath.splitext(comp)[0]
        if HOST_TOKEN.match(stem):
            out.append({"token": stem, "from": comp, "authority": "path-token"})
    return out


def dir_provenance(con, path: str) -> dict:
    """Provenance for a directory (a study's summary/ or run folder): who writes into it, which scripts sit in it
    or above it, and who cites it."""
    d = path.strip("/")
    n = con.execute("SELECT COUNT(*) FROM files WHERE path LIKE ?", (d + "/%",)).fetchone()[0]
    if not n:
        return result("not_found", con, path=path)
    writers = [dict(file=r["src"], via=r["mode"], ref=r["raw"]) for r in con.execute(
        "SELECT DISTINCT src, raw, mode FROM refs WHERE (target = ? OR target LIKE ?) AND mode = 'write' LIMIT 40", (d, d + "/%"))]
    scripts = []
    parts = d.split("/")
    for i in range(len(parts), max(0, len(parts) - 4), -1):
        anc = "/".join(parts[:i])
        for r in con.execute(f"SELECT path, role FROM files WHERE dir = ? AND role IN ({','.join('?' * len(SCRIPT_ROLES))})", (anc, *SCRIPT_ROLES)):
            scripts.append({"file": r["path"], "role": r["role"], "levels_up": len(parts) - i})
    cited_by = [dict(file=r["src"], mode=r["mode"]) for r in con.execute(
        "SELECT DISTINCT src, mode FROM refs WHERE (target = ? OR target LIKE ?) AND src NOT LIKE ? LIMIT 40", (d, d + "/%", d + "/%"))]
    roles = dict(con.execute("SELECT role, COUNT(*) FROM files WHERE path LIKE ? GROUP BY role", (d + "/%",)).fetchall())
    hosts = sorted({h["token"] for (p,) in con.execute("SELECT path FROM files WHERE path LIKE ? LIMIT 5000", (d + "/%",))
                    for h in host_hints(p[len(d) + 1:])})
    declared_hosts = []
    host_key = re.compile(r"(^|[._])(host|hostname|machine|node_name|server|cluster)$", re.I)
    for r in con.execute("SELECT x.path, x.json FROM facts x WHERE x.path LIKE ? AND x.json LIKE '%declared%' LIMIT 400", (d + "/%",)):
        for loc, val in (json.loads(r["json"]).get("declared") or {}).items():
            if host_key.search(loc) and isinstance(val, str) and len(declared_hosts) < 10:
                declared_hosts.append({"path": r["path"], "key": loc, "value": val})
    return result("found", con, path=d, kind="directory", files=n, roles=roles, writers=writers, scripts_here_or_above=scripts[:30],
                  cited_by=cited_by, host_hints_below=hosts[:20], declared_hosts=declared_hosts, named_by=name_mentions(con, d),
                  limitations=["scripts listed by location; read them to see which outputs they produce"])


def pair(a_doc, b_doc, key: str | None = None, value: str | None = None) -> dict:
    """Paired per-item comparison of two result documents (e.g. per-episode success arrays from two evaluations)."""
    def arrays(doc):
        flat = {}

        def walk(o, p="$"):
            if isinstance(o, dict):
                for k, v in o.items():
                    walk(v, f"{p}.{k}")
            elif isinstance(o, list) and o and all(isinstance(x, (int, float, bool)) for x in o):
                flat[p] = o
        walk(doc)
        return flat
    fa, fb = arrays(a_doc), arrays(b_doc)
    succ = re.compile(r"(success|succ|solved|done|correct|hit)", re.I)
    ids = re.compile(r"(episode|ids?|index|indices|seed|start)", re.I)

    def pick(flat, wanted, rx, binary):
        if wanted:
            return next((p for p in flat if p.endswith("." + wanted) or p == wanted), None)
        cands = [p for p in flat if rx.search(p.split(".")[-1]) and (not binary or set(map(float, flat[p])) <= {0.0, 1.0})]
        return cands[0] if cands else None
    va, vb = pick(fa, value, succ, True), pick(fb, value, succ, True)
    if not va or not vb:
        return {"status": "unknown", "reason": "no binary per-item array found; pass --value", "arrays_a": list(fa)[:12], "arrays_b": list(fb)[:12]}
    def pick_key(flat, wanted, exclude):
        if wanted:
            return pick(flat, wanted, ids, False)
        # an id array: unique values, same length as the outcome array, and not the outcome array itself
        n = len(flat[exclude])
        cands = [p for p in flat if p != exclude and ids.search(p.split(".")[-1]) and len(flat[p]) == n
                 and len(set(flat[p])) == n and not succ.search(p.split(".")[-1])]
        return cands[0] if cands else None
    ka, kb = pick_key(fa, key, va), pick_key(fb, key, vb)
    A, B = fa[va], fb[vb]
    if ka and kb and len(fa[ka]) == len(A) and len(fb[kb]) == len(B):
        ma = dict(zip(fa[ka], A))
        mb = dict(zip(fb[kb], B))
        common = sorted(set(ma) & set(mb), key=str)
        pairs = [(ma[i], mb[i]) for i in common]
        aligned = f"by {ka.split('.')[-1]}"
    elif len(A) == len(B):
        pairs = list(zip(A, B))
        aligned = "by position (no shared id array found)"
    else:
        return {"status": "unknown", "reason": f"arrays differ in length ({len(A)} vs {len(B)}) and no id array to align"}
    c = Counter((bool(x), bool(y)) for x, y in pairs)
    return {"status": "found", "aligned": aligned, "n": len(pairs), "a_value": va, "b_value": vb,
            "both": c[(True, True)], "only_a": c[(True, False)], "only_b": c[(False, True)], "neither": c[(False, False)],
            "a_rate": round(sum(x for x, _ in pairs) / max(1, len(pairs)), 6), "b_rate": round(sum(y for _, y in pairs) / max(1, len(pairs)), 6)}


def find(con, queries: list[str], context: int = 3, per_query: int = 4, scope: str | None = None) -> dict:
    """Several literal queries in one call; each returns the best text windows (±context lines) from the probe's text
    snapshots, authors' key documents first, identical content collapsed. Like `grep -C` over many files at once,
    without touching the (possibly slow) source mount."""
    like = f"{scope.rstrip('/')}/%" if scope else "%"
    out = []
    for q in queries:
        # A phrase first (what a person types into grep); fall back to all-terms-in-file only if the phrase is absent.
        rows = con.execute("SELECT t.path, t.text, f.sha, f.role FROM texts t JOIN files f ON f.path = t.path "
                           "WHERE t.path LIKE ? AND lower(t.text) LIKE ? LIMIT 400", [like, f"%{q.lower()}%"]).fetchall()
        terms = [q.lower()]
        mode = "phrase"
        if not rows:
            terms = [t.lower() for t in q.split() if t.strip()] or [q.lower()]
            where = " AND ".join("lower(t.text) LIKE ?" for _ in terms)
            rows = con.execute(f"SELECT t.path, t.text, f.sha, f.role FROM texts t JOIN files f ON f.path = t.path "
                               f"WHERE t.path LIKE ? AND {where} LIMIT 400", [like] + [f"%{t}%" for t in terms]).fetchall()
            mode = "all-terms"
        windows, seen_sha = [], set()
        for r in rows:
            if r["sha"] in seen_sha:
                continue
            seen_sha.add(r["sha"])
            lines = r["text"].splitlines()
            best = None
            for i, line in enumerate(lines):
                low = line.lower()
                n = sum(t in low for t in terms)
                if n and (best is None or n > best[0]):
                    best = (n, i)
            if best is None:  # terms spread over several lines: take the first line with any term
                best = next(((1, i) for i, l in enumerate(lines) if any(t in l.lower() for t in terms)), (0, 0))
            i = best[1]
            base = posixpath.basename(r["path"])
            vendored = bool(re.search(r"(^|/)(code|repositories|working-snapshots|runtime|third_party|vendor|site-packages)/", r["path"]))
            score = (best[0] == len(terms), not vendored, bool(KEY_DOC.search(base)), -r["path"].count("/"))
            windows.append((score, {"path": r["path"], "role": r["role"], "line": i + 1,
                                    "window": [f"{j + 1}: {lines[j][:300]}" for j in range(max(0, i - context), min(len(lines), i + context + 1))]}))
        windows.sort(key=lambda w: w[0], reverse=True)
        # Folder/file names are part of what authors wrote (`..._incomplete_do_not_use`): report them too.
        path_hits = [r[0] for r in con.execute("SELECT DISTINCT dir FROM files WHERE path LIKE ? AND lower(dir) LIKE ? LIMIT 400",
                                                (like, f"%{q.lower()}%"))]
        roots = sorted({p[: p.lower().index(q.lower()) + len(q)] + p[p.lower().index(q.lower()) + len(q):].split("/")[0]
                        for p in path_hits})[:6]
        if not windows:
            # IDs and names often live only in structured files (job queues, manifests, tables): look in extracted facts.
            for r in con.execute("SELECT x.path, x.json, f.role FROM facts x JOIN files f ON f.path = x.path WHERE x.path LIKE ? "
                                 "AND lower(x.json) LIKE ? LIMIT 50", (like, f"%{q.lower()}%")):
                facts = json.loads(r["json"])
                rows_hit = [row for row in ((facts.get("table") or {}).get("rows") or []) if q.lower() in json.dumps(row, ensure_ascii=False).lower()]
                snippet = rows_hit[:2] or [v for v in (facts.get("refs", []) + facts.get("ids", [])) if q.lower() in str(v).lower()][:3]
                windows.append(((True, True, False, 0), {"path": r["path"], "role": r["role"], "in": "structured facts", "matches": snippet}))
            mode = mode + "+facts" if windows else mode
        item = {"query": q, "match": mode, "files_matched": len(rows) or len(windows), "hits": [w for _, w in windows[:per_query]]}
        if roots:
            item["in_paths"] = roots
        out.append(item)
    return result("found" if any(o["hits"] or o.get("in_paths") for o in out) else "not_found", con, results=out,
                  limitations=["searches text snapshots (reports, READMEs, notes, launchers, small JSON); use grep for other files",
                               "all terms of one query must occur in the same file"])


def name_mentions(con, path: str, limit: int = 15) -> list[dict]:
    """Files whose extracted content names this artifact's own directory/file stem — job queues, manifests, launch
    lists. `pusht_e1opt_search_rh1_s42` in `queues/final/rp6.jsonl` links the result folder to its job."""
    parts = path.rstrip("/").split("/")
    names = [posixpath.splitext(parts[-1])[0]] if "." in parts[-1] else []
    names += [p for p in reversed(parts[:-1] if "." in parts[-1] else parts) if len(p) >= 8 and re.search(r"[_\-]", p)][:2]
    out, seen = [], set()
    for nm in names:
        if len(nm) < 8:
            continue
        for r in con.execute("SELECT f.path, f.role FROM facts x JOIN files f ON f.path = x.path WHERE x.json LIKE ? AND f.path NOT LIKE ? LIMIT ?",
                             (f"%{nm}%", "/".join(parts[:-1]) + "/%" if "." in parts[-1] else path.rstrip("/") + "/%", limit)):
            if r["path"] not in seen:
                seen.add(r["path"])
                out.append({"file": r["path"], "role": r["role"], "names": nm})
        if out:
            break
    return out[:limit]
