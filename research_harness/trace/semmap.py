"""Turn a verified semantic research map (SEMANTIC_MAP.md format) into LabWeft map nodes.

The hierarchy follows the paper, not the folder tree: experiment type (baseline / ablation / ...) -> the question an
experiment answers -> one Cell per compared condition, with its reported number and a hash-pinned link to the line it
was read from. Claims become claim nodes that the experiments supporting them point to. Every node carries the
verification status `verify-map` gave its numbers, so a reader of the map sees which values the tool found in the
source and which rest on the agent's reading alone."""
from __future__ import annotations

import hashlib
import re

from ..store import stable_id
from . import mapcheck

CHECK_TEXT = {"ok": "数字在引用行找到", "ok_derived": "由引用行的数据算出", "number_not_at_source": "引用行未找到该数字",
              "path_missing": "引用文件不存在", "line_out_of_range": "引用行号超出文件", "unreadable": "引用文件无法读取",
              "no_source": "无来源", "no_number": "未给出数字"}


def _short(text: str, n: int = 90) -> str:
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    return text if len(text) <= n else text[:n - 1].rstrip() + "…"


def _fmt(v, sd=None) -> str:
    if v is None:
        return "—"
    s = f"{v:g}" if isinstance(v, (int, float)) and not isinstance(v, bool) else str(v)
    return f"{s} ± {sd:g}" if isinstance(sd, (int, float)) and not isinstance(sd, bool) else s


def _metric_name(e: dict) -> str:
    m = (e.get("design") or {}).get("metric") or "result"
    return _short(m, 60)


