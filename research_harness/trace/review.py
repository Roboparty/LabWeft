"""A review worklist: what a careful auditor must check, study by study, after `audit` (which only finds leads).

For every non-vendored report with numbers it lists the numbers nothing in the folder reproduces (by table row),
the table rows whose arithmetic fails, and the files it cites that are missing; for every replicate group it lists
the sibling sets. The agent then works through the list instead of stopping at the audit."""
from __future__ import annotations

import posixpath
import re
from collections import defaultdict

from .analyze import page, reconcile, result
from .audit import VENDORED, _table_arithmetic
from .index import fid_range


def worklist(con, scope: str | None = None, limit: int = 30, offset: int = 0) -> dict:
    rng = fid_range(con, scope) if scope else (0, 1 << 62)
    rng = rng or (0, -1)
    reports = con.execute(
        "SELECT f.path, COUNT(*) AS n FROM lines_t l JOIN files f ON f.fid = l.fid WHERE l.fid BETWEEN ? AND ? AND l.kind = 'numbers' "
        "AND f.role = 'report' AND f.ext IN ('.md', '.markdown', '.tex', '.rst', '.html') AND f.path NOT LIKE '%::%' "
        "GROUP BY f.path ORDER BY n DESC", rng).fetchall()
    reports = [r for r in reports if not VENDORED.search(r[0])]
    arith = defaultdict(list)
    for f in _table_arithmetic(con, rng):
        arith[f["files"][0]].append(f"{f['locator']}: {f['evidence'][:200]}")
    items = []
    for path, n in reports[offset: offset + limit]:
        rep = reconcile(con, path=path, limit=100000)
        entry = {"report": path, "numbers": n}
        if rep.get("status") == "found":
            doc = rep["report"]
            entry["by_state"] = doc.get("by_state")
            entry["check_rows_without_source"] = [f"{r['row'][:80]} ({r['count']} numbers, e.g. {', '.join(r['numbers'][:3])})"
                                                  for r in doc.get("unsourced_by_row", [])[:6]]
            if doc.get("mixed_sd_conventions"):
                entry["mixed_sd_conventions"] = doc["mixed_sd_conventions"]
        if arith.get(path):
            entry["table_arithmetic_fails"] = arith[path]
        missing = [r[0] for r in con.execute(
            "SELECT DISTINCT t.raw FROM refs_t t JOIN files f ON f.fid = t.src WHERE f.path = ? AND t.target IS NULL", (path,))
            if re.search(r"\.(json|csv|jsonl|txt|md|log|png|pdf)$", r[0].strip("`'\" "))][:6]
        if missing:
            entry["cited_files_not_found"] = missing
        entry["todo"] = ("read the report; for each table/claim, open the raw files it summarises and recompute "
                         "(means over the stated set, deltas and relative changes against the right base, SD convention, "
                         "p-values from counts, n vs listed items, units); compare with sibling documents")
        items.append(entry)
    return result("found" if items else "not_found", con, scope=scope, reports_total=len(reports),
                  worklist=page(items, 0, len(items)), next_offset=offset + limit if offset + limit < len(reports) else None,
                  limitations=["ordered by how many numbers a report prints; vendored copies (source/, third_party/) skipped",
                               "unsourced = nothing indexed reproduces the number; it is a place to look, not an error"])
