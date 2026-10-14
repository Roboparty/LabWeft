"""Consistency audit across replicate runs: the cross-checks a reviewer otherwise scripts by hand.

Files whose paths differ only in numbers (`train3072/train.log`, `train3073/train.log`, ...) are treated as one group
of replicates. Within a group the audit reports
- identical-replicate-content: two "independent" replicates whose result files are byte-identical,
- truncated-run: a log that stops mid-progress while its siblings finished,
- setting-outlier: a launch setting (Hydra override / --flag) that differs from the value every sibling used.
Findings are leads with evidence, never verdicts: the agent reads the cited files before reporting them.
"""
from __future__ import annotations

import json
import posixpath
import re
from collections import Counter, defaultdict

from .analyze import page, result
from .index import fid_range
from .navigate import _exists

DIGITS = re.compile(r"\d+")
DONE = re.compile(r"(model saved|saved (?:checkpoint|model)|max_epochs?\S*\s*(?:=\S+\s*)?reached|training (?:complete|finished|done)|"
                   r"trainer\.fit\(\) returned|finished training|\bfinished\b|\bcompleted?\b|exit(?:ed)? (?:with )?(?:code|status) 0|\bdone\b)", re.I)
STEP = re.compile(r"(?:step|iter(?:ation)?)\s*[:=]?\s*(\d+)\s*/\s*(\d+)", re.I)
EPOCH = re.compile(r"epoch\s*[:=\[]?\s*(\d+)\s*/\s*(\d+)", re.I)
SEEDISH = re.compile(r"(^|[._-])(seed|train_seed|eval_seed|run|name|id|output|out|dir|path|log|save|ckpt|checkpoint|resume|wandb|tag|host|gpu|port|rank|time|date)", re.I)


def _template(path: str) -> str:
    return DIGITS.sub("#", path)


def _groups(con, like, roles):
    q = f"SELECT path, sha, size, role FROM files WHERE path LIKE ? AND role IN ({','.join('?' * len(roles))})"
    groups = defaultdict(list)
    for r in con.execute(q, (like, *roles)):
        groups[_template(r["path"])].append(dict(r))
    return {k: v for k, v in groups.items() if len(v) >= 2}


def _end_state(facts: dict) -> dict:
    tail = " \n ".join((facts.get("progress") or {}).get("tail") or [])
    done = bool(DONE.search(tail))
    step = epoch = None
    for m in STEP.finditer(tail):
        step = (int(m.group(1)), int(m.group(2)))
    for m in EPOCH.finditer(tail):
        epoch = (int(m.group(1)), int(m.group(2)))
    stopped = (step and step[0] < step[1]) or False
    return {"done_marker": done, "last_step": step, "last_epoch": epoch, "stopped_mid_progress": bool(stopped) and not done,
            "tail": (facts.get("progress") or {}).get("tail", [])[-2:]}