def build_patch(state: dict, sem: dict, alias: str, archive_drafts: bool = True) -> dict:
    pid = state["project"]["id"]
    by_path = {f.get("path"): f for f in state["files"].values() if f.get("source") == alias and f.get("sha256") and not f.get("missing")}

    def refs(locs):
        out, seen = [], set()
        for loc in locs:
            if not loc:
                continue
            p, a, b = mapcheck.parse(loc)
            f = by_path.get(p) or by_path.get(_member_mirror(p))
            key = (p, a, b)
            if not f or key in seen:
                continue
            seen.add(key)
            out.append({"file_id": f["id"], "sha256": f["sha256"], "locator": f"line:{a}" + (f"-{b}" if b and b != a else "") if a else "file"})
        return out

    nodes, edges = [], []
    claim_ids = {}
    exps = sem.get("experiments", [])
    groups = {}
    for e in exps:
        groups.setdefault(str(e.get("type") or "实验"), []).append(e)
    module_ids = {}
    for order, (typ, es) in enumerate(groups.items()):
        mid = stable_id("module", pid, "semantic", typ)
        module_ids[typ] = mid
        valid = sum(1 for e in es if e.get("status") not in ("作废", "invalid", "invalidated"))
        nodes.append({"id": mid, "kind": "module", "label": f"{typ}实验" if not typ.endswith("实验") else typ, "parent_id": pid,
                      "status": "provisional",
                      "description": f"{len(es)} 个实验（有效 {valid}）：" + "；".join(_short(e.get("question"), 40) for e in es[:6]) + ("…" if len(es) > 6 else ""),
                      "attrs": {"semantic": {"group": typ}, "order": order}})
    for c in sem.get("claims", []):
        cid = stable_id("claim", pid, "semantic", str(c.get("id")))
        claim_ids[str(c.get("id"))] = cid
        ev = refs(list(c.get("evidence", [])) + [n.get("source") for n in c.get("numbers", [])])
        status = "recorded" if c.get("status") in ("成立", "supported") and c.get("_check") == "verified" else "provisional"
        if c.get("_check") == "problem":
            status = "needs_review"
        nums = [{"label": _short(n.get("meaning"), 60), "value": str(n.get("value"))} for n in c.get("numbers", [])[:6]]
        node = {"id": cid, "kind": "claim", "label": f"{c.get('id')} · {_short(c.get('statement'), 80)}", "parent_id": pid, "status": status,
                "description": c.get("statement", ""),
                "attrs": {"semantic": {"id": c.get("id"), "status": c.get("status"), "check": c.get("_check"),
                                       "caveats": c.get("caveats")},
                          "finding": {"priority": "primary" if ev else None, "type": "effect"} if ev else {"type": "effect"},
                          "scope": {"stated_in": "semantic map", "caveats": c.get("caveats") or ""} if ev else {}}}
        if ev:
            node["evidence"] = ev
            if nums:
                node["attrs"]["study_summary"] = {"zh": {"columns": [], "rows": [], "metrics": nums}}
        nodes.append(node)
    for e in exps:
        typ = str(e.get("type") or "实验")
        qid = stable_id("question", pid, "semantic", str(e.get("id")))
        invalid = e.get("status") in ("作废", "invalid", "invalidated")
        design = e.get("design") or {}
        metric = _metric_name(e)
        rows = [[_short(r.get("condition"), 60), _fmt(r.get("value"), r.get("sd")), str(r.get("n") or ""),
                 CHECK_TEXT.get(r.get("_check"), r.get("_check") or "")] for r in e.get("results", [])]
        ev = refs(list(e.get("evidence", [])) + [r.get("source") for r in e.get("results", [])])
        desc = "。 ".join(x.rstrip("。") for x in [
            f"结论：{e.get('finding')}" if e.get("finding") else "",
            "比较：" + "；".join(map(str, design.get("compared") or [])) if design.get("compared") else "",
            "固定：" + "；".join(map(str, design.get("fixed") or [])) if design.get("fixed") else "",
            f"重复：{design.get('seeds')}" if design.get("seeds") else "",
            f"指标：{design.get('metric')}" if design.get("metric") else ""] if x)
        q = {"id": qid, "kind": "question", "label": f"{e.get('id')} · {_short(e.get('question'), 90)}", "parent_id": module_ids[typ],
             "status": "archived" if invalid else ("needs_review" if e.get("_check") == "problem" else "provisional"),
             "description": desc,
             "attrs": {"semantic": {"id": e.get("id"), "type": typ, "status": e.get("status"), "check": e.get("_check"),
                                    "supports": e.get("supports") or []},
                       "config": {k: ("；".join(map(str, v)) if isinstance(v, list) else v) for k, v in design.items() if v}}}
        if ev:
            q["evidence"] = ev
            if rows:
                q["attrs"]["study_summary"] = {"zh": {"columns": ["条件", metric, "n", "核对"], "rows": rows, "metrics": [],
                                                      "note": e.get("finding") or ""}}
        nodes.append(q)
        first = None
        for i, r in enumerate(e.get("results", [])):
            rid = stable_id("cell", pid, "semantic", str(e.get("id")), str(i), str(r.get("condition")))
            metrics = {}
            if isinstance(r.get("value"), (int, float)) and not isinstance(r.get("value"), bool):
                metrics[metric] = r["value"]
            if isinstance(r.get("sd"), (int, float)) and not isinstance(r.get("sd"), bool):
                metrics["SD"] = r["sd"]
            if not metrics and r.get("value") is not None:
                metrics[metric] = str(r.get("value"))
            chk = r.get("_check")
            cell = {"id": rid, "kind": "cell", "label": (_short(r.get("condition"), 100) or f"{e.get('id')} 条件 {i + 1}")
                    + (f" · {_fmt(r.get('value'), r.get('sd'))}" if r.get("value") is not None else ""), "parent_id": qid,
                    "status": "archived" if invalid else ("recorded" if chk in ("ok", "ok_derived") else "needs_review"),
                    "description": "；".join(x for x in [r.get("note") or "", f"重复：{r.get('n')}" if r.get("n") else "",
                                                       f"核对：{CHECK_TEXT.get(chk, chk)}" if chk else ""] if x),
                    "attrs": {"config": {"条件": r.get("condition"), **({"重复": r.get("n")} if r.get("n") else {})},
                              "metrics": metrics, "semantic": {"experiment": e.get("id"), "check": chk, "source": r.get("source")},
                              "selection": f"来源：{r.get('source')}" if r.get("source") else ""}}
            ev_r = refs([r.get("source")])
            if ev_r:
                cell["evidence"] = ev_r
            nodes.append(cell)
            if first is None:
                first = rid
            elif i <= 12:
                edges.append(_edge(first, rid, "compares"))
        for sid in e.get("supports") or []:
            if str(sid) in claim_ids and not invalid:
                edges.append(_edge(qid, claim_ids[str(sid)], "supports"))
    edges = list({x["id"]: x for x in edges}.values())
    keep = {n["id"] for n in nodes}
    archived = 0
    if archive_drafts:
        for nid, n in state["nodes"].items():
            if nid in keep or n.get("status") == "archived" or n.get("protected"):
                continue
            draft = (n.get("attrs", {}).get("trace") or str(n.get("description", "")).startswith("Draft")
                     or n.get("attrs", {}).get("semantic"))
            if draft:
                old = dict(n)
                old["status"] = "archived"
                nodes.append(old)
                archived += 1
    return {"patch": {"base_revision": state["revision"],
                      "reason": f"Research map from the verified semantic map of {alias}: experiments as questions, conditions as cells, claims"
                                + (f"; {archived} earlier folder-derived drafts archived" if archived else ""),
                      "nodes": nodes, "edges": edges},
            "counts": {"modules": len(module_ids), "questions": len(exps), "cells": sum(len(e.get("results", [])) for e in exps),
                       "claims": len(claim_ids), "edges": len(edges), "archived_drafts": archived}}


def _member_mirror(path):
    from .tools import member_mirror
    return member_mirror(path)


def _edge(s, t, rel):
    return {"id": "edge-" + hashlib.sha256(f"{s}|{t}|{rel}".encode()).hexdigest()[:20], "source": s, "target": t, "relation": rel}
