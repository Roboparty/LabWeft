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
import re
from collections import Counter, defaultdict

from .analyze import page, result

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
    order = {"identical-replicate-content": 0, "truncated-run": 1, "setting-outlier": 2}
    findings.sort(key=lambda f: (order.get(f["kind"], 9), f["files"][0]))
    return result("found" if findings else "not_found", con, scope=scope, by_kind=dict(Counter(f["kind"] for f in findings)),
                  findings=page(findings, offset, limit),
                  limitations=["replicates are recognised by paths that differ only in numbers; differently named variants are not compared",
                               "launch settings come from command lines echoed in logs/launch scripts (probe v7); older indexes have none",
                               "a lead, not a verdict: read the cited files (and the authors' notes) before reporting"])
