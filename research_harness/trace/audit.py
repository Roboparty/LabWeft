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
VENDORED = re.compile(r"(^|/)(source|eval_source|third_party|vendor|external|site-packages|node_modules|upstream)(/|$)", re.I)
INFRA_KEY = re.compile(r"(workers|prefetch|pin_memory|num_threads|nproc|master|port|device|cuda_visible|world_size|local_rank|"
                       r"interval|log_every|print_freq|save_every|wandb|progress|cache|mmap|compile|tmp|scratch|root)", re.I)
INPUT_LIKE = re.compile(r"(normali[sz]|norm_stats|statistic|stats|mean_std|vocab|split|config|hparams|args|params|meta|schema|requirements|env|"
                        r"manifest|subset|dataset|index|episodes?_ids?|resolved|optimization|options|settings)", re.I)
PCT_COL = re.compile(r"(sr|success|rate|acc|accuracy|score|pct|percent|macro|mean|avg|average|top\d)", re.I)
# statistics of activations/geometry (mean_std, grad_norm, cos_mean) are not percentages even when named "mean"
NON_PCT_COL = re.compile(r"(std|var|norm|rank|cos|loss|entropy|grad|dist|sigma|eig|magnitude|scale|lr\b|logit|kl\b)", re.I)
TIME_SERIES_FILE = re.compile(r"(epoch|step|histor|curve|progress|trajector|train_log|training_log|learning)", re.I)
COUNT_COL = re.compile(r"(^n_|_n$|count|num_|^num|only_|both|neither|episode|_id$|^id$|row|index|step|epoch|seed|size|seconds|time)", re.I)
REPLICATE_SEG = re.compile(r"(?:^|[_.-])(?:s|seed|train|eval|rep|run|trial|fold|r)[_-]?\d+(?=$|[_.-])", re.I)
SEEDISH = re.compile(r"(^|[._-])(seed|train_seed|eval_seed|run|name|id|output|out|dir|path|log|save|ckpt|checkpoint|resume|wandb|tag|host|gpu|port|rank|time|date)", re.I)


def _template(path: str) -> str:
    return DIGITS.sub("#", path)


