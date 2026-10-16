"""Verify an agent-written semantic research map against the project itself.

Every `path:line` (or `path:a-b`, `archive.tgz::member:line`) must exist, and every number the map states with a
`source` must actually be printed at that place (same value at the printed precision, also x100 / /100). The result
is a per-item status the HTML view shows next to each claim and result, so a reader sees which statements the tool
checked and which still rest on the agent's reading alone."""
from __future__ import annotations

import re
import shlex
import subprocess
from collections import Counter, defaultdict
from pathlib import Path

from ..store import HarnessError
from . import index, navigate, source

LOC = re.compile(r"^(?P<path>.+?):(?P<a>\d+)(?:\s*[-–]\s*(?P<b>\d+))?\s*$")
NUM = re.compile(r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?")
THOUSANDS = re.compile(r"(?<=\d),(?=\d{3}(?!\d))")


def _nums(text: str) -> list:
    t = text.replace("−", "-")
    csv_like = "|" not in t and ", " not in t and t.count(",") >= 3
    if not csv_like:  # prose and markdown tables write "3,276"; in CSV rows commas separate cells
        t = THOUSANDS.sub("", t)
    return NUM.findall(t)


def parse(loc: str):
    loc = (loc or "").strip()
    m = LOC.match(loc)
    if not m:
        return loc, None, None
    a = int(m.group("a"))
    return m.group("path"), a, int(m.group("b") or a)


def _texts(con, ws: Path, name: str, paths: set) -> dict:
    """Full text lines of each path as it is NOW on the host (batched; a map written after the scan cites the live
    file), the index snapshot only when the host cannot be read."""
    out = {}
    live = []
    for p in paths:
        if "::" in p:
            try:
                r = source.read_archive_member(ws, name, p, start=1, lines=800)
                out[p] = [x["text"] for x in r["lines"]]
            except HarnessError:
                out[p] = None
        else:
            live.append(p)
    if live:
        cfg = source.load(ws, name)
        for i in range(0, len(live), 40):
            chunk = live[i:i + 40]
            script = "; ".join(f"echo '@@@FILE {j}'; timeout 20 head -c 2000000 -- {shlex.quote(p)} 2>/dev/null" for j, p in enumerate(chunk))
            cmd = f"cd {shlex.quote(cfg['root'])} && {script}; echo '@@@END'"
            try:
                if cfg.get("host"):
                    _, raw = source._remote(cfg, cmd, 300, "map evidence read")
                else:
                    raw = subprocess.run(["bash", "-c", cmd], capture_output=True, timeout=300).stdout
            except (HarnessError, subprocess.TimeoutExpired):
                continue
            parts = re.split(r"^@@@FILE (\d+)$", raw.decode("utf-8", errors="replace"), flags=re.M)
            got = {}
            for k in range(1, len(parts) - 1, 2):
                got[int(parts[k])] = parts[k + 1].split("@@@END")[0].lstrip("\n")
            for j, p in enumerate(chunk):
                txt = got.get(j)
                out[p] = txt.splitlines() if txt else None
    for p in paths:
        if out.get(p) is None:
            row = con.execute("SELECT text FROM texts WHERE path = ?", (p,)).fetchone()
            if row and row[0] is not None:
                out[p] = row[0].splitlines()
    return out


def _tokens(value) -> list:
    """Numbers stated in a map value with their printed decimals ('88.56 ± 1.07' -> [(88.56,2),(1.07,2)])."""
    if isinstance(value, bool) or value is None:
        return []
    if isinstance(value, (int, float)):
        s = repr(float(value))
        d = len(s.split(".")[1].rstrip("0")) if "." in s else 0
        return [(float(value), min(d, 6))]
    out = []
    for t in NUM.findall(THOUSANDS.sub("", str(value).replace("−", "-"))):  # map values are prose
        mant = t.split("e")[0].split("E")[0]
        d = len(mant.split(".")[1]) if "." in mant else 0
        if "e" in t.lower():
            d += max(0, -int(t.lower().split("e")[1]))
        out.append((float(t), d))
    return out


def _found(x: float, d: int, lines: list) -> bool:
    tol = 0.5 * 10 ** (-d) + 1e-9
    for line in lines:
        for t in _nums(line):
            y = float(t)
            for sc in (1.0, 100.0, 0.01):
                if abs(abs(y * sc) - abs(x)) <= tol:
                    return True
                # the source prints more decimals than the map: compare at the map's precision
                if abs(round(abs(y * sc), d) - abs(x)) <= tol:
                    return True
    return False


def _columns(lines: list) -> list:
    rows = []
    for line in lines:
        cells = re.split(r"[,\t|]", line)
        rows.append([float(c.strip().strip("*% ")) if re.fullmatch(r"\s*\**\s*[-+]?\d+(?:\.\d+)?\s*%?\s*\**\s*", c) else None
                     for c in cells])
    width = max((len(r) for r in rows), default=0)
    return [[r[c] for r in rows if c < len(r) and r[c] is not None] for c in range(width)], [
        [r[c] if c < len(r) else None for r in rows] for c in range(width)]


def _derived(x: float, d: int, lines: list, sd: tuple | None = None) -> bool:
    """The number is an aggregate of a table printed there. A single value must be the mean / SD of 2-5 CONSECUTIVE
    rows of one column; a `mean ± SD` pair may use any 2-5 rows (replicates are often interleaved with other
    conditions) because matching both numbers at once is not a coincidence."""
    import math
    from itertools import combinations
    tol = 0.5 * 10 ** (-d) + 1e-9
    compact, full = _columns(lines)
    def stats(seg):
        k = len(seg)
        m = sum(seg) / k
        ss = sum((v - m) ** 2 for v in seg)
        return m, math.sqrt(ss / (k - 1)), math.sqrt(ss / k)
    if sd is not None:
        y, dy = sd
        tol_sd = 0.5 * 10 ** (-dy) + 1e-9
        for vals in compact:
            for k in range(2, 6):
                for seg in combinations(vals[:14], k):
                    if _match_stats(list(seg), [(x, d), sd]):
                        return True
        return False
    for vals in full:
        for i in range(len(vals)):
            for k in range(2, 6):
                seg = vals[i:i + k]
                if len(seg) < k or any(v is None for v in seg):
                    continue
                for cand in stats(seg)[:1]:  # a lone number is a mean; an SD is only checked with its mean
                    for sc in (1.0, 100.0):
                        if abs(cand * sc - x) <= tol:
                            return True
    return False


SEED_TOKEN = re.compile(r"(?i)(?<![a-z0-9])(s|seed[_-]?|train_seed[_-]?|eval_seed[_-]?)(\d+)(?![0-9])")
PAIR = re.compile(r"([-+]?\d+(?:\.\d+)?)\s*(?:±|\+/-|\+-)\s*(\d+(?:\.\d+)?)")
KEYVAL = re.compile(r'^\s*"?([A-Za-z_][\w .%/-]*?)"?\s*[:=]\s*([-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)\s*,?\s*$')


def _decimals(v: float) -> int:
    r = repr(float(v))
    return len(r.split(".")[1].rstrip("0")) if "." in r and "e" not in r else 0


def _match_stats(vals: list, toks: list) -> bool:
    """`toks` (value[, SD]) are the mean[/SD] of `vals` at the printed precision (also x100). Authors compute the SD
    from unrounded values, so the SD may also differ by the rounding of the printed inputs."""
    import math
    if len(vals) < 2 or not toks:
        return False
    k = max(_decimals(v) for v in vals)
    in_tol = 0.5 * 10 ** (-k) if k else 0.0
    m = sum(vals) / len(vals)
    ss = sum((v - m) ** 2 for v in vals)
    sds = (math.sqrt(ss / (len(vals) - 1)), math.sqrt(ss / len(vals)))
    (x, d), rest = toks[0], toks[1:]
    for sc in (1.0, 100.0):
        if abs(m * sc - x) > 0.5 * 10 ** (-d) + 1e-9:
            continue
        if not rest:
            return True
        y, dy = rest[0]
        if any(abs(sd * sc - y) <= 0.5 * 10 ** (-dy) + 1.3 * in_tol * sc + 1e-9 for sd in sds):
            return True
    return False


def _cells(line: str) -> list:
    if "|" in line:
        return [c.strip() for c in line.strip().strip("|").split("|")]
    return [c.strip() for c in re.split(r"\t|,", line)]


def _seed_rows(lines: list, a: int, toks: list) -> bool:
    """Mean (± SD) over the seed replicates of the cited table row: rows anywhere in the file whose identifying cells
    equal the cited row's once seed numbers are masked (replicates are often interleaved with other settings)."""
    if not a or a > len(lines):
        return False
    header = _cells(lines[0]) if lines else []
    seed_cols = {i for i, h in enumerate(header) if re.search(r"seed", h, re.I)}

    def key(line):
        cells = _cells(line)
        out = []
        for i, c in enumerate(cells):
            if i in seed_cols:
                continue
            if re.fullmatch(r"[-+]?\d+\.\d+%?|\**[-+]?\d+\.\d+\**", c):
                break  # measurements start at the first decimal cell
            out.append(SEED_TOKEN.sub(lambda m: m.group(1) + "#", c))
        return tuple(out), cells
    k0, row0 = key(lines[a - 1])
    if len(row0) < 3 or not any(SEED_TOKEN.search(c) for c in row0) and not seed_cols:
        return False
    group = [cells for k, cells in (key(l) for l in lines[:20000]) if k == k0 and len(cells) == len(row0)]
    if not 2 <= len(group) <= 12:
        return False
    for col in range(len(row0)):
        vals = []
        for cells in group:
            t = cells[col].strip("*% ")
            if not re.fullmatch(r"[-+]?\d+(?:\.\d+)?", t):
                break
            vals.append(float(t))
        else:
            if _match_stats(vals, toks):
                return True
    return False


def _seed_siblings(con, path: str) -> list:
    """Files that differ from `path` only in one seed number (runs/x_s7/result.json -> x_s8, x_s9)."""
    out = []
    for m in SEED_TOKEN.finditer(path):
        prefix, suffix = path[:m.start(2)], path[m.end(2):]
        pat = re.compile(re.escape(prefix) + r"\d+" + re.escape(suffix) + "$")
        rows = con.execute("SELECT path FROM files WHERE path LIKE ? ESCAPE '\\' LIMIT 400",
                           (prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%",)).fetchall()
        sib = sorted({r[0] for r in rows if pat.match(r[0]) and r[0] != path})
        if 1 <= len(sib) <= 11:
            out.append(sib)
    toks = list(SEED_TOKEN.finditer(path))
    if len(toks) >= 2:  # every seed number free: training x evaluation seed grids
        pat, last = "", 0
        for m in toks:
            pat += re.escape(path[last:m.start(2)]) + r"(\d+)"
            last = m.end(2)
        pat = re.compile(pat + re.escape(path[last:]) + "$")
        prefix = path[:toks[0].start(2)]
        rows = con.execute("SELECT path FROM files WHERE path LIKE ? ESCAPE '\\' LIMIT 4000",
                           (prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%",)).fetchall()
        sib = sorted({r[0] for r in rows if pat.match(r[0]) and r[0] != path})
        if 3 <= len(sib) <= 40:
            out.append(("grid", pat, sib))
    return out


def _value_like(cited: str, lines: list, a: int):
    """The number a sibling file prints where the cited file printed its value: same key for `key: value` lines,
    else the same line if its text (numbers masked) matches."""
    kv = KEYVAL.match(cited)
    if kv:
        for line in lines:
            m = KEYVAL.match(line)
            if m and m.group(1) == kv.group(1):
                return [float(m.group(2))]
        return None
    if kv is None and a and a <= len(lines) and NUM.sub("#", lines[a - 1]) == NUM.sub("#", cited):
        return [float(x) for x in _nums(lines[a - 1])]
    return None


def _seed_derived(con, ws, name, path, lines, a, b, toks, cache):
    """The stated value is a mean (± SD) over seed replicates: of interleaved rows in the cited table, or of the
    same field in sibling files that differ from the cited one only in a seed number."""
    for i in range(a, min(b, a + 3) + 1):
        if _seed_rows(lines, i, toks):
            return "seed_rows"
    for i in range(a, min(b, a + 3) + 1):
        if i > len(lines):
            break
        cited = lines[i - 1]
        v0 = _value_like(cited, lines, i)
        if not v0:
            continue
        for sibs in _seed_siblings(con, path):
            grid = isinstance(sibs, tuple)
            pat, files = (sibs[1], sibs[2]) if grid else (None, sibs)
            need = {p for p in files if p not in cache}
            if need:
                cache.update(_texts(con, ws, name, need))
            vals = [(path, v0)]
            for p in files:
                v = _value_like(cited, cache.get(p) or [], i)
                if v and len(v) == len(v0):
                    vals.append((p, v))
            if len(vals) < 2:
                continue
            for pos in range(len(v0)):
                if not grid:
                    if _match_stats([v[pos] for _, v in vals], toks):
                        return f"seed_files:{len(vals)}"
                    continue
                groups = [pat.match(p).groups() for p, _ in vals]
                varying = [k for k in range(len(groups[0])) if len({g[k] for g in groups}) > 1]
                if len(varying) < 2:
                    continue
                outer = {}
                for (p, v), g in zip(vals, groups):  # mean over the inner (evaluation) seeds of each outer (training) seed
                    outer.setdefault(g[varying[0]], []).append(v[pos])
                means = [sum(x) / len(x) for x in outer.values()]
                if len(means) >= 2 and len({len(x) for x in outer.values()}) == 1 and _match_stats(means, toks):
                    return f"seed_grid:{len(means)}x{len(vals) // len(means)}"
    return None


def verify(ws: Path, name: str, sem: dict, slack: int = 2) -> dict:
    ws = Path(ws)
    con = index.connect(ws, name)
    root = source.load(ws, name).get("root")
    items = []
    for c in sem.get("claims", []):
        for loc in c.get("evidence", []):
            items.append(("evidence", f"claim {c.get('id')}", loc, None))
        for n in c.get("numbers", []):
            items.append(("number", f"claim {c.get('id')}", n.get("source"), n.get("value")))
    for e in sem.get("experiments", []):
        for loc in e.get("evidence", []):
            items.append(("evidence", f"experiment {e.get('id')}", loc, None))
        for r in e.get("results", []):
            vals = [r.get("value")] + ([r.get("sd")] if r.get("sd") is not None else [])
            items.append(("number", f"experiment {e.get('id')} / {r.get('condition')}", r.get("source"), vals))
    for key in ("phases", "invalidated", "open_questions"):
        for x in sem.get(key, []):
            for loc in x.get("evidence", []):
                items.append(("evidence", key, loc, None))
    resolved = {}
    for _, _, loc, _ in items:
        if not loc:
            continue
        p, _, _ = parse(loc)
        if p in resolved:
            continue
        q = p if "::" in p else navigate.resolve_links(con, p, root)[0]
        exists = (con.execute("SELECT 1 FROM files WHERE path = ?", (q,)).fetchone() is not None
                  or con.execute("SELECT 1 FROM skips WHERE path = ?", (q,)).fetchone() is not None)
        resolved[p] = (q, exists)
    # files written after the scan are not in the index but exist on the host: read every cited path live
    texts = _texts(con, ws, name, {q for q, _ in resolved.values()})
    for p, (q, ok) in list(resolved.items()):
        if not ok and texts.get(q) is not None:
            resolved[p] = (q, True)
    sib_texts = {}
    results = []
    for kind, where, loc, vals in items:
        st = {"kind": kind, "where": where, "locator": loc}
        if not loc:
            st["status"] = "no_source"
        else:
            p, a, b = parse(loc)
            q, exists = resolved[p]
            lines = texts.get(q) if exists else None
            if not exists:
                st["status"] = "path_missing"
            elif lines is None:
                st["status"] = "unreadable"
            elif a is not None and (a < 1 or a > len(lines) + 1):
                st["status"] = "line_out_of_range"
                st["file_lines"] = len(lines)
            elif kind == "number" and vals is not None:
                window = lines[max(0, a - 1 - slack): b + slack] if a else lines
                toks = [t for v in (vals if isinstance(vals, list) else [vals]) for t in _tokens(v)]
                miss = [x for x, d in toks if not _found(x, d, window)]
                wide = lines[max(0, a - 1 - 6): b + 6] if a else lines
                derived = []
                if len(toks) == 2 and miss:  # mean ± SD stated together: match them as a pair
                    near = lines[max(0, a - 2): b + 1] if a else lines
                    if _derived(toks[0][0], toks[0][1], near if len(near) <= 14 else wide, sd=toks[1]):
                        derived = [t[0] for t in toks]
                else:
                    derived = [x for x, d in toks if x in miss and _derived(x, d, wide)]
                miss = [x for x in miss if x not in derived]
                if miss and a and 1 <= len(toks) <= 2:
                    how = _seed_derived(con, ws, name, q, lines, a, b, toks, sib_texts)
                    if how:
                        derived, miss = [t[0] for t in toks], []
                        st["derived_from"] = how
                if miss and a and len(toks) > 2:
                    # several `mean ± SD` pairs in one value ("71.14 ± 45.80 / 97.42 ± 0.22"): check pair by pair
                    for v in (vals if isinstance(vals, list) else [vals]):
                        for m_, s_ in PAIR.findall(THOUSANDS.sub("", str(v or ""))):
                            pair = _tokens(m_) + _tokens(s_)
                            if not any(x in miss for x, _ in pair):
                                continue
                            if _derived(pair[0][0], pair[0][1], lines[max(0, a - 1): b + 1], sd=pair[1]) \
                                    or _seed_derived(con, ws, name, q, lines, a, b, pair, sib_texts):
                                derived += [x for x, _ in pair]
                                miss = [x for x in miss if x not in (pair[0][0], pair[1][0])]
                                st["derived_from"] = "mean_sd_pairs"
                st["status"] = ("ok" if not derived else "ok_derived") if toks and not miss else ("number_not_at_source" if toks else "no_number")
                if miss:
                    st["missing"] = miss[:4]
            else:
                st["status"] = "ok"
        results.append(st)
    con.close()
    counts = Counter(r["status"] for r in results)
    by_kind = defaultdict(Counter)
    for r in results:
        by_kind[r["kind"]][r["status"]] += 1
    return {"status": "found", "checked": len(results), "summary": dict(counts),
            "by_kind": {k: dict(v) for k, v in by_kind.items()},
            "problems": [r for r in results if r["status"] not in ("ok", "ok_derived")][:300], "results": results}


def _verdict(sts: list) -> str:
    if not sts:
        return "unchecked"
    bad = [s for s in sts if s in ("path_missing", "line_out_of_range", "number_not_at_source")]
    if not bad:
        return "verified" if all(s in ("ok", "ok_derived") for s in sts) else "partly"
    return "problem" if len(bad) == len(sts) else "partly"


def annotate(sem: dict, check: dict) -> dict:
    """Attach `_check` to claims, their numbers, experiments and result rows (same order as verify built them)."""
    it = iter(check["results"])

    def take(n):
        return [next(it) for _ in range(n)]
    for c in sem.get("claims", []):
        ev = take(len(c.get("evidence", [])))
        nums = take(len(c.get("numbers", [])))
        for n, r in zip(c.get("numbers", []), nums):
            n["_check"] = r["status"]
        c["_check"] = _verdict([r["status"] for r in ev + nums])
    for e in sem.get("experiments", []):
        ev = take(len(e.get("evidence", [])))
        rs = take(len(e.get("results", [])))
        for row, r in zip(e.get("results", []), rs):
            row["_check"] = r["status"]
        e["_check"] = _verdict([r["status"] for r in ev + rs])
    sem["_check_summary"] = {"checked": check["checked"], **check["summary"]}
    return sem
