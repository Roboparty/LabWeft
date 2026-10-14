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
KILLED = re.compile(r"(SIGTERM|SIGKILL|death signal|\bKilled\b|Terminated|CUDA out of memory|OutOfMemoryError|Traceback \(most recent call last\)|"
                    r"Segmentation fault|core dumped|exitcode\s*:\s*-?[1-9]|DUE TO TIME LIMIT|CANCELLED)", re.I)
SEED_LINE = re.compile(r"(?<![_\w])(?:global[ _])?seed(?: set to|\s*[:=])\s*(\d+)", re.I)
PATH_SEED = re.compile(r"(?:^|[_/.-])(?:s|seed|train|train_seed|rs)(\d{1,6})(?=$|[_/.-])", re.I)
INPUT_LIKE = re.compile(r"(normali[sz]|norm_stats|statistic|stats|mean_std|vocab|split|config|hparams|args|params|meta|schema|requirements|env|"
                        r"manifest|subset|dataset|index|episodes?_ids?)", re.I)
PCT_COL = re.compile(r"(sr|success|rate|acc|accuracy|score|pct|percent|macro|mean|avg|average|top\d)", re.I)
COUNT_COL = re.compile(r"(^n_|_n$|count|num_|^num|only_|both|neither|episode|_id$|^id$|row|index|step|epoch|seed|size|seconds|time)", re.I)
REPLICATE_SEG = re.compile(r"(?:^|[_.-])(?:s|seed|train|eval|rep|run|trial|fold|r)\d+(?=$|[_.-])", re.I)
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
    killed = KILLED.search(tail)
    return {"done_marker": done, "last_step": step, "last_epoch": epoch,
            "stopped_mid_progress": (bool(stopped) or bool(killed)) and not done,
            "killed_by": killed.group(0) if killed and not done else None,
            "tail": (facts.get("progress") or {}).get("tail", [])[-2:]}


