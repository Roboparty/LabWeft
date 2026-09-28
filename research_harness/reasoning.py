"""Deterministic comparison and bounded reuse checks, NOT an autonomous scientist."""
from __future__ import annotations
from collections import Counter
import math
import statistics
from .store import canonical


def drift(state: dict) -> list[dict]:
    """Flag updated/missing sources without rewriting historical conclusions."""
    out = []
    for n in state["nodes"].values():
        for ref in n.get("evidence", []):
            f = state["files"].get(ref["file_id"], {})
            if f.get("missing") or f.get("sha256") != ref["sha256"]:
                out.append({"node_id": n["id"], "file_id": ref["file_id"],
                            "reason": "source_missing" if f.get("missing") else "source_changed",
                            "note": "Original snapshot remains evidence of the old state. Review applicability to new work; this does not automatically falsify the old result."})
    return out


def compare(state: dict, cell_ids: list[str] | None = None, metric: str | None = None) -> dict:
    cells = [n for n in state["nodes"].values() if n["kind"] == "cell" and n.get("status") != "archived"
             and (not cell_ids or n["id"] in cell_ids)]
    dirty = {item["node_id"] for item in drift(state)}
    dirty_runs = {n["id"] for n in state["nodes"].values() if n["kind"] == "run" and n["id"] in dirty}
    dirty_runs.update(n.get("parent_id") for n in state["nodes"].values()
                      if n["kind"] == "evaluation" and n.get("status") != "archived" and n["id"] in dirty)
    rows = []
    warnings = []
    if metric is None:
        selected_ids = {c["id"] for c in cells}
        metric_keys = {key for n in state["nodes"].values()
                       if n["kind"] == "run" and n.get("parent_id") in selected_ids and n.get("status") == "completed"
                       and n["id"] not in dirty_runs
                       for key in n.get("attrs", {}).get("metrics", {})}
        if "success_rate" in metric_keys:
            metric = "success_rate"
        elif len(metric_keys) == 1:
            metric = next(iter(metric_keys))
        elif metric_keys:
            metric = ""
            warnings.append("Multiple metrics are available; specify --metric to choose one before aggregating.")
        else:
            metric = "success_rate"
    for cell in cells:
        runs = [n for n in state["nodes"].values() if n["kind"] == "run" and n.get("parent_id") == cell["id"]]
        complete = [r for r in runs if r.get("status") == "completed"]
        cell_config = cell.get("attrs", {}).get("config", {})
        invalid_cell_config = not isinstance(cell_config, dict)
        if invalid_cell_config:
            cell_config = {}
        invalid_run_config = any(not isinstance(r.get("attrs", {}).get("config", {}), dict) for r in complete)
        cell_config_conflict = any(
            any(key not in r.get("attrs", {}).get("config", {}) or
                canonical(r["attrs"]["config"][key]) != canonical(value)
                for key, value in cell_config.items())
            for r in complete if isinstance(r.get("attrs", {}).get("config", {}), dict)
        )
        seed_counts = Counter(canonical(r["attrs"].get("seed")) for r in complete if r["attrs"].get("seed") is not None)
        duplicated = [s for s, count in seed_counts.items() if count > 1]
        protocol_set = {canonical(r["attrs"].get("eval_protocol")) for r in complete}
        has_unknown_protocol = "null" in protocol_set
        eligible = [r for r in complete if r["attrs"].get("seed") is not None
                    and seed_counts[canonical(r["attrs"]["seed"])] == 1 and r["id"] not in dirty_runs]
        local_warnings = []
        if any(r["id"] in dirty_runs for r in complete):
            local_warnings.append("Evidence source changed or missing; affected runs excluded from the current aggregate. Historical snapshots remain available.")
        recorded_conditions = {canonical({k: v for k, v in r["attrs"].get("config", {}).items() if k not in {"seed", "training.seed", "run_id"}})
                               for r in complete if isinstance(r["attrs"].get("config", {}), dict)}
        code_versions = {canonical(r["attrs"].get("code_revision")) for r in complete if r["attrs"].get("code_revision")}
        if invalid_cell_config or invalid_run_config:
            local_warnings.append("Cell or run configuration is not an object; no pooled aggregate.")
            eligible = []
        if cell_config_conflict:
            local_warnings.append("A run conflicts with the cell's recorded configuration; no pooled aggregate.")
            eligible = []
        if len(recorded_conditions) > 1 or len(code_versions) > 1:
            local_warnings.append("Recorded conditions or code versions differ within this cell; no pooled aggregate.")
            eligible = []
        if duplicated:
            local_warnings.append("Duplicate seed entries excluded until retry/replicate identity is resolved: " + ", ".join(duplicated))
        if len(protocol_set) > 1 or has_unknown_protocol:
            local_warnings.append("Evaluation protocols differ or are unknown; no pooled aggregate.")
            eligible = []
        if any(r["attrs"].get("seed") is None for r in complete):
            local_warnings.append("Runs with unknown training seed excluded from seed-level aggregation.")
        if any(not r["attrs"].get("code_revision") for r in complete):
            local_warnings.append("Historical code revision missing for some runs; summary is descriptive, not proof of a controlled comparison.")
        if len(complete) != len(runs):
            local_warnings.append("Unverified/incomplete runs excluded from aggregation.")
        values, used = [], []
        for r in eligible:
            value = r["attrs"].get("metrics", {}).get(metric)
            if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
                values.append(value)
                used.append(r["id"])
        rows.append({"id": cell["id"], "label": cell["label"], "config": cell_config,
                     "run_count": len(runs), "n": len(values), "mean": statistics.mean(values) if values else None,
                     "sd": statistics.stdev(values) if len(values) > 1 else None, "run_ids": used,
                     "protocols": sorted(protocol_set), "warnings": local_warnings})
    configs = [r["config"] for r in rows]
    keys = sorted(set().union(*(set(c) for c in configs))) if configs else []
    differing = [k for k in keys if len({canonical(c[k]) if k in c else "<MISSING>" for c in configs}) > 1]
    for required in ("dataset_version", "eval_protocol", "train_steps"):
        values = [c.get(required) for c in configs]
        if any(v is None for v in values) or len({canonical(v) for v in values}) > 1:
            warnings.append(f"Comparable {required} not established for all selected cells.")
    training_run_cells = {}
    for row in rows:
        for node_id in row["run_ids"]:
            training_id = state["nodes"][node_id].get("attrs", {}).get("run_id")
            if training_id is not None:
                training_run_cells.setdefault(str(training_id), set()).add(row["id"])
    shared = sorted(run_id for run_id, cell_set in training_run_cells.items() if len(cell_set) > 1)
    if shared:
        warnings.append(f"{len(shared)} recorded run_id values recur across selected cells. These may be checkpoint views or identity collisions; do not add per-cell seed counts as independent replicates until reconciled.")
    return {"metric": metric, "rows": rows, "config_keys": keys, "differing_keys": differing,
            "warnings": warnings, "aggregation": "Arithmetic mean and sample SD across unambiguous, completed training seeds; not across episodes. No automatic winner or causal claim."}


