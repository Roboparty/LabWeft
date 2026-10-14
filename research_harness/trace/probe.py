#!/usr/bin/env python3
"""LabWeft trace probe: read-only fact extraction that runs next to the data.

Self-contained on purpose (stdlib only, Python 3.8+) so it can be streamed to a server with
`ssh host python3 - --root ... < probe.py`. It never executes project code, never writes inside
the scanned root, and classifies files by content rather than by folder name. Output is JSON
lines (optionally gzip); every record is a fact about one file with a content hash.
"""
from __future__ import annotations

import argparse
import ast
import csv
import gzip
import hashlib
import io
import json
import math
import os
import re
import socket
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED

PROBE_VERSION = "11"
BULK_MIN_FILES = 5000
RESUME_COMPATIBLE = {"11"}  # v5 lacks only JSON declared facts; reuse its parse work on huge trees
SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv", ".mypy_cache", ".pytest_cache",
             ".ipynb_checkpoints", "wandb-cache", ".cache", ".research"}
SENSITIVE = re.compile(r"(^|[._-])(secret|secrets|token|credentials?|password|passwd|id_rsa|id_ed25519|netrc)([._-]|$)|\.env$|\.pem$|\.key$", re.I)
SECRET_VALUE = re.compile(r"(api[_-]?key|token|secret|password|passwd|authorization|bearer)\s*[=:]\s*\S+|sk-[A-Za-z0-9]{16,}|ghp_[A-Za-z0-9]{20,}|hf_[A-Za-z0-9]{20,}", re.I)
TEXT_EXT = {".json", ".jsonl", ".csv", ".tsv", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".py", ".sh", ".bash",
            ".md", ".markdown", ".rst", ".txt", ".log", ".out", ".err", ".tex", ".bib", ".html", ".xml", ".ipynb"}
BINARY_KIND = {
    "checkpoint": {".pt", ".pth", ".ckpt", ".safetensors", ".bin", ".pkl", ".pickle", ".joblib", ".h5", ".hdf5", ".onnx"},
    "array": {".npy", ".npz", ".parquet", ".arrow", ".feather", ".zarr", ".lmdb", ".tfrecord"},
    "media": {".png", ".jpg", ".jpeg", ".gif", ".svg", ".pdf", ".mp4", ".webm", ".avi", ".mov", ".wav", ".mp3", ".webp"},
    "archive": {".tar", ".gz", ".tgz", ".zip", ".7z", ".xz", ".zst", ".bz2", ".partial"},
}
METRIC_KEY = re.compile(r"(^|[_/.\-\s])(sr|success|succ|acc|accuracy|top1|top5|loss|reward|return|fid|psnr|ssim|lpips|auc|f1|precision|recall|err|error|mse|mae|rmse|rank|erank|score|macro|micro|fps|throughput|it_s|its|latency|time|sec|seconds|mem|memory|vram|emd|dist|distance|bleu|rouge|ppl|perplexity|win|rate|pct|percent|gain|delta|collapse|var|std|sd|mean|median|ci)([_/.\-\s0-9]|$)", re.I)
CONFIG_KEY = re.compile(r"(^|[_/.\-])(lr|learning_rate|seed|epoch|epochs|ep|batch|batch_size|bs|lambda|lam|lmbda|weight|coef|coeff|beta|alpha|gamma|tau|eps|dim|depth|layers|heads|width|hidden|model|method|arch|variant|arm|family|task|tasks|env|dataset|data|optimizer|optim|warmup|steps|max_steps|sched|scheduler|sigreg|sig|vis|visreg|qq|endpoint|solver|planner|horizon|num_workers|workers|gpus|world_size|precision|amp|dtype|attn|sdpa|backend|ckpt|checkpoint|resume|init|baseline|ablation|mode|protocol|split|n_|num_)([_/.\-0-9]|$)", re.I)
SEED_KEY = re.compile(r"(^|_)(seed|train_seed|eval_seed|run_seed|rep|replicate)(s)?$", re.I)
NUM_RE = re.compile(r"(?<![\w.])[-+]?\d+\.\d+(?:[eE][-+]?\d+)?%?|(?<![\w.])\d{1,3}(?:\.\d+)?%")
PM_RE = re.compile(r"([-+]?\d+(?:\.\d+)?)\s*(?:±|\+/-|\\pm|\+-)\s*(\d+(?:\.\d+)?)")
DATE_RE = re.compile(r"(?<!\d)(20\d{2})[-_./]?(0[1-9]|1[0-2])[-_./]?(0[1-9]|[12]\d|3[01])(?!\d)")
PATHLIKE = re.compile(r"(?:(?:/|\.{1,2}/|~/)?[A-Za-z0-9_.@+-]+/)+[A-Za-z0-9_.@+*{}$-]+")
IDENT = re.compile(r"\b(?:phase\d+[a-z]?|run[_-]?\w+|exp[_-]?\w+|seed[_-]?\d+|e\d{1,4}|ep\d+|step_?\d{3,}|[A-Za-z][A-Za-z0-9]*(?:[_-][A-Za-z0-9]+){1,6})\b")
CMD_RE = re.compile(r"^\s*(?:CUDA_VISIBLE_DEVICES=\S+\s+|[A-Z_]+=\S+\s+)*(?:nohup\s+|setsid\s+|srun\s+|exec\s+)*(python3?|torchrun|accelerate|deepspeed|bash|sh|uv\s+run)\b.*")
WRITE_FLAG = re.compile(r"--(?:out|output|save|log|ckpt_dir|checkpoint_dir|run_dir|work_dir|exp_dir|result|results|dump)[\w-]*[ =]+(\S+)", re.I)
READ_FLAG = re.compile(r"--(?:config|cfg|load|resume|init|ckpt|checkpoint|weights|pretrained|data|dataset|input|manifest|bank)[\w-]*[ =]+(\S+)", re.I)
PROGRESS = re.compile(r"(?:epoch|ep)\s*[:=\[ ]\s*(\d+)\s*(?:/\s*(\d+))?|step\s*[:= ]\s*(\d+)\s*(?:/\s*(\d+))?", re.I)
KV_IN_LINE = re.compile(r"([A-Za-z][\w/.\-]{1,48})\s*[=:]\s*([-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)%?")
ERROR_RE = re.compile(r"Traceback \(most recent call last\)|\b(Error|Exception|CUDA out of memory|Killed|Segmentation fault|NaN detected)\b")
STATUS_KEY = re.compile(r"(^|_)(status|state|verdict|valid|validity|complete|completed|completion|usable|ok|passed|outcome|result_status|deprecated|superseded|host|hostname|machine|node_name|server|cluster|gpu_name|device_name)$", re.I)
NONMETRIC_KEY = re.compile(r"(^|_)(ids?|index|idx|indices|position|positions|start_steps?|return_code|returncode|pid|port|rank|gpu|gpu_id|env_index|episode_ids?|timestamp|time_stamp|created|mtime|size|bytes|version|line|row)$", re.I)
INFRA_KEY = re.compile(r"^(gpu|gpus|gpu_id|device|rank|local_rank|pid|port|host|hostname|node|worker|job|job_id|shard|index|idx|row|line)$", re.I)
PATH_KV = re.compile(r"(?i)(?:^|[_\-./])(lr|seed|ep|epoch|epochs|bs|lam|lambda|sig|vis|qq|beta|gamma|tau|dim|h|k|n|rh|e)[_=-]?(\d+(?:p\d+|\.\d+)?(?:e-?\d+)?)(?=$|[_\-./])")