def audit(con, scope: str | None = None, offset: int = 0, limit: int = 40) -> dict:
    like = f"{scope.rstrip('/')}/%" if scope else "%"
    findings = []

    # 1. identical content across replicates
    for tpl, members in _groups(con, like, ("result", "result_table", "data", "other_text")).items():
        if len(members) < 3:
            continue
        if INPUT_LIKE.search(posixpath.basename(tpl)):
            continue  # dataset statistics / configs are legitimately identical across seeds
        by_sha = defaultdict(list)
        for m in members:
            if m["sha"] and (m["size"] or 0) >= 200:
                by_sha[m["sha"]].append(m["path"])
        for sha, paths in by_sha.items():
            if 1 < len(paths) < len(members):  # some replicates share bytes, others do not: a copy, not a constant file
                # mirrors of one run kept on two hosts (H20-1 vs H20-2) are copies by design: the paths must differ in a
                # replicate segment (seed / train / eval / run number) for identical bytes to be suspicious
                segs = [p.split("/") for p in paths]
                diff = {i for i in range(min(map(len, segs))) if len({sg[i] for sg in segs}) > 1}
                if not any(REPLICATE_SEG.search(sg[i]) for sg in segs for i in diff):
                    continue
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
                    where = 'step %d/%d' % e['last_step'] if e['last_step'] else 'mid-run'
                    why = f" after `{e['killed_by']}`" if e.get("killed_by") else ""
                    findings.append({"kind": "truncated-run", "files": [p], "group": tpl,
                                     "evidence": f"log ends at {where}{why} with no completion "
                                                 f"marker, while {len(finished)} of {len(ends) - 1} sibling logs finished",
                                     "tail": e["tail"], "siblings_finished": finished[:3], "confidence": "high"})
        # the seed a run really used (echoed by the framework) vs the seed its folder/name claims
        recorded = {}
        for p, f in facts.items():
            text = "\n".join((f.get("head") or []) + ((f.get("progress") or {}).get("tail") or []))
            got = {int(x) for x in SEED_LINE.findall(text)}
            claim = [int(x) for x in PATH_SEED.findall(posixpath.dirname(p))]
            if got and claim:
                # every number in the run's folder names counts (train AND eval seeds are both legitimate)
                nums = {int(x) for x in DIGITS.findall("/".join(posixpath.dirname(p).split("/")[-3:]))}
                recorded[p] = (claim[-1], got, nums)
        agree = [p for p, (c, g, n) in recorded.items() if g & n]
        claimed = {c for c, _, _ in recorded.values()}
        if len(agree) >= 2:
            for p, (c, g, n) in recorded.items():
                if not (g & n) and (g & claimed):
                    findings.append({"kind": "seed-mismatch", "files": [p], "group": tpl,
                                     "evidence": f"the run is labelled seed {c} (path) but its log records seed {sorted(g)}, the seed of a "
                                                 f"sibling run; {len(agree)} sibling runs record the seed their label claims",
                                     "confidence": "high"})
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
        # only percentage-like metric columns: success/accuracy/score/macro/mean values in 0..100
        if med < 5 or max(nums) > 100.0001 or min(nums) < 0 or not PCT_COL.search(key[6:]) or COUNT_COL.search(key[6:]):
            continue
        for loc, v in vals:
            if v and 0 < v <= 1 and abs(v) * 50 < med and abs(v * 100 - med) < 0.6 * med:
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
    findings += _value_outliers(con, like)
    findings += _checksum_lists(con, rng)
    # 8./9. mean ± SD pairs printed in reports, compared across documents
    findings += _report_pairs(con, rng)
    findings += _row_counts(con, rng)
    order = {"identical-replicate-content": 0, "truncated-run": 1, "setting-outlier": 2, "aggregate-mismatch": 3,
             "scale-outlier": 4, "mixed-sd-convention": 5, "referenced-file-missing": 6, "report-number-disagrees": 7,
             "cites-flagged-study": 8, "table-row-count-mismatch": 9, "seed-mismatch": 1, "result-setting-outlier": 2,
             "duplicate-checksum": 3}
    findings.sort(key=lambda f: (order.get(f["kind"], 9), f["files"][0]))
    return result("found" if findings else "not_found", con, scope=scope, by_kind=dict(Counter(f["kind"] for f in findings)),
                  findings=page(findings, offset, limit),
                  limitations=["replicates are recognised by paths that differ only in numbers; differently named variants are not compared",
                               "launch settings come from command lines echoed in logs/launch scripts (probe v7); older indexes have none",
                               "a lead, not a verdict: read the cited files (and the authors' notes) before reporting"])