def assess(state: dict, proposal: dict) -> dict:
    """Match a proposed recorded configuration against explicitly scoped decisions.

This never schedules experiments. A positive coverage result is only as valid as
its confirmed scope. Unknown and changed factors require review rather than a
blanket hardware-ablation recommendation.
"""
    config = proposal.get("config", {})
    question_id = proposal.get("question_id")
    result = {"coverage": [], "review": [], "repeat_candidates": [], "replication": [],
              "outcome": "information_needed", "automatic_execution": False}
    if not isinstance(config, dict) or not config:
        result["review"].append({"reason": "A flat, effective configuration is required; do not infer it from the experiment name."})
        return result
    dirty_nodes = {x["node_id"] for x in drift(state)}
    for dec in state["nodes"].values():
        attrs = dec.get("attrs", {})
        if dec["kind"] != "decision" or attrs.get("action") != "reuse":
            continue
        if attrs.get("question_id") != question_id:
            continue
        if dec.get("status") != "accepted" or not dec.get("protected") or not dec.get("confirmation"):
            result["review"].append({"decision_id": dec["id"], "reason": "Candidate decision is not explicitly human-confirmed."})
            continue
        scope = attrs.get("scope", {})
        required = scope.get("required_context", {})
        covered = scope.get("covered_values", {})
        exempt = set(scope.get("replication_keys", ["seed"]))
        mismatches = []
        for k, v in required.items():
            if k not in config or canonical(config[k]) != canonical(v):
                mismatches.append(k)
        for k, allowed in covered.items():
            if not isinstance(allowed, list) or k not in config or not any(canonical(config[k]) == canonical(v) for v in allowed):
                mismatches.append(k)
        extra = set(config) - set(required) - set(covered) - exempt
        if extra:
            mismatches.extend(sorted(extra))
        dependencies, todo = set(), [dec["id"]]
        while todo:
            nid = todo.pop()
            if nid in dependencies:
                continue
            dependencies.add(nid)
            todo.extend(state["nodes"].get(nid, {}).get("evidence_ids", []))
        if dirty_nodes & dependencies:
            mismatches.append("referenced_source_changed_or_missing")
        if mismatches:
            result["review"].append({"decision_id": dec["id"], "reason": "Outside recorded coverage or missing conditions.", "fields": sorted(set(mismatches))})
        else:
            result["coverage"].append({"decision_id": dec["id"], "label": dec["label"],
                                       "basis": dec["confirmation"]["note"], "evidence_ids": dec.get("evidence_ids", []),
                                       "note": "Reuse this bounded judgment. New seeds remain replication, not a reason to repeat hardware ablation."})
    # Exact-condition match is only a review candidate, never an automatic merge.
    for run in state["nodes"].values():
        if run["kind"] != "run":
            continue
        attrs = run.get("attrs", {})
        old = attrs.get("config", {})
        old_base = {k: v for k, v in old.items() if k not in {"seed", "training.seed", "run_id"}}
        new_base = {k: v for k, v in config.items() if k not in {"seed", "training.seed", "run_id"}}
        if canonical(old_base) != canonical(new_base):
            continue
        old_seed = attrs.get("seed")
        new_seed = config.get("seed", config.get("training.seed"))
        if new_seed is not None and old_seed is not None and canonical(new_seed) != canonical(old_seed):
            result["replication"].append(run["id"])
        elif new_seed is not None and old_seed is not None:
            result["repeat_candidates"].append({"run_id": run["id"], "verified_duplicate": False,
                "reason": "Recorded condition and seed match. Confirm code, data, evaluation, retry identity and intent before reuse/merge."})
    if result["coverage"] and not result["review"]:
        result["outcome"] = "covered_by_confirmed_scope"
    elif result["review"]:
        result["outcome"] = "needs_review_not_automatic_new_experiment"
    elif result["repeat_candidates"]:
        result["outcome"] = "possible_reuse_check_provenance"
    elif result["replication"]:
        result["outcome"] = "new_seed_is_replication"
    result["note"] = "This is a bounded record check. The host agent must connect it to the scientific question; no evidence found does not mean an experiment never happened."
    return result
