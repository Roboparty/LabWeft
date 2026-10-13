"""Evidence obligations for recorded research semantics, and reviewable patch proposals.

`obligations` audits the store the way REA audits a reconstruction: each claim/run must close concrete
obligations (evidence exists, locator resolves, printed numbers appear in the cited bytes, replication,
comparator). Diagnostics have stable codes; `unknown` never aggregates to `ready`.
`propose` turns a recovered study into a draft Cell/Run patch with evidence locators filled in. It is a
proposal for the agent to read and edit, never an automatic commit.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from collections import Counter

from ..store import Store, stable_id

NUM = re.compile(r"(?<![\w.])[-+]?\d+\.\d+(?![\d.])")


def _resolve_json(doc, locator: str):
    if not locator.startswith("$"):
        raise KeyError("not a JSON locator")
    cur = doc
    for name, idx in re.findall(r"\.([^.\[\]]+)|\[(\d+)\]", locator[1:]):
        if name:
            cur = cur[name]
        else:
            cur = cur[int(idx)]
    return cur


def resolve_locator(text: str, locator: str | None):
    """Return (status, value). status: resolved | unresolved | free_text."""
    if not locator:
        return "free_text", None
    loc = locator.strip()
    m = re.fullmatch(r"(?:lines?\s*)?(\d+)\s*(?:-|–|to)\s*(\d+)", loc, re.I) or re.fullmatch(r"lines?\s*(\d+)", loc, re.I)
    lines = text.splitlines()
    if m:
        a = int(m.group(1))
        b = int(m.group(2)) if m.lastindex and m.lastindex >= 2 else a
        if 1 <= a <= b <= len(lines):
            return "resolved", "\n".join(lines[a - 1:b])
        return "unresolved", None
    if loc.startswith("$"):
        try:
            return "resolved", _resolve_json(json.loads(text), loc)
        except (KeyError, IndexError, TypeError, ValueError):
            return "unresolved", None
    m = re.fullmatch(r"row:(\d+)(?:,col:(.+))?", loc)
    if m:
        rows = list(csv.reader(io.StringIO(text)))
        r = int(m.group(1))
        if not 1 <= r <= len(rows):
            return "unresolved", None
        if m.group(2) is None:
            return "resolved", rows[r - 1]
        header = rows[0]
        if m.group(2) not in header:
            return "unresolved", None
        row = rows[r - 1]
        i = header.index(m.group(2))
        return ("resolved", row[i]) if i < len(row) else ("unresolved", None)
    return "free_text", None


def _printed(text: str, number: str) -> bool:
    dec = len(number.split(".")[1]) if "." in number else 0
    x = float(number)
    tol = 0.5 * 10 ** (-dec) + 1e-12
    for tok in re.findall(r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?", text):
        try:
            v = float(tok)
        except ValueError:
            continue
        for scale in (1.0, 100.0, 0.01):
            if abs(v * scale - x) <= tol:
                return True
    return False


def obligations(workspace, kinds=("claim", "run", "cell"), offset: int = 0, limit: int = 50) -> dict:
    store = Store(workspace)
    state = store.load()
    nodes, files, edges = state["nodes"], state["files"], state["edges"]
    compared = {e["source"] for e in edges.values() if e["relation"] == "compares"} | {e["target"] for e in edges.values() if e["relation"] == "compares"}
    children = Counter(n.get("parent_id") for n in nodes.values() if n["kind"] == "run" and n.get("status") == "completed")
    blob_cache: dict[str, str] = {}

    def blob(sha):
        if sha not in blob_cache:
            try:
                blob_cache[sha] = store.read_blob(sha)
            except Exception:
                blob_cache[sha] = None
        return blob_cache[sha]
    items = []
    for n in nodes.values():
        if n["kind"] not in kinds or n.get("status") == "archived":
            continue
        diags = []
        refs = n.get("evidence", [])
        if not refs:
            diags.append({"code": "missing-evidence", "detail": "no direct immutable source snapshot"})
        cited_text = []
        for ref in refs:
            f = files.get(ref["file_id"], {})
            if f.get("missing") or f.get("sha256") != ref["sha256"]:
                diags.append({"code": "source-drift", "detail": f.get("path"), "file_id": ref["file_id"]})
            text = blob(ref["sha256"])
            if text is None:
                diags.append({"code": "snapshot-unreadable", "detail": ref["sha256"][:12]})
                continue
            st, val = resolve_locator(text, ref.get("locator"))
            if st == "unresolved":
                diags.append({"code": "locator-unresolved", "detail": f"{f.get('path')} :: {ref.get('locator')}"})
            cited_text.append(json.dumps(val, default=str) if st == "resolved" else text)
        attrs = n.get("attrs", {})
        if n["kind"] == "claim":
            finding = attrs.get("finding") or {}
            card = attrs.get("finding_card") or {}
            printed = " ".join([n.get("label", ""), (finding.get("estimate") or "") if isinstance(finding.get("estimate"), str) else json.dumps(finding.get("estimate", "")),
                                card.get("en", {}).get("value", "") if isinstance(card.get("en"), dict) else ""])
            unsourced = [x for x in dict.fromkeys(NUM.findall(printed)) if refs and not any(_printed(t, x) for t in cited_text)]
            if unsourced:
                diags.append({"code": "value-not-in-cited-evidence", "detail": unsourced[:6],
                              "hint": "the number may be derived (mean/SD/difference); cite the per-seed source or record the derivation"})
            if finding.get("priority") in ("primary", "secondary"):
                if not attrs.get("scope"):
                    diags.append({"code": "missing-scope"})
                if finding.get("type") == "effect" and n["id"] not in compared and not finding.get("comparison"):
                    diags.append({"code": "missing-comparator", "detail": "effect without a compares edge or finding.comparison"})
            if n.get("status") == "accepted" and not n.get("confirmation"):
                diags.append({"code": "unconfirmed-acceptance"})
        elif n["kind"] == "run":
            if n.get("status") == "completed" and not attrs.get("metrics"):
                diags.append({"code": "completed-without-metrics"})
            if attrs.get("seed") is None:
                diags.append({"code": "unknown-seed"})
            if not attrs.get("eval_protocol"):
                diags.append({"code": "unknown-eval-protocol"})
            resolved_nums = []
            for t in cited_text:
                try:
                    v = json.loads(t)
                except ValueError:
                    v = t
                try:
                    resolved_nums.append(float(str(v).strip().strip('"').rstrip("%")))
                except ValueError:
                    pass
            for key, val in (attrs.get("metrics") or {}).items():
                if not isinstance(val, (int, float)) or not refs:
                    continue
                if any(_printed(t, repr(float(val)) if "." in repr(float(val)) else f"{val}.0") for t in cited_text):
                    continue
                # Derived metric: the mean of the cited per-evaluation values (each locator resolves to one number).
                if len(resolved_nums) == len(refs) and resolved_nums and abs(sum(resolved_nums) / len(resolved_nums) - float(val)) <= 1e-6 * max(1.0, abs(float(val))):
                    diags_ok = {"code": "derived-mean-verified", "detail": f"{key}={val} = mean of {len(resolved_nums)} cited values"}
                    n.setdefault("_notes", []).append(diags_ok)
                    continue
                diags.append({"code": "metric-not-in-cited-evidence", "detail": f"{key}={val}"})
        elif n["kind"] == "cell":
            if children.get(n["id"], 0) < 2:
                diags.append({"code": "single-seed" if children.get(n["id"], 0) == 1 else "no-completed-runs",
                              "detail": f"{children.get(n['id'], 0)} completed run(s)"})
        blocking = {"missing-evidence", "source-drift", "locator-unresolved", "snapshot-unreadable", "value-not-in-cited-evidence",
                    "metric-not-in-cited-evidence", "missing-comparator", "missing-scope"}
        status = "failed" if any(d["code"] in blocking for d in diags) else ("open" if diags else "ready")
        item = {"node": n["id"], "kind": n["kind"], "label": n.get("label", "")[:120], "status": status, "diagnostics": diags}
        if n.get("_notes"):
            item["verified"] = n.pop("_notes")
        items.append(item)
    order = {"failed": 0, "open": 1, "ready": 2}
    items.sort(key=lambda x: (order[x["status"]], x["kind"], x["node"]))
    summary = Counter(x["status"] for x in items)
    codes = Counter(d["code"] for x in items for d in x["diagnostics"])
    nxt = offset + limit if offset + limit < len(items) else None
    return {"status": "ready" if items and summary["ready"] == len(items) else ("open" if items else "unknown"),
            "summary": dict(summary), "by_code": dict(codes.most_common()),
            "obligations": {"total": len(items), "offset": offset, "next_offset": nxt, "items": items[offset:offset + limit]},
            "limitations": ["numbers are matched at printed precision (also x100 / /100)", "free-text locators are not verifiable"]}


def propose(workspace, alias: str, study: dict, cells: list[dict], parent_id: str, eval_protocol: str | None = None) -> dict:
    """Draft patch for one recovered study. Evidence must already be synced into the store (see `trace fetch`)."""
    store = Store(workspace)
    state = store.load()
    by_path = {(f.get("source"), f.get("path")): f for f in state["files"].values() if not f.get("missing")}
    missing = set()

    def ref(path, locator):
        f = by_path.get((alias, path))
        if not f or not f.get("sha256"):
            missing.add(path)
            return None
        return {"file_id": f["id"], "sha256": f["sha256"], "locator": locator}
    qid = stable_id("question", state["project"]["id"], study["id"])
    treat = [f["key"] for f in study["factors"] if f.get("role") == "treatment"]
    nodes = [{"id": qid, "kind": "question", "label": f"Effect of {', '.join(treat) or 'conditions'} on {study['primary_metric']} (draft)",
              "parent_id": parent_id, "status": "provisional",
              "description": f"Recovered by `labweft trace experiments` from {study['source']}: {study['units']} {study['unit']}s, "
                             f"{study['cells']} conditions. Factor authorities: "
                             + ", ".join(f"{f['key']}={f['authority']}" for f in study["factors"]) + ". Agent must confirm meaning and protocol.",
              "attrs": {"trace": {"study": study["id"], "controlled_axes": study["controlled_axes"], "constant_config": study["constant_config"]}}}]
    edges = []
    protocol = eval_protocol or "UNKNOWN-confirm-before-compare"
    for c in cells:
        cid = stable_id("cell", state["project"]["id"], study["id"], c["id"])
        cfg = {k: v for k, v in c["levels"].items()}
        cfg["eval_protocol"] = protocol
        label = ", ".join(f"{k}={v}" for k, v in c["levels"].items()) or "all units"
        runs = [r for r in c["runs"] if r.get("value") is not None]
        cell_refs = [x for x in (ref(r["source"], r["locator"]) for r in runs[:1]) if x]
        # One Run = one independent training seed. Evaluation-seed rows of the same training seed are averaged
        # (and all of them cited), never counted as extra replicates.
        train_keys = [k for k in (study.get("replicate_keys") or []) if not re.search(r"eval", k, re.I)]
        eval_keys = [k for k in (study.get("replicate_keys") or []) if re.search(r"eval", k, re.I)]
        if eval_keys and train_keys:
            grouped: dict[str, list] = {}
            for r in runs:
                key = json.dumps({k: r["seed"].get(k) for k in train_keys}, sort_keys=True, default=str)
                grouped.setdefault(key, []).append(r)
            runs = [{"source": g[0]["source"], "locator": g[0]["locator"], "rows": g,
                     "seed": {k: g[0]["seed"].get(k) for k in train_keys},
                     "value": sum(x["value"] for x in g) / len(g), "eval_n": len(g)} for g in grouped.values()]
        nodes.append({"id": cid, "kind": "cell", "label": label[:200], "parent_id": qid, "status": "recorded",
                      "description": "Draft condition from factor recovery; seed is not a factor.", "attrs": {"config": cfg},
                      "evidence": cell_refs})
        seen_seeds = Counter()
        for r in runs:
            seed = next((v for k, v in sorted(r["seed"].items(), key=lambda kv: ("train" not in kv[0], kv[0])) if v is not None), None) if r.get("seed") else None
            seen_seeds[json.dumps(seed, default=str)] += 1
            rid = stable_id("run", state["project"]["id"], study["id"], c["id"], r["source"], str(r["locator"]))
            run_cfg = dict(cfg)
            run_cfg["seed"] = seed
            evs = [x for x in (ref(row["source"], row["locator"]) for row in r.get("rows", [r])) if x]
            ev = evs[0] if evs else None
            nodes.append({"id": rid, "kind": "run", "label": f"{label[:120]} | seed {seed}", "parent_id": cid,
                          "status": "needs_review" if seen_seeds[json.dumps(seed, default=str)] > 1 or seed is None else "completed",
                          "description": "Draft run; completion and seed identity must be verified in the cited source.",
                          "attrs": {"config": run_cfg, "seed": seed, "run_id": f"{r['source']}#{r['locator']}", "eval_protocol": protocol,
                                    "code_revision": None, "metrics": {study["primary_metric"]: round(r["value"], 6)},
                                    "seed_keys": r.get("seed"), "eval_rows_averaged": r.get("eval_n", 1)},
                          "evidence": evs})
    ids = {n["id"]: n for n in nodes}
    for ax in study["controlled_axes"]:
        for a, b in ax.get("example_pairs", []):
            s, t = stable_id("cell", state["project"]["id"], study["id"], a), stable_id("cell", state["project"]["id"], study["id"], b)
            if s in ids and t in ids:
                edges.append({"id": "edge-" + hashlib.sha256(f"{s}|{t}|compares".encode()).hexdigest()[:20], "source": s, "target": t,
                              "relation": "compares"})
    return {"patch": {"base_revision": state["revision"], "reason": f"Draft from trace study {study['id']} (review before apply)",
                      "nodes": nodes, "edges": edges},
            "missing_evidence_paths": sorted(missing),
            "next": ("run `labweft trace fetch` for the missing paths, `labweft sync`, then propose again" if missing else
                     "read the cited sources, fix labels/protocol/seed identity, then `labweft apply`")}