def _report_pairs(con, rng) -> list[dict]:
    """8. cites-flagged-study: a report outside any flagged folder prints mean ± SD pairs that exist only in a folder
    the authors flagged (incomplete / do_not_use / superseded).
    9. report-number-disagrees: a report prints `x ± s` where a sibling document in the same folder prints `y ± s`
    for (evidently) the same quantity, y is backed by stored data and x is backed by nothing."""
    from .analyze import ISO_TIME, PM
    from .navigate import PATH_FLAG, TEXT_FLAG
    if not rng:
        return []
    occ = defaultdict(list)  # "x±s" -> [(path, line, text)]
    by_sd = defaultdict(list)  # (dir, s) -> [(x, path, line, text)]
    rows = con.execute("SELECT f.path, l.line, l.text FROM lines_t l JOIN files f ON f.fid = l.fid WHERE l.fid BETWEEN ? AND ? "
                       "AND l.kind = 'numbers' AND f.role = 'report'", rng).fetchall()
    for path, line, text in rows:
        text = ISO_TIME.sub(" ", text)
        for m in PM.finditer(text):
            a, b = m.group(1), m.group(2)
            if "." not in a or "." not in b:
                continue
            occ[f"{a}±{b}"].append((path, line, text))
            by_sd[(posixpath.dirname(path), b)].append((a, path, line, text))
    flagged = lambda p: any(PATH_FLAG.search(c) for c in p.split("/")[:-1])
    out = []
    # 8: flagged folders may print the pair as `x ± s` or as two adjacent table cells `| x | s |`
    from .analyze import NUM_TOKEN
    flagged_pairs = defaultdict(set)
    clean_pairs = defaultdict(set)
    for path, line, text in rows:
        toks = NUM_TOKEN.findall(ISO_TIME.sub(" ", text))
        target = flagged_pairs if flagged(path) else clean_pairs
        for i in range(len(toks) - 1):
            target[f"{toks[i]}±{toks[i + 1]}"].add(path)
    cited = defaultdict(list)
    for key, places in occ.items():
        for path, line, text in places:
            if flagged(path) or key not in flagged_pairs:
                continue
            if clean_pairs.get(key, set()) - {path}:
                continue  # also printed by another unflagged document: not uniquely from the flagged study
            if TEXT_FLAG.search(text) or PATH_FLAG.search(text):
                continue  # the line itself says the value is from the flagged study: a documented caveat
            cited[path].append({"line": line, "pair": key, "flagged_source": sorted(flagged_pairs[key])[0]})
    for path, items in cited.items():
        lines = sorted({i["line"] for i in items})
        out.append({"kind": "cites-flagged-study", "files": [path, items[0]["flagged_source"]],
                    "locator": f"line{'s' if len(lines) > 1 else ''} {', '.join(map(str, lines[:8]))}",
                    "evidence": f"{len(items)} mean ± SD value(s) ({', '.join(i['pair'] for i in items[:4])}) appear elsewhere only under the "
                                f"flagged folder {posixpath.dirname(items[0]['flagged_source'])}",
                    "confidence": "high" if len(items) >= 2 else "medium"})

    # 9
    def backed(x: float, dec: int, path: str) -> bool:
        # stored data in the report's own study (top two folders): a match anywhere in a big tree is a coincidence
        area = fid_range(con, "/".join(path.split("/")[:2])) if path.count("/") >= 2 else fid_range(con, path.split("/")[0])
        area = area or rng
        tol = 0.5 * 10 ** (-dec) + 1e-9
        for scale in (1.0, 0.01):
            if con.execute("SELECT 1 FROM metrics_t WHERE fid BETWEEN ? AND ? AND value BETWEEN ? AND ? LIMIT 1",
                           (area[0], area[1], x * scale - tol * scale, x * scale + tol * scale)).fetchone():
                return True
        return False
    seen = set()
    for (d, sd), items in by_sd.items():
        means = {a for a, *_ in items}
        if len(means) < 2 or len(items) > 12:
            continue
        for a, path, line, text in items:
            if len(occ[f"{a}±{sd}"]) > 1 or flagged(path):
                continue  # printed identically elsewhere: not an isolated edit
            dec = len(a.split(".")[1])
            others = [(b, p, l) for b, p, l, _ in items if b != a and p != path and len(occ[f"{b}±{sd}"]) >= 1
                      and abs(float(b) - float(a)) <= 0.25 * max(abs(float(a)), abs(float(b)), 1e-9)]
            if not others or backed(float(a), dec, path):
                continue
            good = [(b, p, l) for b, p, l in others if backed(float(b), dec, p)]
            if not good:
                continue
            b, p, l = good[0]
            if (path, line) in seen:
                continue
            seen.add((path, line))
            out.append({"kind": "report-number-disagrees", "files": [path, p], "locator": f"line {line}",
                        "evidence": f"prints {a} ± {sd}; {p}:{l} prints {b} ± {sd} (same SD) and {b} is in stored data, {a} is not",
                        "context": text.strip()[:200], "confidence": "high"})
    return out