LIMITS = {"text_bytes": 256 * 1024, "metrics": 600, "config": 400, "refs": 200, "ids": 200, "numbers": 400, "outline": 120, "cmds": 60,
          "table_rows": 3000, "table_bytes": 768 * 1024, "dates": 40, "kv": 400}


def redact(text):
    return SECRET_VALUE.sub("[redacted]", text)


def sniff_kind(rel, ext, head):
    for kind, exts in BINARY_KIND.items():
        if ext in exts:
            return kind
    if b"\x00" in head[:4096]:
        return "binary"
    if ext in TEXT_EXT or not ext:
        return "text"
    try:
        head[:2048].decode("utf-8")
        return "text"
    except UnicodeDecodeError:
        return "binary"


def finite(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def flatten(obj, prefix="$", out=None, limit=20000):
    if out is None:
        out = []
    if len(out) >= limit:
        return out
    if isinstance(obj, dict):
        for k, v in obj.items():
            flatten(v, prefix + "." + str(k), out, limit)
    elif isinstance(obj, list):
        if len(obj) > 8 and all(finite(v) for v in obj[:64]):
            vals = [float(v) for v in obj if finite(v)]
            out.append((prefix + "[*]", ("__vector__", len(obj), sum(vals) / max(1, len(vals)), min(vals or [0]), max(vals or [0]))))
            return out
        for i, v in enumerate(obj[:2000]):
            flatten(v, prefix + "[" + str(i) + "]", out, limit)
    else:
        out.append((prefix, obj))
    return out


def leaf_key(locator):
    key = re.split(r"[.\[]", re.sub(r"\[(\d+|\*)\]$", "", locator))[-1].rstrip("]")
    return key


def path_config(rel):
    """Weak facts from path tokens such as `lr3e-4` or `seed_42` (authority: path-token)."""
    found = {}
    for part in rel.split("/"):
        for k, v in PATH_KV.findall(part):
            found.setdefault(k.lower(), v.replace("p", "."))
    return found


AGG_LOC = re.compile(r"(macro|mean|avg|average|std|stdev|_sd\b|\.sd\b|summary|overall|total|final|by_train_seed|by_seed|aggregate)", re.I)


def json_facts(rel, data, facts):
    leaves = flatten(data, limit=200000)
    metrics, config, strings = [], {}, []
    vectors = []
    declared = {}
    for loc, val in leaves:
        key = leaf_key(loc)
        if isinstance(val, tuple) and val and val[0] == "__vector__":
            if len(vectors) < 200:
                vectors.append([loc, val[1], round(val[2], 6), val[3], val[4]])
            continue
        if finite(val) and NONMETRIC_KEY.search(key):
            continue
        if finite(val):
            if SEED_KEY.search(key) or (CONFIG_KEY.search(key) and not METRIC_KEY.search(key)):
                if len(config) < LIMITS["config"]:
                    config[loc] = val
            else:
                metrics.append([loc, key, val])
        elif isinstance(val, str):
            if STATUS_KEY.search(key) and len(val) <= 80 and len(declared) < 60:
                declared[loc] = val  # the authors' own declared state ("complete", "invalid", "superseded")
            if CONFIG_KEY.search(key) and len(val) <= 120 and len(config) < LIMITS["config"]:
                config[loc] = val
            if len(val) <= 400:
                strings.append(val)
        elif isinstance(val, bool) and CONFIG_KEY.search(key) and len(config) < LIMITS["config"]:
            config[loc] = val
    facts["n_leaves"] = len(leaves)
    for loc, val in leaves:
        if isinstance(val, bool) and STATUS_KEY.search(leaf_key(loc)) and len(declared) < 60:
            declared[loc] = val
    if declared:
        facts["declared"] = declared
    if vectors:
        facts["vectors"] = vectors
    if len(metrics) > LIMITS["metrics"]:
        # big summaries (coverage / results JSON with thousands of cells): keep the aggregates first
        agg = [m for m in metrics if AGG_LOC.search(m[0])]
        rest = [m for m in metrics if not AGG_LOC.search(m[0])]
        facts["metrics_truncated"] = len(metrics)
        metrics = (agg + rest)[: max(LIMITS["metrics"], min(len(agg), 4000))]
    named_metrics = sum(1 for _, k, _ in metrics if METRIC_KEY.search(k))
    facts["metrics"] = metrics
    facts["config"] = config
    rows = None
    if isinstance(data, list) and data and all(isinstance(x, dict) for x in data[:50]):
        rows = data
    elif isinstance(data, dict):
        for key in ("rows", "results", "records", "runs", "data", "items", "table", "jobs", "entries"):
            if isinstance(data.get(key), list) and data[key] and all(isinstance(x, dict) for x in data[key][:50]):
                rows = data[key]
                facts["table_locator"] = "$." + key
                break
    if rows is not None:
        table_facts(rows, facts, source="json")
    if facts.get("table") and facts["table"]["n_rows"] >= 2:
        role = "result_table" if facts["table"]["metric_cols"] else "manifest"
    elif named_metrics >= 1 and named_metrics >= len(config) * 0.25:
        role = "result"
    elif config and len(config) >= max(3, len(metrics)):
        role = "config"
    elif sum(1 for s in strings if "/" in s) > max(5, len(leaves) // 2):
        role = "manifest"
    elif metrics:
        role = "result"
    else:
        role = "data"
    return role, " ".join(strings)[:200000]


def classify_columns(rows, cols):
    kinds = {}
    for c in cols:
        vals = [r.get(c) for r in rows[:LIMITS["table_rows"]]]
        nums = []
        strs = set()
        for v in vals:
            if finite(v):
                nums.append(float(v))
            elif isinstance(v, str):
                t = v.strip().rstrip("%")
                try:
                    f = float(t)
                    if math.isfinite(f):
                        nums.append(f)
                        continue
                except ValueError:
                    pass
                if t:
                    strs.add(t[:80])
        distinct_num = len(set(nums))
        if SEED_KEY.search(c):
            kinds[c] = "seed"
        elif INFRA_KEY.search(c):
            kinds[c] = "infra"
        elif strs and len(strs) >= len(nums):
            kinds[c] = "factor" if len(strs) <= max(64, len(vals) // 2) else "id"
        elif nums and METRIC_KEY.search(c):
            kinds[c] = "metric"
        elif nums and CONFIG_KEY.search(c):
            kinds[c] = "factor"
        elif nums and distinct_num <= 12 and len(nums) >= 8 and all(float(x).is_integer() or abs(x) < 10 for x in set(nums)):
            kinds[c] = "factor"
        elif nums:
            kinds[c] = "metric"
        else:
            kinds[c] = "empty"
    return kinds


def table_facts(rows, facts, source):
    cols = []
    for r in rows[:200]:
        for c in r.keys():
            if c not in cols and len(cols) < 200:
                cols.append(str(c))
    rows = [{str(k): v for k, v in r.items() if not isinstance(v, (dict, list))} for r in rows]
    kinds = classify_columns(rows, cols)
    table = {"source": source, "n_rows": len(rows), "columns": cols, "col_kinds": kinds,
             "metric_cols": [c for c in cols if kinds.get(c) == "metric"],
             "factor_cols": [c for c in cols if kinds.get(c) == "factor"],
             "seed_cols": [c for c in cols if kinds.get(c) == "seed"]}
    keep = [c for c in cols if kinds.get(c) in ("metric", "factor", "seed", "id")]
    slim = [{c: r.get(c) for c in keep if r.get(c) not in (None, "")} for r in rows[:LIMITS["table_rows"]]]
    blob = json.dumps(slim, ensure_ascii=False, default=str)
    if len(blob) <= LIMITS["table_bytes"]:
        table["rows"] = slim
        table["rows_complete"] = len(rows) <= LIMITS["table_rows"]
    else:
        table["rows"] = slim[:20]
        table["rows_complete"] = False
        table["rows_truncated_reason"] = "table_bytes"
    facts["table"] = table


def csv_facts(text, delim, facts):
    reader = csv.DictReader(io.StringIO(text), delimiter=delim)
    rows = []
    for i, r in enumerate(reader):
        rows.append(r)
        if i > 200000:
            break
    if not reader.fieldnames:
        return "data"
    table_facts(rows, facts, source="csv")
    return "result_table" if facts["table"]["metric_cols"] else "manifest"


def yaml_like(text, facts):
    """Indentation-aware key: value reader; enough for Hydra/OmegaConf dumps without PyYAML."""
    config, stack = {}, []
    for raw in text.splitlines()[:5000]:
        if not raw.strip() or raw.lstrip().startswith(("#", "- ")) or ":" not in raw:
            continue
        indent = len(raw) - len(raw.lstrip())
        key, _, val = raw.strip().partition(":")
        key = key.strip().strip("'\"")
        while stack and stack[-1][0] >= indent:
            stack.pop()
        path = ".".join([s[1] for s in stack] + [key])
        val = val.split(" #")[0].strip().strip("'\"")
        if val == "":
            stack.append((indent, key))
            continue
        if len(config) < LIMITS["config"]:
            try:
                num = float(val)
                config["$." + path] = int(num) if num.is_integer() and "." not in val and "e" not in val.lower() else num
            except ValueError:
                if len(val) <= 160:
                    config["$." + path] = val
    facts["config"] = config
    return "config"


def py_facts(text, facts):
    args, imports, literals, funcs = [], [], [], []
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError, RecursionError):
        tree = None
    if tree is not None:
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and getattr(node.func, "attr", "") == "add_argument" and node.args:
                first = node.args[0]
                if isinstance(first, ast.Constant) and isinstance(first.value, str):
                    default = None
                    for kw in node.keywords:
                        if kw.arg == "default" and isinstance(kw.value, ast.Constant):
                            default = kw.value.value
                    args.append([first.value, default if isinstance(default, (int, float, str, bool, type(None))) else None])
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                mod = getattr(node, "module", None) or ",".join(a.name for a in node.names)
                if mod and len(imports) < 80:
                    imports.append(mod)
            elif isinstance(node, (ast.FunctionDef, ast.ClassDef)) and len(funcs) < 200:
                funcs.append([node.name, node.lineno])
            elif isinstance(node, ast.Constant) and isinstance(node.value, str) and "/" in node.value and len(node.value) < 300:
                literals.append(node.value)
    facts["args"] = args[:200]
    facts["imports"] = sorted(set(imports))[:80]
    facts["symbols"] = funcs
    is_entry = "__main__" in text or bool(args)
    lower = text.lower()
    if is_entry and re.search(r"\b(train|fit|optimizer\.step|backward\(\))", lower):
        return "train_script", " ".join(literals)
    if is_entry and re.search(r"\b(eval|evaluate|rollout|benchmark|success)", lower):
        return "eval_script", " ".join(literals)
    if re.search(r"\b(plt\.|matplotlib|savefig)", lower):
        return "plot_script", " ".join(literals)
    return ("script" if is_entry else "module"), " ".join(literals)


HYDRA_KV = re.compile(r"(?:^|\s)(\+{0,2}[A-Za-z_][\w.\-]{0,60})=([^\s\"']{1,120})")
FLAG_KV = re.compile(r"(?:^|\s)--([A-Za-z][\w\-]{0,60})(?:=|\s+)([^\s\-][^\s]{0,119})")


def launch_args(text):
    """Settings stated on a command line: Hydra overrides and --flags. Only lines that look like a command."""
    out = {}
    for line in text.splitlines():
        if not re.search(r"(\.py\b|python|torchrun|accelerate|deepspeed|\bcmd\b|command|\bargs?\b)", line, re.I):
            continue
        for k, v in HYDRA_KV.findall(line):
            k = k.lstrip("+")
            if len(out) < 120 and not SECRET_VALUE.search(f"{k}={v}"):
                out.setdefault(k, v)
        for k, v in FLAG_KV.findall(line):
            if len(out) < 120 and not SECRET_VALUE.search(f"{k}={v}"):
                out.setdefault("--" + k, v)
    return out


def line_facts(text, facts, doc):
    lines = text.splitlines()
    cmds, numbers, outline, kv, errors = [], [], [], {}, 0
    max_epoch = max_step = None
    total_epoch = total_step = None
    for i, line in enumerate(lines, 1):
        s = line.strip()
        if not s:
            continue
        if len(cmds) < LIMITS["cmds"] and CMD_RE.match(s):
            cmds.append([i, redact(s[:600])])
        if doc and (s.startswith("#") or s.startswith("\\section") or s.startswith("\\subsection") or s.startswith("\\caption")) and len(outline) < LIMITS["outline"]:
            outline.append([i, s[:200]])
        if NUM_RE.search(s) and len(numbers) < LIMITS["numbers"] and (doc or KV_IN_LINE.search(s) is None):
            numbers.append([i, redact(s[:300])])
        if not doc:
            for k, v in KV_IN_LINE.findall(s):
                if METRIC_KEY.search(k) or CONFIG_KEY.search(k):
                    kv.setdefault(k, [i, v])  # first occurrence
                    kv[k + "@last"] = [i, v]
                    if len(kv) > LIMITS["kv"]:
                        break
            m = PROGRESS.search(s)
            if m:
                if m.group(1):
                    max_epoch = max(max_epoch or 0, int(m.group(1)))
                    total_epoch = int(m.group(2)) if m.group(2) else total_epoch
                if m.group(3):
                    max_step = max(max_step or 0, int(m.group(3)))
                    total_step = int(m.group(4)) if m.group(4) else total_step
            if ERROR_RE.search(s):
                errors += 1
    facts["cmds"] = cmds
    facts["numbers"] = numbers
    if doc:
        facts["outline"] = outline
        pm = [[m.group(1), m.group(2)] for m in PM_RE.finditer(text)][:200]
        if pm:
            facts["pm"] = pm
    else:
        facts["kv"] = kv
        facts["progress"] = {"max_epoch": max_epoch, "of_epoch": total_epoch, "max_step": max_step, "of_step": total_step, "errors": errors,
                             "tail": [redact(x[:300]) for x in lines[-5:]]}
    return lines


def refs_and_ids(text, rel):
    refs, ids = [], {}
    for m in PATHLIKE.findall(text[:400000]):
        if len(m) > 3 and not m.startswith("http") and "." in m.split("/")[-1] or m.count("/") >= 2:
            refs.append(m.strip("'\".,;:()[]"))
            if len(refs) >= 4 * LIMITS["refs"]:
                break
    for m in IDENT.findall(text[:400000]):
        if len(m) >= 4 and any(ch.isdigit() for ch in m) or "-" in m or "_" in m:
            ids[m] = ids.get(m, 0) + 1
    top = sorted(ids.items(), key=lambda kv: (-kv[1], kv[0]))[: LIMITS["ids"]]
    uniq = []
    for r in refs:
        if r not in uniq:
            uniq.append(r)
        if len(uniq) >= LIMITS["refs"]:
            break
    dates = sorted({"-".join(d) for d in DATE_RE.findall(rel + "\n" + text[:200000])})[: LIMITS["dates"]]
    return uniq, [k for k, _ in top], dates


ARCHIVE_RE = re.compile(r"\.(tar|tgz|tar\.gz|tar\.bz2|tar\.xz|zip)$", re.I)


def peek_archive(path, rel, mtime, max_text, max_members=5000, max_read=64 * 1024 * 1024):
    """Look inside tar/zip bundles the way REA unpacks app bundles: list every member, analyse small text members
    as virtual files `bundle.tgz::inner/path`. Never extracts to disk."""
    import tarfile
    import zipfile
    members, listed, read_total = [], 0, 0

    def member(name, msize, data):
        rel_m = rel + "::" + name.lstrip("./")
        if data is None:
            return {"t": "file", "p": rel_m, "s": msize, "m": int(mtime), "ext": os.path.splitext(name)[1].lower(),
                    "k": "archived", "st": "metadata_only", "r": "archive_member"}
        sub = analyze(None, rel_m, msize, mtime, max_text, _raw=data)
        sub["r"] = "archive_member"
        return sub
    if rel.lower().endswith(".zip"):
        with zipfile.ZipFile(path) as zf:
            for info in zf.infolist()[:max_members]:
                if info.is_dir():
                    continue
                listed += 1
                ext = os.path.splitext(info.filename)[1].lower()
                take = ext in TEXT_EXT and info.file_size <= max_text and read_total + info.file_size <= max_read
                data = zf.read(info) if take else None
                read_total += len(data or b"")
                members.append(member(info.filename, info.file_size, data))
    else:
        with tarfile.open(path, "r:*") as tf:
            for info in tf:
                if listed >= max_members:
                    break
                if not info.isfile():
                    continue
                listed += 1
                ext = os.path.splitext(info.name)[1].lower()
                take = ext in TEXT_EXT and info.size <= max_text and read_total + info.size <= max_read
                data = tf.extractfile(info).read() if take else None
                read_total += len(data or b"")
                members.append(member(info.name, info.size, data))
    return members, {"members_listed": listed, "bytes_read": read_total, "complete": listed < max_members,
                     "truncated": listed >= max_members, "note": "member list capped" if listed >= max_members else None}


def analyze(root, rel, size, mtime, max_text, _raw=None, max_archive=128 * 1024 * 1024):
    ext = os.path.splitext(rel)[1].lower()
    rec = {"t": "file", "p": rel, "s": size, "m": int(mtime), "ext": ext}
    if SENSITIVE.search(os.path.basename(rel.split("::")[-1])):
        rec.update(st="skipped", r="sensitive_name", k="sensitive")
        return rec
    if _raw is not None:
        raw = _raw
        rec["k"] = sniff_kind(rel, ext, raw[:8192])
        if rec["k"] != "text":
            rec["st"] = "metadata_only"
            return rec
    else:
        path = os.path.join(root, rel)
        try:
            with open(path, "rb") as fh:
                head = fh.read(8192)
                kind = sniff_kind(rel, ext, head)
                rec["k"] = kind
                if kind != "text":
                    if kind in ("archive", "binary") and size <= max_archive:
                        # declared checksums (*.sha256, manifests) of bundles and tarballs must be checkable
                        h = hashlib.sha256(head)
                        for chunk in iter(lambda: fh.read(1 << 20), b""):
                            h.update(chunk)
                        rec["h"] = h.hexdigest()
                    if kind == "archive" and ARCHIVE_RE.search(rel):
                        if size > max_archive:
                            if rel.lower().endswith(".tar"):
                                # an uncompressed tar can be listed by seeking from header to header: names and sizes
                                # without reading payloads, so its contents are still discoverable
                                try:
                                    members, info = peek_archive(path, rel, mtime, 0, max_read=0)
                                    rec.update(st="parsed", role="archive", r="archive_listed_only",
                                               f={"archive": dict(info, contents="names only; read members live"),
                                                  "title": os.path.basename(rel)}, members=members)
                                    return rec
                                except Exception:
                                    pass
                            rec.update(st="metadata_only", r="archive_too_large")
                            return rec
                        try:
                            members, info = peek_archive(path, rel, mtime, max_text)
                        except Exception as exc:  # corrupt / partial bundles stay inventoried
                            rec.update(st="metadata_only", r="archive_unreadable:" + type(exc).__name__)
                            return rec
                        rec.update(st="parsed", role="archive", f={"archive": info, "title": os.path.basename(rel)}, members=members)
                        return rec
                    rec["st"] = "metadata_only"
                    return rec
                if size > max_text and not (ext in (".json", ".csv", ".tsv") and size <= BIG_STRUCTURED):
                    rec.update(st="too_large", r="max_text_bytes")
                    return rec
                raw = head + fh.read()
        except OSError as exc:
            rec.update(st="error", r=type(exc).__name__)
            return rec
    rec["h"] = hashlib.sha256(raw).hexdigest()
    text = raw.decode("utf-8", errors="replace").lstrip("\ufeff")  # Excel/PowerShell CSVs start with a BOM
    facts = {}
    role, extra = "doc", ""
    try:
        if ext in (".json", ".ipynb"):
            try:
                data = json.loads(text)
                if ext == ".ipynb":
                    role, extra = "notebook", ""
                    text = "\n".join("".join(c.get("source", [])) for c in data.get("cells", []) if isinstance(c, dict))
                else:
                    role, extra = json_facts(rel, data, facts)
            except ValueError:
                role = "broken_json"
        elif ext == ".jsonl":
            rows = []
            for line in text.splitlines()[: LIMITS["table_rows"]]:
                try:
                    obj = json.loads(line)
                except ValueError:
                    continue
                if isinstance(obj, dict):
                    rows.append(obj)
            if rows:
                flat_rows = [{k[2:]: v for k, v in flatten(r) if not isinstance(v, (dict, list))} for r in rows]
                table_facts(flat_rows, facts, source="jsonl")
                role = "result_table" if facts["table"]["metric_cols"] else ("log" if len(rows) > 1 else "data")
        elif ext in (".csv", ".tsv"):
            role = csv_facts(text, "\t" if ext == ".tsv" else ",", facts)
        elif ext in (".yaml", ".yml", ".toml", ".ini", ".cfg"):
            role = yaml_like(text, facts)
        elif ext == ".py":
            role, extra = py_facts(text, facts)
        elif ext in (".sh", ".bash"):
            role = "launcher"
        elif ext in (".md", ".markdown", ".rst", ".tex", ".html"):
            role = "report" if ext != ".html" else "page"
        elif ext in (".log", ".out", ".err"):
            role = "log"
        elif ext == ".txt":
            role = "log" if PROGRESS.search(text[:200000]) or re.search(r"\d{2}:\d{2}:\d{2}", text[:5000]) else "report"
        elif ext == ".bib":
            role = "bib"
        elif not ext and text.lstrip()[:1] in ("{", "["):
            try:
                role, extra = json_facts(rel, json.loads(text), facts)
            except ValueError:
                role = "other_text"
        else:
            role = "other_text"
        doc = role in ("report", "page", "notebook", "bib")
        if role not in ("result", "result_table", "config", "manifest", "data", "broken_json"):
            line_facts(text, facts, doc)
        if role in ("launcher", "log", "other_text"):
            # The first lines of a log usually echo the launch command (Hydra `a.b=c` overrides, `--flag value`):
            # the effective settings of this run, which an auditor compares across replicate runs.
            head = [l.strip()[:400] for l in text.splitlines()[:40] if l.strip()][:8]
            if head:
                facts["head"] = [redact(h) for h in head[:5]]
            args = launch_args("\n".join(head + [c[1] for c in facts.get("cmds", [])][:5]))
            if args:
                facts["launch_args"] = args
        if role == "launcher" or role == "log":
            joined = "\n".join(c[1] for c in facts.get("cmds", []))
            facts["writes"] = sorted(set(WRITE_FLAG.findall(joined)))[:60]
            facts["reads"] = sorted(set(READ_FLAG.findall(joined)))[:60]
            if role == "launcher":
                redirects = re.findall(r"(?:>>?|tee(?:\s+-a)?)\s+([^\s;&|]+)", text)
                facts["writes"] = sorted(set(facts["writes"] + redirects))[:80]
        refs, ids, dates = refs_and_ids(text + "\n" + extra, rel)
        facts["refs"], facts["ids"], facts["dates"] = refs, ids, dates
        pc = path_config(rel)
        if pc:
            facts["path_config"] = pc
        title = ""
        for line in text.splitlines()[:30]:
            if line.strip():
                title = line.strip().lstrip("#").strip()[:160]
                break
        facts["title"] = redact(title)
        # Human-written prose (reports, READMEs, notes, launchers) is what the agent must read to name things;
        # keep it (redacted, capped) so reading and phrase search work even when the source mount is sick.
        if ((doc or role in ("launcher", "other_text") or re.search(r"(readme|notes?|handoff|protocol|status|plan|final|summary|results|live|aggregate|coverage|manifest)", os.path.basename(rel), re.I))
                and len(raw) <= LIMITS["text_bytes"]) or (len(raw) <= SMALL_TEXT and ext in SMALL_TEXT_EXT):
            # small logs, queues, env/requirements files, short JSON/CSV: grep over the index is then exhaustive
            facts["text"] = redact(text)
    except RecursionError:
        rec.update(st="error", r="recursion")
        return rec
    rec.update(st="parsed", role=role, f=facts)
    return rec


SMALL_TEXT = 64 * 1024
BIG_STRUCTURED = 48 * 1024 * 1024  # coverage / results JSON and CSV tables are worth parsing even when large
SMALL_TEXT_EXT = {".txt", ".log", ".out", ".err", ".md", ".yaml", ".yml", ".sh", ".py", ".cfg", ".ini", ".toml", ".csv", ".tsv",
                  ".jsonl", ".json", ".sha256", ".md5", ".sum", ".lst", ".list", ".env", ".rst", ".tex"}


def _tally(path, cap=20000, seconds=10.0):
    """File count and bytes under a skipped folder (bounded: huge caches report a lower bound)."""
    n = b = 0
    t0 = time.time()
    for base, dirs, names in os.walk(path):
        for nm in names:
            n += 1
            try:
                b += os.lstat(os.path.join(base, nm)).st_size
            except OSError:
                pass
        if n >= cap or time.time() - t0 > seconds:
            return {"files": n, "bytes": b, "complete": False}
    return {"files": n, "bytes": b, "complete": True}


def walk(root, excludes, deadline):
    stack = [""]
    while stack:
        if deadline and time.time() > deadline:
            yield ("deadline", None, None, None)
            return
        cur = stack.pop()
        try:
            entries = list(os.scandir(os.path.join(root, cur) if cur else root))
        except OSError as exc:
            yield ("dir_error", cur, type(exc).__name__, None)
            continue
        entries.sort(key=lambda e: e.name)
        if not entries and cur:
            # "the folder is there but empty" is itself evidence (a study that was planned, cleaned or never synced)
            yield ("empty_dir", cur, None, None)
            continue
        subdirs = []
        # A person glances at a 200k-image dataset folder and moves on: summarize bulk binary directories
        # (many files, sample all non-text) instead of stat-ing every file. Sub-directories are still walked.
        files_here = [e for e in entries if not e.name.startswith(".") and e.is_file(follow_symlinks=False)]
        if len(files_here) >= BULK_MIN_FILES:
            step = max(1, len(files_here) // 300)
            sample = files_here[::step]
            exts = {}
            for e in files_here:
                x = os.path.splitext(e.name)[1].lower()
                exts[x] = exts.get(x, 0) + 1
            if all(os.path.splitext(e.name)[1].lower() not in TEXT_EXT for e in sample):
                yield ("bulk", cur, len(files_here), dict(sorted(exts.items(), key=lambda kv: -kv[1])[:8]))
                entries = [e for e in entries if not (e in files_here)]
        for e in entries:
            rel = (cur + "/" + e.name) if cur else e.name
            try:
                if e.is_symlink():
                    try:
                        target = os.readlink(os.path.join(root, rel))
                    except OSError:
                        target = None
                    yield ("symlink", rel, target, None)
                    continue
                if e.name.startswith(".nfs"):  # NFS silly-rename of a deleted-but-open file; reads can hang
                    yield ("nfs_orphan", rel, None, None)
                    continue
                if e.is_dir() and e.name == ".git":
                    # which commit a checkout is really at: a few tiny ref files, never objects or config (may hold tokens)
                    for sub in (".git/HEAD", ".git/ORIG_HEAD", ".git/FETCH_HEAD", ".git/packed-refs", ".git/logs/HEAD"):
                        fp = os.path.join(root, cur, sub) if cur else os.path.join(root, sub)
                        if os.path.isfile(fp):
                            st2 = os.stat(fp)
                            yield ("file", (cur + "/" + sub) if cur else sub, st2.st_size, st2.st_mtime)
                    for base, _, names in os.walk(os.path.join(root, cur, ".git", "refs") if cur else os.path.join(root, ".git", "refs")):
                        for nm in names[:200]:
                            fp = os.path.join(base, nm)
                            relp = os.path.relpath(fp, root).replace(os.sep, "/")
                            st2 = os.stat(fp)
                            yield ("file", relp, st2.st_size, st2.st_mtime)
                    yield ("skip_dir", rel, json.dumps({**_tally(os.path.join(root, rel)), "note": "git objects not read"}), None)
                    continue
                if e.is_dir():
                    if e.name in SKIP_DIRS or any(re.search(x, rel) for x in excludes):
                        # not read, but counted: "how many files are in X" must stay answerable
                        yield ("skip_dir", rel, json.dumps(_tally(os.path.join(root, rel))), None)
                    else:
                        subdirs.append(rel)
                    continue
                st = e.stat()
            except OSError as exc:
                yield ("stat_error", rel, type(exc).__name__, None)
                continue
            yield ("file", rel, st.st_size, st.st_mtime)
        stack.extend(reversed(subdirs))


def load_previous(paths):
    prev = {}
    for p in paths:
        opener = gzip.open if p.endswith(".gz") else open
        try:
            with opener(p, "rt", encoding="utf-8") as fh:
                for line in fh:
                    try:
                        r = json.loads(line)
                    except ValueError:
                        continue  # a torn final line from an interrupted run
                    if r.get("t") == "meta" and r.get("probe_version") not in RESUME_COMPATIBLE:
                        break  # parser changed: previous facts are not reusable
                    if r.get("t") == "file" and r.get("st") in ("parsed", "metadata_only", "too_large", "skipped"):
                        prev[r["p"]] = (r["s"], r["m"])
        except (OSError, EOFError):
            pass  # an interrupted part is readable up to its last sync-flush
    return prev


def main(argv=None):
    ap = argparse.ArgumentParser(description="LabWeft read-only trace probe")
    ap.add_argument("--root", required=True)
    ap.add_argument("--out", default="-", help="output .jsonl[.gz] path or - for stdout")
    ap.add_argument("--resume-from", action="append", default=[], help="previous part files; unchanged files are skipped")
    ap.add_argument("--max-text-bytes", type=int, default=4 * 1024 * 1024)
    ap.add_argument("--max-files", type=int, default=0)
    ap.add_argument("--deadline-seconds", type=int, default=0)
    ap.add_argument("--file-timeout", type=float, default=20.0)
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--exclude", action="append", default=[], help="regex on relative directory paths")
    ap.add_argument("--status", help="small JSON status file rewritten during the run")
    a = ap.parse_args(argv)
    root = os.path.abspath(a.root)
    if a.out != "-" and os.path.abspath(a.out).startswith(root + os.sep):
        ap.error("--out must be outside the scanned root (the probe is read-only)")
    tmp = a.out + ".partial" if a.out != "-" else None
    if a.out == "-":
        out = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    elif a.out.endswith(".gz"):
        out = gzip.open(tmp, "wt", encoding="utf-8", compresslevel=6)
    else:
        out = open(tmp, "w", encoding="utf-8")
    lock = threading.Lock()

    def emit(rec):
        with lock:
            out.write(json.dumps(rec, ensure_ascii=False, separators=(",", ":"), default=str) + "\n")

    started = time.time()
    deadline = started + a.deadline_seconds if a.deadline_seconds else 0
    prev = load_previous(a.resume_from)
    emit({"t": "meta", "probe_version": PROBE_VERSION, "root": root, "host": socket.gethostname(),
          "started": started, "python": sys.version.split()[0], "resume_parts": len(a.resume_from),
          "limits": {"max_text_bytes": a.max_text_bytes, "max_files": a.max_files, "excludes": a.exclude}})
    stats = {"files": 0, "bytes": 0, "parsed": 0, "unchanged": 0, "timeouts": 0, "by_status": {}, "by_kind": {}, "by_role": {},
             "skipped_dirs": 0, "errors": 0, "complete": True, "stop_reason": None}
    started_at = {}
    stuck = [0]
    pools = [ThreadPoolExecutor(max_workers=max(1, a.workers))]

    def work(rel, size, mtime):
        started_at[rel] = time.time()
        try:
            return analyze(root, rel, size, mtime, a.max_text_bytes)
        finally:
            started_at.pop(rel, None)

    pending = {}

    def drain(block):
        if not pending:
            return
        done, _ = wait(list(pending), timeout=a.file_timeout if block else 0, return_when=FIRST_COMPLETED)
        now = time.time()
        for fut in done:
            rel, _ = pending.pop(fut)
            try:
                rec = fut.result()
            except Exception as exc:  # parser bugs must not kill a long scan
                rec = {"t": "file", "p": rel, "st": "error", "r": "parser:" + type(exc).__name__}
            st = rec.get("st")
            stats["by_status"][st] = stats["by_status"].get(st, 0) + 1
            stats["by_kind"][rec.get("k", "?")] = stats["by_kind"].get(rec.get("k", "?"), 0) + 1
            if rec.get("role"):
                stats["by_role"][rec["role"]] = stats["by_role"].get(rec["role"], 0) + 1
            stats["parsed"] += st == "parsed"
            for m in rec.pop("members", []):
                stats["archive_members"] = stats.get("archive_members", 0) + 1
                emit(m)
            emit(rec)
        for fut, (rel, _) in list(pending.items()):
            t0 = started_at.get(rel)
            if t0 is not None and now - t0 > a.file_timeout:
                pending.pop(fut)
                stats["timeouts"] += 1
                stats["by_status"]["timeout"] = stats["by_status"].get("timeout", 0) + 1
                emit({"t": "file", "p": rel, "st": "timeout", "r": "file_timeout"})
                stuck[0] += 1
                if stuck[0] >= max(1, a.workers // 2):
                    # Stuck reader threads never come back; give new work a fresh pool and re-queue waiting files.
                    old_pool = pools[0]
                    pools[0] = ThreadPoolExecutor(max_workers=max(1, a.workers))
                    for f2, (rel2, info) in list(pending.items()):
                        if rel2 not in started_at and f2.cancel():
                            pending.pop(f2)
                            pending[pools[0].submit(work, rel2, *info)] = (rel2, info)
                    old_pool.shutdown(wait=False)
                    stuck[0] = 0

    last_status = 0
    for kind, rel, size, mtime in walk(root, a.exclude, deadline):
        if kind == "deadline":
            stats["complete"], stats["stop_reason"] = False, "deadline"
            break
        if kind == "bulk":
            stats["bulk_dirs"] = stats.get("bulk_dirs", 0) + 1
            stats["bulk_files"] = stats.get("bulk_files", 0) + size
            emit({"t": "bulk", "p": rel, "n": size, "exts": mtime})
            continue
        if kind != "file":
            if kind == "skip_dir":
                stats["skipped_dirs"] += 1
            emit({"t": "skip", "kind": kind, "p": rel, "r": size})
            continue
        stats["files"] += 1
        stats["bytes"] += size
        if a.max_files and stats["files"] > a.max_files:
            stats["complete"], stats["stop_reason"] = False, "max_files"
            break
        if prev.get(rel) == (size, int(mtime)):
            stats["unchanged"] += 1
            emit({"t": "same", "p": rel})
        else:
            pending[pools[0].submit(work, rel, size, mtime)] = (rel, (size, mtime))
            while len(pending) >= a.workers * 4:
                drain(True)
            drain(False)
        if a.status and time.time() - last_status > 10:
            last_status = time.time()
            with lock:
                out.flush()  # gzip sync-flush: an interrupted part stays readable up to here
            with open(a.status + ".tmp", "w") as fh:
                json.dump({"running": True, "elapsed": round(time.time() - started, 1), **stats}, fh)
            os.replace(a.status + ".tmp", a.status)
    while pending:
        drain(True)
    stats["elapsed"] = round(time.time() - started, 1)
    emit({"t": "end", "stats": stats})
    out.flush()
    if a.out != "-":
        out.close()
        os.replace(tmp, a.out)
    if a.status:
        with open(a.status + ".tmp", "w") as fh:
            json.dump({"running": False, **stats}, fh)
        os.replace(a.status + ".tmp", a.status)
    pools[0].shutdown(wait=False)
    sys.stdout.flush()
    os._exit(0)  # do not wait for reader threads stuck on a hung NFS file


if __name__ == "__main__":
    main()
