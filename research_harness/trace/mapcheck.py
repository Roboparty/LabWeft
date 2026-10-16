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
THOUSANDS = re.compile(r"(?<=\d),(?=\d{3}\b)")


def _nums(text: str) -> list:
    t = text.replace("−", "-")
    if t.count(",") < 3:  # prose "3,276 jobs"; never inside CSV rows, where commas separate cells
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
    for t in _nums(str(value)):
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
        rows.append([float(c) if re.fullmatch(r"\s*[-+]?\d+(?:\.\d+)?\s*", c) else None for c in cells])
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
                    m, s1, s0 = stats(seg)
                    for sc in (1.0, 100.0):
                        if abs(m * sc - x) <= tol and (abs(s1 * sc - y) <= tol_sd or abs(s0 * sc - y) <= tol_sd):
                            return True
        return False
    for vals in full:
        for i in range(len(vals)):
            for k in range(2, 6):
                seg = vals[i:i + k]
                if len(seg) < k or any(v is None for v in seg):
                    continue
                for cand in stats(seg):
                    for sc in (1.0, 100.0):
                        if abs(cand * sc - x) <= tol:
                            return True
    return False


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
    con.close()
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
                st["status"] = ("ok" if not derived else "ok_derived") if toks and not miss else ("number_not_at_source" if toks else "no_number")
                if miss:
                    st["missing"] = miss[:4]
            else:
                st["status"] = "ok"
        results.append(st)
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