def _row_counts(con, rng) -> list[dict]:
    """10. table-row-count-mismatch: a points/rows table holds fewer rows than the summary JSON it belongs to says it
    pooled (`alignment_x_points.csv` 10 rows vs `ALIGNMENT_X.json` pooled.n = 15); seed levels are compared with a
    sibling table of the same kind to name what is missing."""
    if not rng:
        return []
    tables = {}
    for path, js in con.execute("SELECT f.path, t.json FROM facts_t t JOIN files f ON f.fid = t.fid WHERE t.fid BETWEEN ? AND ? "
                                "AND f.ext IN ('.csv', '.tsv') AND f.path NOT LIKE '%::%'", rng):
        t = (json.loads(js) or {}).get("table") or {}
        if t.get("n_rows"):
            tables[path] = t
    by_dir = defaultdict(list)
    for p in tables:
        by_dir[posixpath.dirname(p)].append(p)
    out = []
    for d, paths in by_dir.items():
        jsons = [r[0] for r in con.execute("SELECT path FROM files WHERE dir = ? AND ext = '.json'", (d,))]
        for p in paths:
            stem = posixpath.splitext(posixpath.basename(p))[0].lower()
            owners = [j for j in jsons if len(posixpath.splitext(posixpath.basename(j))[0]) >= 6
                      and stem.startswith(posixpath.splitext(posixpath.basename(j))[0].lower()) and stem != posixpath.splitext(posixpath.basename(j))[0].lower()]
            n_rows = tables[p]["n_rows"]
            for j in owners:
                ns = [v for (v,) in con.execute("SELECT m.value FROM metrics_t m JOIN files f ON f.fid = m.fid WHERE f.path = ? "
                                                "AND (m.key LIKE '%.n' OR m.key = 'n' OR m.key LIKE '%n_points' OR m.key LIKE '%.n_rows')", (j,))]
                if not ns:
                    continue
                n, cnt = Counter(ns).most_common(1)[0]
                if n > n_rows and cnt >= 2:
                    ev = f"{p} has {n_rows} rows, while {j} reports n = {int(n)} ({cnt} statistics)"
                    seed_cols = tables[p].get("seed_cols") or []
                    for sc in seed_cols[:1]:
                        mine = {r.get(sc) for r in tables[p].get("rows", [])}
                        for q in paths:
                            if q != p and sc in (tables[q].get("seed_cols") or []) and tables[q]["n_rows"] == int(n):
                                theirs = {r.get(sc) for r in tables[q].get("rows", [])}
                                if mine < theirs:
                                    ev += f"; {q} ({int(n)} rows) has {sc} {sorted(theirs)}, this table only {sorted(mine)}"
                                    break
                    out.append({"kind": "table-row-count-mismatch", "files": [p, j], "evidence": ev, "confidence": "high"})
                    break
    return out


DATEISH = re.compile(r"20\d\d[-_]?\d\d[-_]?\d\d|\d\d:\d\d")