def audit(con, scope: str | None = None, offset: int = 0, limit: int = 40) -> dict:
    like = f"{scope.rstrip('/')}/%" if scope else "%"
    findings = []

    # 1. identical content across replicates
    for tpl, members in _groups(con, like, ("result", "result_table", "data", "other_text")).items():
        if len(members) < 3:
            continue
        by_sha = defaultdict(list)
        for m in members:
            if m["sha"] and (m["size"] or 0) >= 200:
                by_sha[m["sha"]].append(m["path"])
        for sha, paths in by_sha.items():
            if 1 < len(paths) < len(members):  # some replicates share bytes, others do not: a copy, not a constant file
                findings.append({"kind": "identical-replicate-content", "files": sorted(paths), "group": tpl,
                                 "evidence": f"{len(paths)} of {len(members)} files that should be independent replicates are byte-identical "
                                             f"(sha256 {sha[:12]}…)", "confidence": "high"})

    # 2. truncated runs and 3. setting outliers, both among sibling logs/launchers
    for tpl, members in _groups(con, like, ("log", "launcher", "other_text")).items():
        facts = {}
        for m in members:
            row = con.execute("SELECT json FROM facts WHERE path = ?", (m["path"],)).fetchone()
            facts[m["path"]] = json.loads(row[0]) if row else {}
        ends = {p: _end_state(f) for p, f in facts.items() if f.get("progress")}
        if len(ends) >= 2:
            finished = [p for p, e in ends.items() if e["done_marker"] or (e["last_step"] and e["last_step"][0] == e["last_step"][1])]
            for p, e in ends.items():
                if e["stopped_mid_progress"] and len(finished) >= max(1, (len(ends) - 1) // 2):
                    findings.append({"kind": "truncated-run", "files": [p], "group": tpl,
                                     "evidence": f"log ends at {'step %d/%d' % e['last_step'] if e['last_step'] else 'mid-run'} with no completion "
                                                 f"marker, while {len(finished)} of {len(ends) - 1} sibling logs finished",
                                     "tail": e["tail"], "siblings_finished": finished[:3], "confidence": "high"})
        args = {p: f.get("launch_args") or {} for p, f in facts.items() if f.get("launch_args")}
        if len(args) >= 3:
            keys = Counter(k for a in args.values() for k in a)
            for k, n in keys.items():
                if n < 3 or SEEDISH.search(k):
                    continue
                vals = Counter(a[k] for a in args.values() if k in a)
                if len(vals) != 2:
                    continue
                (major, mc), (minor, nc) = vals.most_common()
                if nc == 1 and mc >= 2 and "/" not in str(minor) and "/" not in str(major):
                    odd = [p for p, a in args.items() if a.get(k) == minor]
                    findings.append({"kind": "setting-outlier", "files": odd, "group": tpl, "setting": k,
                                     "evidence": f"{k}={minor} here, while {mc} sibling runs use {k}={major}",
                                     "siblings": [p for p, a in args.items() if a.get(k) == major][:3], "confidence": "medium"})
    rng = fid_range(con, scope) if scope else (1, 1 << 62)
    rng = rng or (0, -1)

    # 4. structured files citing files that do not exist (a per-run JSON listed in a CSV, a probe file in a manifest)
    seen = set()
    for r in con.execute("SELECT f.path AS src, t.raw FROM refs_t t JOIN files f ON f.fid = t.src WHERE t.src BETWEEN ? AND ? "
                         "AND t.target IS NULL AND f.role IN ('result', 'result_table', 'manifest', 'data')", rng):
        raw = r["raw"].strip("`'\" ")
        if not re.search(r"\.(json|csv|jsonl|txt|log|pt|pth|ckpt|npz|npy|yaml|md)$", raw) or any(ch in raw for ch in "*{<$"):
            continue
        tail = raw.lstrip("./")
        parts = tail.split("/")
        # resolve against the citing file's folder and every ancestor, then by trailing path components
        d0, found = posixpath.dirname(r["src"]), False
        while True:
            if _exists(con, posixpath.normpath(posixpath.join(d0, tail)) if d0 else tail):
                found = True
                break
            if not d0:
                break
            d0 = posixpath.dirname(d0)
        if found:
            continue
        if len(parts) >= 2 and con.execute("SELECT 1 FROM files WHERE path LIKE ? LIMIT 1", ("%/" + "/".join(parts[-2:]),)).fetchone():
            continue
        if re.search(r"\.(pt|pth|ckpt|npz|npy|safetensors|bin|h5)$", raw):
            continue  # weights and arrays are routinely left out of archives on purpose
        # Only "one member of a set is missing": the cited folder exists and holds siblings with the same name pattern.
        d0, hit = posixpath.dirname(r["src"]), None
        while hit is None:
            cand_dir = posixpath.normpath(posixpath.join(d0, posixpath.dirname(tail))) if d0 else posixpath.dirname(tail)
            if cand_dir and cand_dir != "." and _exists(con, cand_dir):
                hit = cand_dir
            if not d0:
                break
            d0 = posixpath.dirname(d0)
        if not hit:
            # absolute paths from the machine that wrote the file: match the cited folder by its trailing components
            dparts = [x for x in posixpath.dirname(tail).split("/") if x]
            for k in range(min(len(dparts), 6), 1, -1):
                suffix = "/".join(dparts[-k:])
                rows = con.execute("SELECT DISTINCT dir FROM files WHERE fid BETWEEN ? AND ? AND (dir = ? OR dir LIKE ?) LIMIT 3",
                                   (*rng, suffix, "%/" + suffix)).fetchall()
                if len(rows) == 1:
                    hit = rows[0][0]
                    break
        if not hit:
            continue
        tpl = _template(posixpath.basename(tail))
        sibs = [x for (x,) in con.execute("SELECT path FROM files WHERE dir = ?", (hit,)) if _template(posixpath.basename(x)) == tpl]
        if len(sibs) < 2:
            continue
        key = (r["src"], tail)
        if key not in seen and len(seen) < 40:
            seen.add(key)
            findings.append({"kind": "referenced-file-missing", "files": [r["src"]], "missing": posixpath.join(hit, posixpath.basename(tail)),
                             "evidence": f"{r['src']} cites {raw}; {hit}/ holds {len(sibs)} siblings of the same pattern but not this one",
                             "confidence": "high"})

    # 5. an aggregate stored next to its parts that is not their mean (macro vs per-task, mean vs per-seed)
    groups = defaultdict(lambda: defaultdict(dict))
    for r in con.execute("SELECT f.path, m.locator, m.value FROM metrics_t m JOIN files f ON f.fid = m.fid "
                         "WHERE m.fid BETWEEN ? AND ? AND f.role IN ('result', 'result_table')", rng):
        loc = r["locator"]
        m = re.match(r"^(.*?)\.(macro|mean|avg|average|macro_mean|mean_sr|overall)(?:\[0\])?$", loc, re.I)
        if m:
            groups[(r["path"], m.group(1))]["agg"][loc] = r["value"]
            continue
        m = re.match(r"^(.*?)\.(tasks|per_task|task_means|per_seed_macro|macro_by_train_seed|seeds|per_seed)\.([^.\[\]]+)$", loc, re.I)
        if m:
            groups[(r["path"], m.group(1))]["parts"][m.group(3)] = r["value"]
    for (path, obj), g in groups.items():
        parts = list(g["parts"].values())
        if len(parts) < 2 or not g["agg"]:
            continue
        mean = sum(parts) / len(parts)
        for loc, val in g["agg"].items():
            if abs(val - mean) > max(0.02, 0.0015 * abs(mean)) and abs(val * 100 - mean) > 0.02 and abs(val - mean * 100) > 0.02:
                findings.append({"kind": "aggregate-mismatch", "files": [path], "locator": loc,
                                 "evidence": f"{loc} = {val:.4g} but the mean of its {len(parts)} parts ({', '.join(sorted(g['parts']))}) is {mean:.4g}",
                                 "confidence": "high"})

    # 6. a value on a different scale from the rest of its column (a fraction among percentages)
    cols = defaultdict(list)
    for r in con.execute("SELECT f.path, m.locator, m.key, m.value FROM metrics_t m JOIN files f ON f.fid = m.fid "
                         "WHERE m.fid BETWEEN ? AND ? AND f.role = 'result_table' AND m.key LIKE 'table:%'", rng):
        cols[(r["path"], r["key"])].append((r["locator"], r["value"]))
    for (path, key), vals in cols.items():
        nums = [v for _, v in vals if v]
        if len(nums) < 4:
            continue
        med = sorted(abs(v) for v in nums)[len(nums) // 2]
        if med < 5:
            continue
        for loc, v in vals:
            if v and abs(v) * 50 < med and abs(v * 100 - med) < 0.6 * med:
                findings.append({"kind": "scale-outlier", "files": [path], "locator": loc,
                                 "evidence": f"{key[6:]} = {v:.4g} while the column's median is {med:.4g} (looks like a fraction among percentages)",
                                 "confidence": "high"})

    # 7. reports that print sample-SD and population-SD rows side by side (cheap when the scope is small)
    n_reports = con.execute("SELECT COUNT(*) FROM files WHERE fid BETWEEN ? AND ? AND role = 'report'", rng).fetchone()[0]
    if n_reports <= 2000:
        from .analyze import reconcile
        rec = reconcile(con, scope=scope, limit=1000)
        for d in rec.get("reports", {}).get("items", []):
            if d.get("mixed_sd_conventions"):
                findings.append({"kind": "mixed-sd-convention", "files": [d["report"]],
                                 "evidence": "; ".join(f"{k}: {', '.join(v)}" for k, v in d["mixed_sd_conventions"].items()),
                                 "confidence": "medium"})
    order = {"identical-replicate-content": 0, "truncated-run": 1, "setting-outlier": 2, "aggregate-mismatch": 3,
             "scale-outlier": 4, "mixed-sd-convention": 5, "referenced-file-missing": 6}
    findings.sort(key=lambda f: (order.get(f["kind"], 9), f["files"][0]))
    return result("found" if findings else "not_found", con, scope=scope, by_kind=dict(Counter(f["kind"] for f in findings)),
                  findings=page(findings, offset, limit),
                  limitations=["replicates are recognised by paths that differ only in numbers; differently named variants are not compared",
                               "launch settings come from command lines echoed in logs/launch scripts (probe v7); older indexes have none",
                               "a lead, not a verdict: read the cited files (and the authors' notes) before reporting"])