def _groups(con, like, roles):
    q = f"SELECT fid, path, sha, size, role FROM files WHERE path LIKE ? AND role IN ({','.join('?' * len(roles))})"
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
    for tpl, members in _groups(con, like, ("result", "result_table", "data", "other_text", "config", "report")).items():
        # eval wrappers classed as config, and per-run text outputs (seed42_n50.txt) classed as report, are results too
        members = [m for m in members if (m["role"] != "config" or m["path"].endswith(".json"))
                   and (m["role"] != "report" or re.search(r"(^|/)(results?|eval\w*|outputs?)/", m["path"]) and m["path"].endswith(".txt"))]
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
        got = {fid: j for fid, j in con.execute(f"SELECT fid, json FROM facts_t WHERE fid IN ({','.join('?' * len(members))})",
                                                 [m["fid"] for m in members])} if len(members) <= 30000 else None
        facts = {}
        for m in members:
            if got is None:
                row = con.execute("SELECT json FROM facts_t WHERE fid = ?", (m["fid"],)).fetchone()
                j = row[0] if row else None
            else:
                j = got.get(m["fid"])
            facts[m["path"]] = json.loads(j) if j else {}
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
                if n < 3 or SEEDISH.search(k) or INFRA_KEY.search(k):
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
    # suffix lookups (`LIKE '%/a/b'`) scan the whole index; on a 600k-file tree build in-memory tables once instead
    lookup = {}

    def tails2():
        if "t2" not in lookup:
            lookup["t2"] = {"/".join(x.split("/")[-2:]) for (x,) in con.execute("SELECT path FROM files")}
        return lookup["t2"]

    def dirs_ending(suffix):
        if "dirs" not in lookup:
            by_last = defaultdict(set)
            for (d,) in con.execute("SELECT DISTINCT dir FROM files WHERE fid BETWEEN ? AND ?", rng):
                if d:
                    by_last[d.rsplit("/", 1)[-1]].add(d)
            lookup["dirs"] = by_last
        last = suffix.rsplit("/", 1)[-1]
        return sorted(d for d in lookup["dirs"].get(last, ()) if d == suffix or d.endswith("/" + suffix))[:3]
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
        if len(parts) >= 2 and "/".join(parts[-2:]) in tails2():
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
                rows = dirs_ending(suffix)
                if len(rows) == 1:
                    hit = rows[0]
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
    # tens of millions of metric rows on a big tree: let SQLite keep only aggregate-like and part-like locators
    agg_like = " OR ".join(f"m.locator LIKE '%.{w}'" + f" OR m.locator LIKE '%.{w}[0]'"
                           for w in ("macro", "mean", "avg", "average", "macro_mean", "mean_sr", "overall"))
    part_like = " OR ".join(f"m.locator LIKE '%.{w}.%'"
                            for w in ("tasks", "per_task", "task_means", "per_seed_macro", "macro_by_train_seed", "seeds", "per_seed"))
    for r in con.execute("SELECT f.path, m.locator, m.value FROM metrics_t m JOIN files f ON f.fid = m.fid "
                         f"WHERE m.fid BETWEEN ? AND ? AND f.role IN ('result', 'result_table') AND ({agg_like} OR {part_like})", rng):
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
    # only columns that can hold the pattern (>= 4 non-zero values in 0..100, one of them in (0, 1], a percentage-like
    # name) are read back row by row; the rest are judged by SQLite aggregates
    pct_like = " OR ".join(f"m.key LIKE '%{w}%'" for w in ("sr", "success", "rate", "acc", "score", "pct", "percent", "macro",
                                                            "mean", "avg", "average", "top"))
    cand = con.execute("SELECT m.fid, m.key FROM metrics_t m JOIN files f ON f.fid = m.fid "
                       f"WHERE m.fid BETWEEN ? AND ? AND f.role = 'result_table' AND m.key LIKE 'table:%' AND ({pct_like}) "
                       "AND m.value IS NOT NULL AND m.value != 0 GROUP BY m.fid, m.key "
                       "HAVING COUNT(*) >= 4 AND MIN(m.value) >= 0 AND MAX(m.value) <= 100.0001 AND MAX(m.value) >= 5 "
                       "AND SUM(m.value > 0 AND m.value <= 1) >= 1", rng).fetchall()
    for fid, key in cand:
        if not PCT_COL.search(key[6:]) or COUNT_COL.search(key[6:]) or NON_PCT_COL.search(key[6:]):
            continue
        name = con.execute("SELECT path FROM files WHERE fid = ?", (fid,)).fetchone()[0].rsplit("/", 1)[-1]
        if TIME_SERIES_FILE.search(name):
            continue  # learning curves start low: epoch 0 at 0.1% is not a fraction among percentages
        for r in con.execute("SELECT f.path, m.locator, m.value FROM metrics_t m JOIN files f ON f.fid = m.fid "
                             "WHERE m.fid = ? AND m.key = ?", (fid, key)):
            cols[(r["path"], key)].append((r["locator"], r["value"]))
    for (path, key), vals in cols.items():
        nums = [v for _, v in vals if v]
        if len(nums) < 4:
            continue
        med = sorted(abs(v) for v in nums)[len(nums) // 2]
        # only percentage-like metric columns: success/accuracy/score/macro/mean values in 0..100
        if med < 5 or max(nums) > 100.0001 or min(nums) < 0 or not PCT_COL.search(key[6:]) or COUNT_COL.search(key[6:]):
            continue
        # success rates over N episodes come in steps of 100/N (300 episodes: 0.33): a small value on that grid is a
        # genuinely low percentage (0.67% = 2/300), a fraction of the median would not be on it
        grain = next((g for g in (1, 2, 3, 4, 5, 6, 8, 10, 20, 25)
                      if sum(abs(x * g - round(x * g)) < 0.02 for x in nums) >= 0.8 * len(nums)), None)
        for loc, v in vals:
            if grain and abs(v * grain - round(v * grain)) < 0.02:
                continue
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
            if d.get("mixed_sd_conventions") and not VENDORED.search(d["report"]):
                findings.append({"kind": "mixed-sd-convention", "files": [d["report"]],
                                 "evidence": "; ".join(f"{k}: {', '.join(v)}" for k, v in d["mixed_sd_conventions"].items()),
                                 "confidence": "medium"})
    findings += _stale_summaries(con, rng)
    findings += _checkpoint_consistency(con, rng)
    future, per_dir = _stamp_pass(con, rng)
    findings += future
    findings += _duplicate_rows(con, rng)
    findings += _table_arithmetic(con, rng)
    findings += _json_records(con, rng)
    findings += _missing_siblings(con, rng)
    findings += _declared_sizes(con, rng)
    findings += _event_order_from(per_dir)
    findings += _sibling_stamps(con, rng)
    findings += _declared_hashes(con, rng)
    findings += _summary_before_runs(con, rng)
    findings += _value_outliers(con, like)
    findings += _checksum_lists(con, rng)
    # 8./9. mean ± SD pairs printed in reports, compared across documents
    findings += _report_pairs(con, rng)
    findings += _row_counts(con, rng)
    # one file with several outlying settings (torch, torchvision, cuda...) is one finding
    merged, keep = {}, []
    for f in findings:
        if f["kind"] in ("result-setting-outlier", "record-outlier", "setting-outlier"):
            key = (f["kind"], f["files"][0])
            if key in merged:
                merged[key]["evidence"] += "; " + f["evidence"]
                continue
            merged[key] = f
        keep.append(f)
    findings = keep
    order = {"identical-replicate-content": 0, "truncated-run": 1, "setting-outlier": 2, "aggregate-mismatch": 3,
             "scale-outlier": 4, "mixed-sd-convention": 5, "referenced-file-missing": 6, "report-number-disagrees": 7,
             "cites-flagged-study": 8, "table-row-count-mismatch": 9, "seed-mismatch": 1, "result-setting-outlier": 2,
             "duplicate-checksum": 3, "summary-older-than-inputs": 4, "summary-predates-run": 4, "duplicated-table-row": 3, "declared-checksum-mismatch": 2,
             "checkpoint-mismatch": 2, "stamp-after-write": 4,
             "table-arithmetic": 3, "record-outlier": 2, "identity-mismatch": 1,
             "missing-in-replicate": 1, "declared-size-mismatch": 2, "event-order": 4,
             "stamp-disagrees-with-log": 4}
    findings.sort(key=lambda f: (order.get(f["kind"], 9), f["files"][0]))
    # what the rules above cannot judge: every report that prints numbers still needs a human-style check
    reports = [r[0] for r in con.execute(
        "SELECT f.path FROM files f WHERE f.fid BETWEEN ? AND ? AND f.role = 'report' AND f.ext IN ('.md', '.markdown', '.tex', '.html') "
        "AND f.path NOT LIKE '%::%' AND EXISTS (SELECT 1 FROM lines_t l WHERE l.fid = f.fid AND l.kind = 'numbers')", rng)]
    reports = [p for p in reports if not VENDORED.search(p)]
    flagged = {f["files"][0] for f in findings}
    manual = {"reports_with_numbers": len(reports), "without_any_automatic_lead": len([p for p in reports if p not in flagged]),
              "next": "these audit rules only catch known patterns; run `worklist` and check every report against its raw "
                      "files (most planted/real problems need arithmetic or cross-file reading)"}
    return result("found" if findings else "not_found", con, scope=scope, by_kind=dict(Counter(f["kind"] for f in findings)),
                  findings=page(findings, offset, limit), manual_review_still_needed=manual,
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
    for tpl, members in _groups(con, like, ("result", "config")).items():
        # evaluation wrappers are sometimes classed as config; real configs (yaml, hydra dumps) vary by design
        members = [m for m in members if "::" not in m["path"] and (m["role"] == "result" or m["path"].endswith(".json"))
                   and "/.hydra/" not in m["path"]]
        if len(members) < 3 or len(members) > 3000:
            continue
        vals = defaultdict(dict)
        raw_vals = defaultdict(dict)
        shape_reported = set()
        # one query per table for the whole group, not three per member
        fids = [m["fid"] for m in members]
        marks = ",".join("?" * len(fids))
        cfg_by, txt_by, refs_by = defaultdict(list), {}, defaultdict(list)
        for fid, k, v in con.execute(f"SELECT fid, key, value FROM config_t INDEXED BY config_fid WHERE fid IN ({marks}) AND num IS NULL", fids):
            cfg_by[fid].append((k, v))
        for fid, t in con.execute(f"SELECT fid, substr(text, 1, 20000) FROM texts_t WHERE fid IN ({marks})", fids):
            txt_by[fid] = t
        for fid, raw in con.execute(f"SELECT src, raw FROM refs_t WHERE src IN ({marks})", fids):
            refs_by[fid].append((raw,))
        for m in members:
            for k, v in cfg_by.get(m["fid"], ()):
                if SEEDISH.search(k.rsplit(".", 1)[-1]) and not re.search(r"(checkpoint|ckpt|policy|model|weights)", k, re.I):
                    continue
                if not isinstance(v, str) or len(v) > 300 or re.search(r"(time|date|_at$|host|node|pid|uuid|hash|sha)", k, re.I):
                    continue
                vals[k][m["path"]] = DIGITS.sub("#", v)
                if len(v) <= 40 and "/" not in v:
                    raw_vals[k][m["path"]] = v
            # version/protocol strings are often not kept as settings: read them from the JSON text
            t0 = txt_by.get(m["fid"])
            if t0 and t0.lstrip().startswith("{"):
                for vk, vv in _version_fields(t0):
                    raw_vals["text:" + vk][m["path"]] = vv
        # paths a result file names (checkpoint, policy dir): same comparison on their digit-free shape
        refs = {}
        for m in members:
            # shape of the last three components only: the same checkpoint relayed via /data vs /data2 is not an outlier
            refs[m["path"]] = {DIGITS.sub("#", "/".join(r[0].split("/")[-3:])): r[0] for r in refs_by.get(m["fid"], ()) if "/" in r[0]}
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
        for k, per in raw_vals.items():
            # short categorical settings (benchmark version, protocol, scorer) compared verbatim
            versionish = bool(re.search(r"(version|torch|cuda|cudnn|python|numpy|driver)", k, re.I))
            if len(per) < (3 if versionish else 4) or k in shape_reported:
                continue
            c = Counter(per.values())
            if len(c) == 2:
                (major, mc), (minor, nc) = c.most_common()
                if nc == 1 and mc >= (2 if versionish else 3):
                    odd = next(p for p, v in per.items() if v == minor)
                    shape_reported.add(k.removeprefix("text:"))
                    out.append({"kind": "result-setting-outlier", "files": [odd], "group": tpl, "setting": k,
                                "evidence": f"{k} = {minor} here, while all {mc} sibling results record {major}", "confidence": "high"})
        for k, per in vals.items():
            if len(per) < 4 or k in shape_reported:
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


JSON_STR_FIELD = re.compile(r'"([\w.]+)"\s*:\s*"([^"/]{1,40})"')
VERSION_KEY = re.compile(r"(version|protocol|scorer|benchmark|evaluator|manifest_version|torch|cuda|cudnn)", re.I)


def _version_fields(text: str) -> list:
    """Same pairs as VERSION_FIELD.findall, in linear time: match every string field, then test the key."""
    return [(k, v) for k, v in JSON_STR_FIELD.findall(text) if VERSION_KEY.search(k)]


VERSION_FIELD = re.compile(r'"([\w.]*(?:version|protocol|scorer|benchmark|evaluator|manifest_version|torch|cuda|cudnn)[\w.]*)"\s*:\s*"([^"/]{1,40})"', re.I)
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


SUMMARY_NAME = re.compile(r"(final|summary|results?|report|status|aggregate|table|overview|live)", re.I)
GEN_KEY = re.compile(r"(generated|created|written|built|updated)(_at|_time|_on)?$", re.I)
TS = re.compile(r"(20\d\d)-(\d\d)-(\d\d)[T ](\d\d):(\d\d)(?::(\d\d))?")


def _ts(value) -> float | None:
    import calendar
    m = TS.search(str(value))
    if not m:
        return None
    y, mo, d, h, mi, se = (int(x or 0) for x in m.groups())
    return calendar.timegm((y, mo, d, h, mi, se, 0, 0, 0))


def _stale_summaries(con, rng) -> list[dict]:
    """A summary/report that names its input files but was generated before some of them were last written: the
    numbers it prints may not include the final inputs (or the inputs were rewritten after the fact).
    Uses the summary's own `generated_at`-style field when present, else its file time; inputs use file times."""
    out = []
    rows = con.execute("SELECT DISTINCT r.src FROM refs_t r WHERE r.src BETWEEN ? AND ? AND r.target IS NOT NULL", rng).fetchall()
    for (src,) in rows:
        f = con.execute("SELECT path, mtime, role FROM files WHERE fid = ?", (src,)).fetchone()
        if not f or f["role"] not in ("report", "result", "result_table") or not SUMMARY_NAME.search(posixpath.basename(f["path"])):
            continue
        gen = None
        for k, v in con.execute("SELECT key, value FROM config_t WHERE fid = ?", (src,)):
            if GEN_KEY.search(k.rsplit(".", 1)[-1]):
                gen = _ts(v)
                if gen:
                    break
        if gen is None:
            row = con.execute("SELECT json FROM facts_t WHERE fid = ?", (src,)).fetchone()
            text = (json.loads(row[0]) or {}).get("text") if row else None
            m = re.search(r"(?:generated|created|updated)[^\n]{0,20}?(20\d\d-\d\d-\d\d[T ]\d\d:\d\d(?::\d\d)?)", text or "", re.I)
            gen = _ts(m.group(1)) - 8 * 3600 if m else None  # report times are local (UTC+8 here); file times are UTC
        if not gen:
            continue  # file times alone are too noisy (copies, re-syncs); require the summary's own generation stamp
        when = gen
        late = []
        for (tpath, tm) in con.execute("SELECT f2.path, f2.mtime FROM refs_t r JOIN files f2 ON f2.path = r.target "
                                        "WHERE r.src = ? AND f2.role IN ('result', 'result_table', 'log')", (src,)):
            if tm and tm - when > 30 * 60:
                late.append((tpath, tm))
        if late and len(late) <= 20:
            import datetime
            fmt = lambda t: datetime.datetime.utcfromtimestamp(t).strftime("%Y-%m-%d %H:%M UTC")
            out.append({"kind": "summary-older-than-inputs", "files": [f["path"]] + [p for p, _ in late[:3]],
                        "evidence": f"{'generated' if gen else 'last written'} {fmt(when)}, but {len(late)} file(s) it names were written "
                                    f"later (e.g. {late[0][0]} at {fmt(late[0][1])})",
                        "confidence": "medium" if gen else "low"})
    return out


STAMP_IN_TEXT = re.compile(r'"?(?:generated(?:_at)?|created_at|updated_at|finished_at|completed_at|end(?:ed)?_at|end_time)"?\s*[:=]?\s*"?'
                           r'(20\d\d-\d\d-\d\d[T ]\d\d:\d\d(?::\d\d)?(?:\.\d+)?(?:[+-]\d\d:?\d\d|Z)?)', re.I)
RUN_TOKEN = re.compile(r"^[a-z0-9]+(?:_[a-z0-9.]+){2,}$", re.I)


def _stamp(text: str, first: bool = True):
    import datetime
    vals = []
    for m in STAMP_IN_TEXT.finditer(text or ""):
        raw = m.group(1).replace(" ", "T").replace("Z", "+00:00")
        try:
            d = datetime.datetime.fromisoformat(raw)
        except ValueError:
            continue
        vals.append(d.timestamp() if d.tzinfo else d.replace(tzinfo=datetime.timezone(datetime.timedelta(hours=8))).timestamp())
        if first:
            break
    return (vals[0] if first else max(vals)) if vals else None


def _summary_before_runs(con, rng) -> list[dict]:
    """A summary stamped `generated_at T` that names runs (by id) whose own results were finished after T: either the
    summary was regenerated without updating its stamp, or it reports numbers that did not exist yet."""
    out = []
    # pick summaries by name first; reading every result text of a big tree just to test its name dominated the audit
    cands = [(fid, path) for fid, path in con.execute("SELECT fid, path FROM files WHERE fid BETWEEN ? AND ? "
                                                      "AND role IN ('result', 'result_table', 'report')", rng)
             if SUMMARY_NAME.search(posixpath.basename(path)) and not re.search(r"(preview|draft|interim|partial|wip|tmp)", path, re.I)]
    run_files = {}
    for fid, path in cands:  # an interim summary is expected to predate later runs
        row = con.execute("SELECT text FROM texts_t WHERE fid = ?", (fid,)).fetchone()
        text = row[0] if row else None
        m = re.search(r'(generated(?:_at)?|Generated)\W{0,4}(20\d\d-\d\d-\d\d[T ]\d\d:\d\d)', text or "")
        if not m:
            continue
        gen = _stamp(m.group(0))
        if not gen:
            continue
        study = "/".join(path.split("/")[:2])
        srng = fid_range(con, study)
        if not srng:
            continue
        own = set(path.lower().split("/"))
        runs = {t for (t,) in con.execute("SELECT token FROM tokens_t WHERE fid = ?", (fid,))
                if RUN_TOKEN.match(t) and any(ch.isdigit() for ch in t) and t.lower() not in own}
        late = []
        if study not in run_files:  # result files of the study by the run folders above them (one scan per study)
            by_run = defaultdict(list)
            for rfid, rpath in con.execute("SELECT fid, path FROM files WHERE fid BETWEEN ? AND ? AND role = 'result'", srng):
                for comp in set(rpath.split("/")[-4:-1]):  # the run's own folder, not a study-level file below a matching name
                    by_run[comp].append((rfid, rpath))
            run_files[study] = by_run
        for run in list(runs)[:300]:
            for rfid, rpath in run_files[study].get(run, ()):
                row = con.execute("SELECT text FROM texts_t WHERE fid = ?", (rfid,)).fetchone()
                rtext = row[0] if row else None
                if rtext is None:
                    continue
                done = _stamp(rtext, first=False)
                if done and done - gen > 10 * 60:
                    late.append((rpath, done))
        if late:
            import datetime
            fmt = lambda t: datetime.datetime.fromtimestamp(t, datetime.timezone(datetime.timedelta(hours=8))).strftime("%Y-%m-%d %H:%M (+08)")
            late.sort(key=lambda x: -x[1])
            out.append({"kind": "summary-predates-run", "files": [path] + [p for p, _ in late[:3]],
                        "evidence": f"stamped {fmt(gen)}, but {len(late)} result file(s) of runs it names finished later "
                                    f"(latest {late[0][0]} at {fmt(late[0][1])})", "confidence": "medium"})
    return out


ROW_NUM = re.compile(r"[-+]?\d+\.\d+")


def _duplicate_rows(con, rng) -> list[dict]:
    """Two rows of one markdown table with different labels but identical numbers (>= 3 decimals each): the classic
    copy-paste error when a table is edited by hand."""
    out = []
    for path, text in con.execute("SELECT f.path, t.text FROM texts_t t JOIN files f ON f.fid = t.fid WHERE t.fid BETWEEN ? AND ? "
                                  "AND f.role = 'report' AND f.ext IN ('.md', '.markdown')", rng):
        block = []
        for n, line in enumerate((text or "").splitlines() + [""], 1):
            if line.strip().startswith("|"):
                block.append((n, line))
                continue
            if len(block) >= 3:
                seen = {}
                for ln, row in block:
                    cells = [c.strip(" *`") for c in row.strip().strip("|").split("|")]
                    # the first cell is the row label even when it holds a number ("VISReg-z (4.5)")
                    nums = tuple(x for c in cells[1:] for x in ROW_NUM.findall(c))
                    label = " | ".join([cells[0]] + [c for c in cells[1:] if c and not ROW_NUM.search(c)])[:80]
                    informative = [x for x in nums if float(x) not in (0.0, 1.0, 100.0)]
                    if len(nums) >= 4 and len(set(informative)) >= 3:
                        if nums in seen and seen[nums][1] != label:
                            if abs(ln - seen[nums][0]) > 40:
                                continue  # far apart: probably two tables quoting the same result
                            out.append({"kind": "duplicated-table-row", "files": [path], "locator": f"lines {seen[nums][0]} and {ln}",
                                        "evidence": f"rows '{seen[nums][1]}' and '{label}' carry identical numbers ({', '.join(nums[:5])}...)",
                                        "confidence": "high" if len(nums) >= 5 else "medium"})
                        seen.setdefault(nums, (ln, label))
            block = []
    return out


HASH64 = re.compile(r"\b[0-9a-f]{64}\b")
FNAME = re.compile(r"[\w./-]+\.(?:json|csv|md|txt|yaml|yml|py|log|tsv|jsonl|pdf|png|html|tex|sh|npz|npy|pt|pth|ckpt|tar|gz|zip|env|toml|cfg|ini)\b")


def _declared_hashes(con, rng) -> list[dict]:
    """A document or manifest states `<file> ... <sha256>`; the indexed file has a different sha256 (edited after the
    audit, or the audit was copied from elsewhere). Only files the probe hashed are compared."""
    out, seen, bad = [], set(), {}
    for path, text in con.execute("SELECT f.path, t.text FROM texts_t t JOIN files f ON f.fid = t.fid WHERE t.fid BETWEEN ? AND ? "
                                  "AND f.role IN ('report', 'manifest', 'result', 'other_text')", rng):
        if not text or "sha" not in text.lower():
            continue
        base = posixpath.dirname(path)
        lines = text.splitlines()
        for i, line in enumerate(lines):
            hs = HASH64.findall(line.lower())
            if len(hs) != 1:
                continue
            names = FNAME.findall(line)
            if not names and i and HASH64.sub("", line.lower()).strip(" \t\"',:-|`") == "":
                names = FNAME.findall(lines[i - 1])  # a hash alone on its line belongs to the file named just above
            for nm in names[:2]:
                nm = nm.strip("./") if not nm.startswith("../") else nm
                cands = [posixpath.normpath(posixpath.join(base, nm)), posixpath.normpath(posixpath.join(posixpath.dirname(base), nm)), nm]
                row = None
                for c in cands:
                    row = con.execute("SELECT path, sha FROM files WHERE path = ?", (c,)).fetchone()
                    if row:
                        break
                if not row or not row[1] or row[0] == path:
                    continue
                key = (row[0], hs[0])
                if key in seen:
                    continue
                seen.add(key)
                if row[1] != hs[0]:
                    bad.setdefault(path, []).append((i + 1, row[0], hs[0], row[1]))
    for path, items in bad.items():
        ln, f, h, a = items[0]
        out.append({"kind": "declared-checksum-mismatch", "files": [f, path], "locator": f"{path} line {ln}",
                    "evidence": f"{path} declares sha256 {h[:12]}… for {f}, the file's sha256 is {a[:12]}…"
                                + (f"; {len(items) - 1} more listed file(s) differ ({', '.join(x[1] for x in items[1:4])})" if len(items) > 1 else ""),
                    "confidence": "high" if len(items) <= 3 else "medium"})
    return out


CKPT_SHA = re.compile(r'"(?:checkpoint_sha256|ckpt_sha256|weights_sha256|model_sha256)"\s*:\s*"([0-9a-f]{64})"', re.I)
CKPT_EPOCH = re.compile(r"(?:weights|checkpoint|ckpt|model)[_-]?(?:epoch|ep|e)[_-]?(\d+)\.(?:pt|pth|ckpt|safetensors|bin)", re.I)
PATH_EPOCH = re.compile(r"(?:^|/)epoch[_-]?(\d{1,4})(?=/)", re.I)


WEIGHT_EXT = re.compile(r"\.(?:pt|pth|ckpt|safetensors|bin)(?![\w])")
PATH_CHARS = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_./-")


def _weight_paths(text: str) -> list[str]:
    """`dir/x_epoch5.pt`-like paths in a text, in linear time (a `[\w./-]+\.pt` regex backtracks quadratically on the
    long tokens of big JSON files)."""
    out = []
    for m in WEIGHT_EXT.finditer(text):
        i, lo = m.start(), max(0, m.start() - 400)
        while i > lo and (text[i - 1] in PATH_CHARS or text[i - 1].isalnum()):
            i -= 1
        if i < m.start():
            out.append(text[i:m.end()])
    return out


def _checkpoint_consistency(con, rng) -> list[dict]:
    """Evaluations of one checkpoint (sibling files differing only in the eval seed) must record the same checkpoint
    hash, and an evaluation filed under `epoch_N/` must load `..._epoch_N.pt`."""
    out = []
    groups = defaultdict(list)
    seed_groups = defaultdict(list)
    label_groups = defaultdict(list)
    for path, text in con.execute("SELECT f.path, t.text FROM texts_t t JOIN files f ON f.fid = t.fid WHERE t.fid BETWEEN ? AND ? "
                                  "AND f.ext = '.json' AND f.path NOT LIKE '%::%' "
                                  "AND (instr(t.text, 'checkpoint') > 0 OR instr(t.text, 'weights') > 0)", rng):
        if not text:
            continue
        sha = CKPT_SHA.search(text) if "sha256" in text or "SHA256" in text else None
        found = _weight_paths(text)
        eps = {int(x) for c in found for x in CKPT_EPOCH.findall(c)}  # the pattern only matches inside such paths
        pe = PATH_EPOCH.findall(path)
        if pe and eps and int(pe[-1]) not in eps and len(eps) == 1:
            out.append({"kind": "checkpoint-mismatch", "files": [path],
                        "evidence": f"filed under epoch {pe[-1]} but loads checkpoint(s) of epoch {sorted(eps)}", "confidence": "high"})
        if sha:
            d, b = posixpath.split(path)
            groups[(d, DIGITS.sub("#", b))].append((path, sha.group(1)))
        files = [c for c in found if not c.endswith(".bin")]
        ck = [c for c in files if re.search(r"(?:weights|checkpoint|ckpt|model)[\w.-]*\.\w+$", c)]
        stems = {posixpath.splitext(posixpath.basename(c))[0] for c in files}
        if len(stems) == 1:
            label_groups[posixpath.dirname(path)].append((path, posixpath.splitext(posixpath.basename(path))[0], stems.pop()))
        if ck:
            seeds = {int(x) for c in ck for x in ID_TOKEN.findall("/".join(c.split("/")[-3:]))}
            if len(seeds) == 1:
                seed_groups[posixpath.dirname(path)].append((path, seeds.pop()))
    for d, items in label_groups.items():
        # probes/evals named after the checkpoint they evaluate (B_epoch5.json -> B_epoch5.ckpt)
        same = [p for p, own, ck in items if own == ck]
        if len(same) >= 2:
            for p, own, ck in items:
                if own != ck and any(o == ck for _, o, _ in items):
                    out.append({"kind": "checkpoint-mismatch", "files": [p],
                                "evidence": f"{posixpath.basename(p)} evaluates checkpoint {ck}, which belongs to its sibling {ck}.json; "
                                            f"{len(same)} sibling files evaluate the checkpoint they are named after", "confidence": "high"})
    for d, items in seed_groups.items():
        c = Counter(sd for _, sd in items)
        own = {int(x) for x in ID_TOKEN.findall("/".join(d.split("/")[-3:]))}
        if len(items) >= 3 and len(c) == 2:
            (major, mc), (minor, nc) = c.most_common()
            if nc == 1 and (not own or major in own):
                odd = next(p for p, sd in items if sd == minor)
                out.append({"kind": "checkpoint-mismatch", "files": [odd],
                            "evidence": f"loads the checkpoint of seed {minor}, while its {mc} sibling evaluations in {d} load seed {major}"
                                        + (f" (the folder is seed {sorted(own)})" if own else ""), "confidence": "high"})
    for (d, _), items in groups.items():
        c = Counter(h for _, h in items)
        if len(items) >= 3 and len(c) == 2:
            (major, mc), (minor, nc) = c.most_common()
            if nc == 1:
                odd = next(p for p, h in items if h == minor)
                out.append({"kind": "checkpoint-mismatch", "files": [odd],
                            "evidence": f"records checkpoint sha256 {minor[:12]}… while its {mc} sibling evaluations in {d} record {major[:12]}…",
                            "confidence": "high"})
    return out


EVENT_STAMP = re.compile(r"(?:completed|finished|ended|done|collected|end)(?:_at|_time)?\s*[=:]\s*\"?(20\d\d-\d\d-\d\dT\d\d:\d\d(?::\d\d)?(?:\.\d+)?(?:[+-]\d\d:?\d\d|Z))", re.I)


# One scan of the text table feeds both stamp checks (each full read of a large index costs about a minute).
STAMP_PASS_SQL = ("SELECT f.path, t.text, f.mtime, f.size FROM texts_t t JOIN files f ON f.fid = t.fid WHERE t.fid BETWEEN ? AND ? "
                  "AND f.path NOT LIKE '%::%' AND length(t.text) <= 200000 AND ("
                  "(f.size < 20000 AND length(t.text) < 80) OR t.text LIKE '%end%' OR t.text LIKE '%done%' OR t.text LIKE '%complet%' "
                  "OR t.text LIKE '%finish%' OR t.text LIKE '%collect%' OR t.text LIKE '%finali%' OR t.text LIKE '%archiv%' "
                  "OR t.text LIKE '%start%')")


def _stamp_pass(con, rng):
    future, per_dir = [], defaultdict(list)
    for path, text, mtime, size in con.execute(STAMP_PASS_SQL, rng):
        if not text:
            continue
        if mtime is not None:
            _future_row(path, text, mtime, future)
        if size is not None and size < 20000:
            _event_row(path, text, per_dir)
    return future, per_dir


def _future_stamps(con, rng) -> list[dict]:
    return _stamp_pass(con, rng)[0]


def _future_row(path, text, mtime, out) -> None:
    """A file states that something completed at time T, but the file itself was last written well before T: the
    stamp was edited (or the record was written before the event it reports)."""
    import datetime
    if True:
        for m in EVENT_STAMP.finditer(text):
            try:
                t = datetime.datetime.fromisoformat(m.group(1).replace("Z", "+00:00")).timestamp()
            except ValueError:
                continue
            if t - mtime > 30 * 60:
                when = datetime.datetime.fromtimestamp(mtime, datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
                out.append({"kind": "stamp-after-write", "files": [path],
                            "evidence": f"records `{m.group(0)[:60]}`, {int((t - mtime) / 60)} min after the file was last written ({when})",
                            "confidence": "medium"})
                break


AGG_COL = re.compile(r"^(macro|mean|avg|average|overall|all|4-task|3-task|four-task|平均|均值|宏平均)", re.I)
DELTA_COL = re.compile(r"(Δ|delta|diff|gain|change|improv|提升|变化|差)", re.I)
SKIP_COL = re.compile(r"(\b(sd|std|stdev|se|sem|ci|n|p|rank|lr|ms|sec|s)\b|^n_|count|seed|p-?value|#|time|epoch|params?|flips?|wins?|losses?)", re.I)
CELL_NUM = re.compile(r"[-+]?\d+(?:\.\d+)?")


def _cell(c):
    m = CELL_NUM.search(c.replace("−", "-"))
    if not m or re.search(r"[A-Za-z]{3,}", c.split(m.group(0))[0]):
        return None, 0
    v = m.group(0)
    return float(v), (len(v.split(".")[1]) if "." in v else 0)


def _table_arithmetic(con, rng) -> list[dict]:
    """Recompute what a markdown table claims about itself: an aggregate column (Macro / Mean) must be the mean of the
    per-task columns in its row, and a delta column must be the same difference (or relative change) of two columns in
    every row. The rule is learnt from the rows (it must hold for most of them); rows that break it are reported."""
    out = []
    for path, text in con.execute("SELECT f.path, t.text FROM texts_t t JOIN files f ON f.fid = t.fid WHERE t.fid BETWEEN ? AND ? "
                                  "AND f.role = 'report' AND f.ext IN ('.md', '.markdown')", rng):
        lines = (text or "").splitlines()
        i = 0
        while i < len(lines):
            if not (lines[i].strip().startswith("|") and i + 1 < len(lines) and re.match(r"^\s*\|?\s*:?-{2,}", lines[i + 1])):
                i += 1
                continue
            header = [c.strip(" *`") for c in lines[i].strip().strip("|").split("|")]
            rows, j = [], i + 2
            while j < len(lines) and lines[j].strip().startswith("|"):
                cells = [c.strip(" *`") for c in lines[j].strip().strip("|").split("|")]
                if len(cells) == len(header):
                    rows.append((j + 1, cells))
                j += 1
            i = j
            if len(rows) < 3 or len(header) < 3:
                continue
            vals = [[_cell(c) for c in cells] for _, cells in rows]
            numeric = [k for k in range(1, len(header)) if sum(1 for v in vals if v[k][0] is not None) >= len(rows) * 0.8]
            # 1. aggregate column = mean of the other value columns
            for a in [k for k in numeric if AGG_COL.search(header[k])]:
                parts = [k for k in numeric if k != a and not AGG_COL.search(header[k]) and not DELTA_COL.search(header[k])
                         and not SKIP_COL.search(header[k])]
                if len(parts) < 2:
                    continue
                ok, bad = 0, []
                for (ln, cells), v in zip(rows, vals):
                    xs = [v[k][0] for k in parts]
                    if v[a][0] is None or any(x is None for x in xs):
                        continue
                    tol = 0.5 * 10 ** (-max(v[a][1], 0)) + 0.5 * 10 ** (-min(v[k][1] for k in parts)) + 1e-9
                    if abs(sum(xs) / len(xs) - v[a][0]) <= tol:
                        ok += 1
                    else:
                        bad.append((ln, cells[0], v[a][0], sum(xs) / len(xs)))
                if bad and ok >= 2 * len(bad) and ok >= 3:
                    for ln, label, got, want in bad[:3]:
                        out.append({"kind": "table-arithmetic", "files": [path], "locator": f"line {ln}",
                                    "evidence": f"row '{label}': {header[a]} = {got:g}, but the mean of {', '.join(header[k] for k in parts)} "
                                                f"is {want:.2f} (it holds in {ok} other rows)", "confidence": "high"})
            # 1b. aggregate ROW (Mean / Macro / Average) = mean of the rows above it, column by column
            body = [(ln, cells, v) for (ln, cells), v in zip(rows, vals) if not AGG_COL.search(cells[0])]
            for (ln, cells), v in zip(rows, vals):
                if not AGG_COL.search(cells[0]) or len(body) < 2 or re.search(r"(total|sum|合计|总)", cells[0], re.I):
                    continue
                ok, bad = 0, []
                for k in numeric:
                    if SKIP_COL.search(header[k]) or v[k][0] is None:
                        continue
                    xs = [b[2][k][0] for b in body if b[2][k][0] is not None]
                    if len(xs) != len(body):
                        continue
                    want = sum(xs) / len(xs)
                    tol = 0.5 * 10 ** (-v[k][1]) + 0.5 * 10 ** (-min(b[2][k][1] for b in body)) + 1e-9
                    if abs(want - v[k][0]) <= tol:
                        ok += 1
                    elif not DELTA_COL.search(header[k]):
                        bad.append((header[k], v[k][0], want))
                if bad and ok >= 1 and ok >= len(bad):
                    for col, got, want in bad[:3]:
                        out.append({"kind": "table-arithmetic", "files": [path], "locator": f"line {ln}",
                                    "evidence": f"row '{cells[0]}', column {col}: {got:g}, but the mean of the {len(body)} rows above is "
                                                f"{want:.2f} (the row holds in {ok} other column(s))", "confidence": "high"})
            # 2. delta column = same difference / relative change of two columns in every row
            for d in [k for k in numeric if DELTA_COL.search(header[k])]:
                best = None
                for x in numeric:
                    for y in numeric:
                        if len({x, y, d}) < 3 or DELTA_COL.search(header[x]) or DELTA_COL.search(header[y]):
                            continue
                        for mode in ("diff", "rel"):
                            ok, bad = 0, []
                            for (ln, cells), v in zip(rows, vals):
                                if None in (v[x][0], v[y][0], v[d][0]) or (mode == "rel" and v[y][0] == 0):
                                    continue
                                want = v[x][0] - v[y][0] if mode == "diff" else (v[x][0] / v[y][0] - 1) * 100
                                tol = 0.5 * 10 ** (-v[d][1]) + 0.5 * 10 ** (-min(v[x][1], v[y][1])) * (1 if mode == "diff" else 100 / max(abs(v[y][0]), 1e-9)) + 1e-9
                                if abs(want - v[d][0]) <= tol:
                                    ok += 1
                                else:
                                    bad.append((ln, cells[0], v[d][0], want))
                            if ok >= 3 and (best is None or ok > best[0]):
                                best = (ok, bad, x, y, mode)
                if best and best[1] and best[0] >= 2 * len(best[1]):
                    ok, bad, x, y, mode = best
                    rule = f"{header[x]} - {header[y]}" if mode == "diff" else f"({header[x]} / {header[y]} - 1) x 100"
                    for ln, label, got, want in bad[:3]:
                        out.append({"kind": "table-arithmetic", "files": [path], "locator": f"line {ln}",
                                    "evidence": f"row '{label}': {header[d]} = {got:g}, but {rule} = {want:.2f} (the rule holds in {ok} other rows)",
                                    "confidence": "high"})
    # the same document copied into several snapshots: one finding listing the copies
    merged = {}
    for f in out:
        key = (posixpath.basename(f["files"][0]), f["locator"], f["evidence"])
        if key in merged:
            merged[key].setdefault("copies", []).append(f["files"][0])
        else:
            merged[key] = f
    return list(merged.values())


ID_TOKEN = re.compile(r"(?:^|[_/.-])(?:s|ts|seed|train|trainseed|train_seed)[_-]?(\d{1,5})(?=$|[_/.-])", re.I)
FLAGGY = re.compile(r"(excluded|leak|valid|ok|pass|complete|status|version|torch|cuda|backend|protocol|scorer|benchmark|split|dataset|"
                    r"deterministic)", re.I)


def _walk_records(obj, path="$"):
    if isinstance(obj, list):
        dicts = [x for x in obj if isinstance(x, dict)]
        if len(dicts) >= 3 and len(dicts) == len(obj):
            yield path, dicts
        for i, x in enumerate(obj[:500]):
            if isinstance(x, (list, dict)):
                yield from _walk_records(x, f"{path}[{i}]")
    elif isinstance(obj, dict):
        vals = list(obj.values())
        if len(vals) >= 3 and all(isinstance(v, dict) for v in vals):
            yield path, vals
        for k, v in list(obj.items())[:500]:
            if isinstance(v, (list, dict)):
                yield from _walk_records(v, f"{path}.{k}")


def _walk_dicts(obj, path="$"):
    if isinstance(obj, dict):
        yield path, obj
        for k, v in list(obj.items())[:500]:
            if isinstance(v, (list, dict)):
                yield from _walk_dicts(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, x in enumerate(obj[:500]):
            if isinstance(x, (list, dict)):
                yield from _walk_dicts(x, f"{path}[{i}]")


def _decimals(v):
    t = repr(float(v))
    return len(t.split(".")[1]) if "." in t and "e" not in t else 6


def _flat(d, prefix=""):
    for k, v in d.items():
        if isinstance(v, dict):
            yield from _flat(v, f"{prefix}{k}.")
        elif not isinstance(v, list):
            yield f"{prefix}{k}", v


# patterns used per JSON key (re.search(r'...') pays a cache lookup on every call)
_JR0 = re.compile(r"(checkpoint|ckpt|weights|model_path)", re.I)
_JR1 = re.compile(r"\.(pt|pth|ckpt|safetensors|bin)$")
_JR2 = re.compile(r"(^|\.)(train_seed|training_seed|job_key|policy|policy_label|model_seed)$", re.I)
_JR3 = re.compile(r"seed", re.I)
_JR4 = re.compile(r"^(.*?)[_-]?(mean|avg|average)$", re.I)
_JR5 = re.compile(r"(per_|values|all)", re.I)
_JR6 = re.compile(r"(policy|name|id|key|cell|run)$", re.I)
_JR7 = re.compile(r"(rate|percent|pct|sr|success|acc)", re.I)


def _json_records(con, rng) -> list[dict]:
    """Inside one JSON file: (a) a list of similar records (manifest entries, per-cell results) where one record's flag,
    version or protocol value differs from all others, or one numeric value is on a 100x smaller scale; (b) a record
    whose checkpoint path names another seed than its own seed fields (job for seed 3074 loading `_s3073` weights)."""
    out = []
    for path, text in con.execute("SELECT f.path, t.text FROM texts_t t JOIN files f ON f.fid = t.fid WHERE t.fid BETWEEN ? AND ? "
                                  "AND f.ext = '.json' AND f.path NOT LIKE '%::%'", rng):
        if not text or not text.lstrip().startswith(("{", "[")) or VENDORED.search(path):
            continue
        try:
            data = json.loads(text)
        except ValueError:
            continue
        # (b) identity mismatch in the file itself (job/config/result for one run)
        if isinstance(data, dict):
            flat = dict(_flat(data))
            ckpt = {k: v for k, v in flat.items() if isinstance(v, str) and _JR0.search(k)
                    and _JR1.search(v)}
            own = set()
            for k, v in flat.items():
                # identity = the training seed the record is about (eval/search seeds legitimately differ from the weights')
                if _JR2.search(k):
                    if isinstance(v, (int, float)) and not isinstance(v, bool) and _JR3.search(k):
                        own.add(int(v))
                    elif isinstance(v, str):
                        own |= {int(x) for x in ID_TOKEN.findall(v)}
            for k, v in ckpt.items():
                ids = {int(x) for x in ID_TOKEN.findall("/".join(v.split("/")[-3:]))}
                if ids and own and not (ids & own) and len(own) == 1:
                    out.append({"kind": "identity-mismatch", "files": [path], "locator": k,
                                "evidence": f"{k} points to weights of seed {sorted(ids)} ({v[-90:]}), while the record itself is for seed {sorted(own)}",
                                "confidence": "high"})
        # (c) a stored mean next to the values it summarises (r2_mean vs r2_per_dim)
        for loc, d in _walk_dicts(data):
            lists = {k: v for k, v in d.items() if isinstance(v, list) and 2 <= len(v) <= 1000
                     and all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in v)}
            for k, v in d.items():
                if isinstance(v, bool) or not isinstance(v, (int, float)):
                    continue
                m = _JR4.match(k)
                if not m:
                    continue
                stem = m.group(1).lower()
                for lk, lv in lists.items():
                    if stem and lk.lower().startswith(stem) or (not stem and _JR5.search(lk)):
                        want = sum(lv) / len(lv)
                        if abs(want - v) > max(1e-6, 1e-3 * abs(want)) and abs(want - v) > 0.5 * 10 ** (-min(6, _decimals(v))):
                            out.append({"kind": "aggregate-mismatch", "files": [path], "locator": f"{loc}.{k}",
                                        "evidence": f"{k} = {v:g}, but the mean of {lk} ({len(lv)} values) is {want:.6g}",
                                        "confidence": "high"})
                        break
        # (a) record outliers
        for loc, recs in _walk_records(data):
            flats = [dict(_flat(r)) for r in recs]
            keys = set.intersection(*(set(f) for f in flats))
            for k in keys:
                vals = [f[k] for f in flats]
                if all(isinstance(v, (bool, str)) for v in vals) and FLAGGY.search(k):
                    c = Counter(json.dumps(v) for v in vals)
                    if len(c) == 2:
                        (major, mc), (minor, nc) = c.most_common()
                        if nc == 1 and mc >= 4 and len(minor) <= 60:
                            i = [json.dumps(v) for v in vals].index(minor)
                            label = next((str(flats[i][x]) for x in flats[i] if _JR6.search(x)), f"#{i}")
                            out.append({"kind": "record-outlier", "files": [path], "locator": f"{loc}[{i}].{k}",
                                        "evidence": f"record '{label[:90]}': {k} = {minor}, while all {mc} other records have {major}",
                                        "confidence": "high"})
                nums = [v for v in vals if isinstance(v, (int, float)) and not isinstance(v, bool)]
                if len(nums) == len(vals) and len(nums) >= 3 and _JR7.search(k):
                    med = sorted(nums)[len(nums) // 2]
                    if 5 <= med <= 100:
                        for i, v in enumerate(nums):
                            if 0 < v <= 1 and v * 50 < med:
                                out.append({"kind": "record-outlier", "files": [path], "locator": f"{loc}[{i}].{k}",
                                            "evidence": f"{k} = {v:g} in record #{i}, while the median of {len(nums)} records is {med:g} "
                                                        "(a fraction among percentages?)", "confidence": "high"})
    return out


RESULTISH = re.compile(r"(\.(json|csv|tsv|jsonl)$|result|metric|eval|score|summary)", re.I)


def _missing_siblings(con, rng) -> list[dict]:
    """Replicate folders (same path shape, digits ignored) normally hold the same set of files. A file that every
    sibling has but one folder lacks is a missing raw result (seed_1.json absent from one cell)."""
    dirs = defaultdict(set)
    for (path,) in con.execute("SELECT path FROM files WHERE fid BETWEEN ? AND ? AND path NOT LIKE '%::%'", rng):
        d, b = posixpath.split(path)
        dirs[d].add(b)
    groups = defaultdict(list)
    for d, names in dirs.items():
        groups[DIGITS.sub("#", d)].append(d)
    out = []
    for tpl, ds in groups.items():
        if len(ds) < 3 or len(ds) > 2000:
            continue
        counts = Counter(n for d in ds for n in dirs[d])
        need = len(ds) - 1 if len(ds) < 10 else max(3, int(0.9 * len(ds)))  # small groups: all but the one folder
        typical = {n for n, c in counts.items() if c >= max(2, need)}
        common = {n for n in typical if counts[n] < len(ds)}
        if not common:
            continue
        for d in ds:
            # only results count: logs, env stamps, scripts and pruned checkpoints are routinely absent
            miss = sorted(n for n in common if n not in dirs[d] and RESULTISH.search(n))
            # a folder missing most of the common set is a different kind of run (or not started), not a lost file
            if miss and len(miss) <= max(1, len(typical) // 3) and len(dirs[d]) >= 2:
                if all(REPLICATE_SEG.search(m) or re.search(r"\d", m) for m in miss) or len(miss) <= 2:
                    out.append({"kind": "missing-in-replicate", "files": [d + "/" + miss[0]], "locator": d,
                                "evidence": f"{d} lacks {', '.join(miss[:4])}, which {counts[miss[0]]} of {len(ds)} sibling folders have",
                                "confidence": "medium"})
    return out[:200]


SIZE_HDR = re.compile(r"^(size|bytes|size_bytes|nbytes|file_size|length)$", re.I)
PATH_HDR = re.compile(r"^(path|file|filename|relpath|relative_path|name)$", re.I)


def _declared_sizes(con, rng) -> list[dict]:
    """An archive/file index (TSV/CSV with a path column and a size column) whose recorded size differs from the
    file's real size: the file was modified after the index was written."""
    out = []
    for path, text in con.execute("SELECT f.path, t.text FROM texts_t t JOIN files f ON f.fid = t.fid WHERE t.fid BETWEEN ? AND ? "
                                  "AND f.ext IN ('.tsv', '.csv') AND f.path NOT LIKE '%::%'", rng):
        lines = (text or "").splitlines()
        if len(lines) < 2:
            continue
        sep = "\t" if "\t" in lines[0] else ","
        hdr = [h.strip().strip('"') for h in lines[0].split(sep)]
        pi = next((i for i, h in enumerate(hdr) if PATH_HDR.match(h)), None)
        si = next((i for i, h in enumerate(hdr) if SIZE_HDR.match(h)), None)
        start = 1
        if pi is None or si is None:
            # headerless `size<TAB>path` listings: infer the columns from the first rows
            sample = [l.split(sep) for l in lines[:6]]
            if not sample or len({len(r) for r in sample}) != 1 or len(sample[0]) < 2:
                continue
            ncol = len(sample[0])
            si = next((i for i in range(ncol) if all(r[i].strip().isdigit() for r in sample)), None)
            pi = next((i for i in range(ncol) if all(re.search(r"[/.]", r[i]) and not r[i].strip().isdigit() for r in sample)), None)
            if pi is None or si is None:
                continue
            start = 0
        base = posixpath.dirname(path)
        bad, ok = [], 0
        for ln, line in enumerate(lines[start:], start + 1):
            cells = [c.strip().strip('"') for c in line.split(sep)]
            if len(cells) <= max(pi, si) or not cells[si].isdigit():
                continue
            name = cells[pi].lstrip("./")
            row = None
            for cand in (name, posixpath.normpath(posixpath.join(base, name)), posixpath.normpath(posixpath.join(posixpath.dirname(base), name))):
                row = con.execute("SELECT path, size FROM files WHERE path = ?", (cand,)).fetchone()
                if row:
                    break
            if not row or row[1] is None or row[0] == path:
                continue  # the index listing itself is written last
            if int(cells[si]) == row[1]:
                ok += 1
            else:
                bad.append((ln, row[0], int(cells[si]), row[1]))
        if bad and ok >= 3 * len(bad):
            ln, f, want, got = bad[0]
            out.append({"kind": "declared-size-mismatch", "files": [f, path], "locator": f"{path} line {ln}",
                        "evidence": f"{path} records {want} bytes for {f}, the file has {got} bytes (modified after the index was written)"
                                    + (f"; {len(bad) - 1} more" if len(bad) > 1 else "") + f"; {ok} other entries match",
                        "confidence": "high"})
    return out


STAMP_KEY = re.compile(r"(?P<k>(?:finali[sz]ed|completed|finished|archived|started|start|collected|created))(?:_at|_time)?\s*[=:]\s*\"?"
                       r"(?P<t>20\d\d-\d\d-\d\dT\d\d:\d\d(?::\d\d)?(?:\.\d+)?(?:[+-]\d\d:?\d\d|Z))", re.I)
BARE_STAMP = re.compile(r"^\s*(20\d\d-\d\d-\d\dT\d\d:\d\d(?::\d\d)?(?:\.\d+)?(?:[+-]\d\d:?\d\d|Z))\s*$")


def _event_order(con, rng) -> list[dict]:
    return _event_order_from(_stamp_pass(con, rng)[1])


def _event_row(path, text, per_dir) -> None:
    base = posixpath.basename(path).lower()
    m = BARE_STAMP.match(text.strip()) if len(text) < 80 else None
    if m:  # FINALIZED_AT.txt / STARTED_AT style: the file name is the event
        ev = re.match(r"(finali[sz]ed|completed|finished|archived|started|start)", base)
        if ev:
            per_dir[posixpath.dirname(path)].append((ev.group(1), m.group(1), path))
        return
    for mm in STAMP_KEY.finditer(text[:5000]):
        per_dir[posixpath.dirname(path)].append((mm.group("k").lower(), mm.group("t"), path))


def _event_order_from(per_dir) -> list[dict]:
    """Stamps in one provenance folder must respect the order of events: a run/phase cannot be finalized or completed
    before it was started or archived (FINALIZED_AT 20:47 vs archived_at 20:51)."""
    import datetime
    out = []
    late = ("finali", "complet", "finish")
    early = ("start", "archiv")
    for d, evs in per_dir.items():
        def ts(t):
            try:
                return datetime.datetime.fromisoformat(t.replace("Z", "+00:00")).timestamp()
            except ValueError:
                return None
        ends = [(k, ts(t), t, p) for k, t, p in evs if k.startswith(late) and ts(t)]
        starts = [(k, ts(t), t, p) for k, t, p in evs if k.startswith(early) and ts(t)]
        for k1, t1, raw1, p1 in ends:
            for k2, t2, raw2, p2 in starts:
                # archiving normally follows finalization, but finalization cannot precede the start of what it finalizes;
                # and a 'finalized' stamp earlier than the archive it describes contradicts a FINALIZED-after-archive layout
                if t2 - t1 > 60 and (k2.startswith("start") or k1.startswith("finali") and k2.startswith("archiv")):
                    out.append({"kind": "event-order", "files": [p1, p2],
                                "evidence": f"{k1} at {raw1} ({posixpath.basename(p1)}) is earlier than {k2} at {raw2} ({posixpath.basename(p2)})",
                                "confidence": "medium"})
                    break
    return out[:100]


LOG_TS = re.compile(r"(20\d\d-\d\d-\d\d)[ T](\d\d:\d\d:\d\d)")
UNIX_START = re.compile(r'"(?:started_unix|start_unix|start_time_unix|started_at_unix)"\s*:\s*(\d{9,10}(?:\.\d+)?)')


def _sibling_stamps(con, rng) -> list[dict]:
    """An eval/run record states when it started (unix time); the log written next to it shows its own wall-clock
    times. The offset between the two is the same for every sibling (time zone); one record whose offset differs
    has an edited or wrong stamp."""
    import datetime
    by_dir = defaultdict(list)
    for path, text in con.execute("SELECT f.path, t.text FROM texts_t t JOIN files f ON f.fid = t.fid WHERE t.fid BETWEEN ? AND ? "
                                  "AND f.ext = '.json' AND f.path NOT LIKE '%::%'", rng):
        m = UNIX_START.search(text or "")
        if not m:
            continue
        stem = posixpath.splitext(path)[0]
        log = con.execute("SELECT t.text FROM texts_t t JOIN files f ON f.fid = t.fid WHERE f.path = ?", (stem + ".log",)).fetchone()
        if not log or not log[0]:
            continue
        lm = LOG_TS.search(log[0])
        if not lm:
            continue
        local = datetime.datetime.fromisoformat(f"{lm.group(1)}T{lm.group(2)}").replace(tzinfo=datetime.timezone.utc).timestamp()
        by_dir[DIGITS.sub("#", posixpath.dirname(path))].append((path, local - float(m.group(1))))
    out = []
    for tpl, items in by_dir.items():
        if len(items) < 4:
            continue
        offs = sorted(o for _, o in items)
        med = offs[len(offs) // 2]
        typical = sum(1 for o in offs if abs(o - med) < 600)
        # a second convention shared by several records (logs in UTC vs local time) is not an edit: flag lone outliers
        bucket = Counter(round((o - med) / 600) for o in offs)
        for p, o in items:
            if abs(o - med) >= 1800 and typical >= 3 and bucket[round((o - med) / 600)] == 1:
                out.append({"kind": "stamp-disagrees-with-log", "files": [p],
                            "evidence": f"its started time is {round((o - med) / 3600, 2)} h away from what its .log shows, relative to the "
                                        f"offset shared by {typical} sibling records", "confidence": "medium"})
    return out[:100]