def _value_outliers(con, like) -> list[dict]:
    """Result files of replicate runs record their settings (checkpoint, policy, protocol). A string setting whose
    shape (digits ignored) differs from the one every sibling shares is a lead: e.g. one evaluation loaded
    `.../run_s3074/weights.pt` while all others loaded `.../run_s#_pbn16384/weights.pt`."""
    out = []
    for tpl, members in _groups(con, like, ("result",)).items():
        if len(members) < 4 or len(members) > 400:
            continue
        vals = defaultdict(dict)
        for m in members:
            for k, v in con.execute("SELECT c.key, c.value FROM config_t c JOIN files f ON f.fid = c.fid WHERE f.path = ? AND c.num IS NULL",
                                    (m["path"],)):
                if SEEDISH.search(k.rsplit(".", 1)[-1]) and not re.search(r"(checkpoint|ckpt|policy|model|weights)", k, re.I):
                    continue
                if not isinstance(v, str) or len(v) > 300 or re.search(r"(time|date|_at$|host|node|pid|uuid|hash|sha)", k, re.I):
                    continue
                vals[k][m["path"]] = DIGITS.sub("#", v)
        # paths a result file names (checkpoint, policy dir): same comparison on their digit-free shape
        refs = {}
        for m in members:
            refs[m["path"]] = {DIGITS.sub("#", r[0]): r[0] for r in con.execute(
                "SELECT t.raw FROM refs_t t JOIN files f ON f.fid = t.src WHERE f.path = ?", (m["path"],)) if "/" in r[0]}
        have = [p for p, r in refs.items() if r]
        if len(have) >= 4:
            count = Counter(t for p in have for t in refs[p])
            for p in have:
                missing = [t for t, n in count.items() if n == len(have) - 1 and t not in refs[p]]
                unique = [t for t in refs[p] if count[t] == 1]
                if missing and unique:
                    sib = next(q for q in have if missing[0] in refs[q])
                    out.append({"kind": "result-setting-outlier", "files": [p], "group": tpl, "setting": "referenced path",
                                "evidence": f"names {refs[p][unique[0]][-160:]} where all {len(have) - 1} siblings name the shape "
                                            f"{refs[sib][missing[0]][-160:]}", "siblings": [sib], "confidence": "medium"})
        for k, per in vals.items():
            if len(per) < 4:
                continue
            shapes = Counter(per.values())
            if len(shapes) != 2:
                continue
            (major, mc), (minor, nc) = shapes.most_common()
            if nc == 1 and mc >= 3:
                odd = next(p for p, v in per.items() if v == minor)
                raw = con.execute("SELECT c.value FROM config_t c JOIN files f ON f.fid = c.fid WHERE f.path = ? AND c.key = ?", (odd, k)).fetchone()[0]
                sib = next(p for p, v in per.items() if v == major)
                sraw = con.execute("SELECT c.value FROM config_t c JOIN files f ON f.fid = c.fid WHERE f.path = ? AND c.key = ?", (sib, k)).fetchone()[0]
                out.append({"kind": "result-setting-outlier", "files": [odd], "group": tpl, "setting": k,
                            "evidence": f"{k} = {raw[:160]} here, while {mc} sibling results record the shape {sraw[:160]}",
                            "siblings": [sib], "confidence": "medium"})
    return out


SUM_LINE = re.compile(r"^\s*(?:([0-9a-fA-F]{64})\s+\*?(\S.*?)|(\S.*?)\s+([0-9a-fA-F]{64}))\s*$")


def _checksum_lists(con, rng) -> list[dict]:
    """A checksum list (SHA256SUMS, *_sha.txt) giving two replicates (names differing only in digits) the same hash:
    either one entry was copied over the other or two 'independent' seeds are one file. Cross-checked against
    checksums recorded elsewhere (result files that store `checkpoint_sha256`)."""
    out = []
    for path, text in con.execute("SELECT f.path, t.text FROM texts_t t JOIN files f ON f.fid = t.fid WHERE t.fid BETWEEN ? AND ? "
                                  "AND (lower(f.path) LIKE '%sha%' OR lower(f.path) LIKE '%sum%' OR lower(f.path) LIKE '%checksum%')", rng):
        by_hash = defaultdict(list)
        for line in (text or "").splitlines():
            m = SUM_LINE.match(line)
            if m:
                h, name = (m.group(1), m.group(2)) if m.group(1) else (m.group(4), m.group(3))
                by_hash[h.lower()].append(name.strip())
        for h, names in by_hash.items():
            names = sorted(set(names))
            if len(names) < 2:
                continue
            tpls = {DIGITS.sub("#", n) for n in names}
            if len(tpls) == 1:
                other = []
                for n in names:
                    stem = posixpath.basename(n.rstrip("/"))
                    for (v,) in con.execute("SELECT c.value FROM config_t c JOIN tokens_t t ON t.fid = c.fid WHERE t.token = ? "
                                            "AND c.key LIKE '%sha256%' LIMIT 20", (stem,)):
                        vv = str(v).strip('"').lower()
                        if len(vv) == 64 and vv != h:
                            other.append(f"{stem}: {vv[:12]}…")
                out.append({"kind": "duplicate-checksum", "files": [path],
                            "evidence": f"{len(names)} replicate entries share sha256 {h[:12]}…: {', '.join(names[:4])}"
                                        + (f"; other files record a different hash for {', '.join(sorted(set(other))[:3])}" if other else ""),
                            "confidence": "high" if other else "medium"})
    return out
