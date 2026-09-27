"""Conservative filesystem ingestion. Never imports or executes research code.

Recognizes JSON/TOML configuration and metrics.json/results.json/metrics.csv.
Everything else is inventoried as evidence, not silently interpreted as a run.
A scan records the current filesystem, NOT a past training-time code snapshot.
"""
from __future__ import annotations
import ast
import copy
import csv
import io
import json
import math
import os
from pathlib import Path
import tomllib
from typing import Any

from .store import HarnessError, Store, canonical, stable_id

TEXT_EXT = {".py", ".md", ".json", ".jsonl", ".yaml", ".yml", ".toml", ".csv", ".txt", ".log", ".sh", ".ini", ".cfg"}
ASSET_EXT = {".pt", ".pth", ".ckpt", ".safetensors", ".npz", ".npy", ".mp4", ".png", ".jpg", ".jpeg", ".pdf"}
SKIP_DIRS = {".git", ".research", ".venv", "venv", "node_modules", "__pycache__", ".mypy_cache", ".pytest_cache", ".cache", ".ssh", ".aws", ".azure", ".config"}
MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_TOTAL_BYTES = 32 * 1024 * 1024
MAX_FILES = 10000


def sensitive_name(name: str) -> bool:
    n = name.lower()
    return (n.startswith(".env") or n in {"id_rsa", "id_ed25519", "credentials", "credentials.json", "secrets.json", "secrets.yaml", "secrets.yml"}
            or n.endswith((".pem", ".key", ".p12", ".pfx")))


def finite_json(raw: str) -> Any:
    return json.loads(raw, parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))


def flatten(value: dict, prefix: str = "") -> dict:
    result = {}
    for key, item in value.items():
        full = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(item, dict):
            result.update(flatten(item, full))
        else:
            result[full] = item
    return result


def numeric_metrics(value: dict) -> dict[str, float]:
    return {key: float(val) for key, val in flatten(value).items()
            if isinstance(val, (int, float)) and not isinstance(val, bool) and math.isfinite(val)
            and key not in {"seed", "step", "epoch", "run_id"}}


def evidence_ref(item: dict, locator: str = "full file") -> dict:
    return {"file_id": item["id"], "sha256": item["sha256"], "locator": locator}


def node(nid: str, kind: str, label: str, parent: str, **kwargs: Any) -> dict:
    return {"id": nid, "kind": kind, "label": label, "parent_id": parent,
            "status": "recorded", "description": "", "attrs": {}, "evidence": [], **kwargs}


def collect(store: Store, *, max_files: int = MAX_FILES, max_bytes: int = MAX_TOTAL_BYTES) -> tuple[list[dict], dict, dict]:
    state = store.load()
    sources = store.sources()
    if not sources:
        raise HarnessError("No source directories configured. Use labweft sync --source code=/path/to/code")
    files, texts, warnings, roots = [], {}, [], []
    total_bytes, complete = 0, True
    visited_paths: set[str] = set()
    for alias, source in sorted(sources.items()):
        root = Path(source).expanduser().resolve()
        roots.append(alias)
        if not root.is_dir():
            complete = False
            warnings.append(f"Source unavailable: {alias}. Existing records are preserved.")
            continue
        for directory, dirs, names in os.walk(root, followlinks=False):
            dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not (Path(directory) / d).is_symlink()
                             and (not d.startswith(".") or d == ".hydra"))
            for name in sorted(names):
                path = Path(directory) / name
                if path.is_symlink() or sensitive_name(name):
                    continue
                if name.startswith(".") or path.suffix.lower() not in TEXT_EXT | ASSET_EXT:
                    continue
                absolute = str(path.resolve())
                if absolute in visited_paths:
                    continue
                visited_paths.add(absolute)
                if len(files) >= max_files:
                    complete = False
                    warnings.append(f"File limit reached ({max_files}). Inventory is partial; unseen sources are NOT marked missing.")
                    break
                relative = path.relative_to(root).as_posix()
                fid = stable_id("file", state["project"]["id"], alias, relative)
                try:
                    stat = path.stat()
                    record = {"id": fid, "source": alias, "path": relative, "size": stat.st_size,
                              "sha256": None, "snapshot": "metadata_only", "missing": False}
                    if path.suffix.lower() in TEXT_EXT and stat.st_size <= MAX_FILE_BYTES and total_bytes + stat.st_size <= max_bytes:
                        # Text only. No pickle, torch.load, imports, or commands from source files.
                        raw = path.read_bytes()
                        if len(raw) > MAX_FILE_BYTES:
                            record["snapshot"] = "changed_while_reading"
                        elif b"\x00" not in raw:
                            text = raw.decode("utf-8", errors="strict")
                            record["sha256"] = store.blob(raw)
                            record["snapshot"] = "text_snapshot"
                            total_bytes += len(raw)
                            texts[fid] = text
                            if path.suffix == ".py":
                                try:
                                    tree = ast.parse(text)
                                    record["symbols"] = [{"name": n.name, "line": n.lineno, "kind": type(n).__name__}
                                                         for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))][:200]
                                except SyntaxError:
                                    record["parse_note"] = "Python AST unavailable; raw source still indexed"
                    elif path.suffix.lower() in TEXT_EXT:
                        record["snapshot"] = "text_budget_exceeded"
                        warnings.append(f"Text not copied due to size/budget: {alias}/{relative}")
                    files.append(record)
                    if len(files) >= max_files:
                        # We stop walking here, so even an exact-boundary scan
                        # cannot prove that no later directory contains files.
                        complete = False
                        warnings.append(f"File limit reached ({max_files}). Inventory is partial; unseen sources are NOT marked missing.")
                        break
                except (OSError, UnicodeError) as exc:
                    complete = False
                    warnings.append(f"Unreadable file {alias}/{relative}: {type(exc).__name__}")
            if len(files) >= max_files:
                break
    by_id = {f["id"]: f for f in files}
    if complete:
        for fid, old in state["files"].items():
            if old["source"] in roots and fid not in by_id:
                files.append({**old, "missing": True})
    report = {"complete": complete, "file_count": sum(not x["missing"] for x in files),
              "warnings": sorted(set(warnings)), "source_aliases": roots,
              "note": "Inventory of configured source directories only, not a complete project audit or proof of historical training inputs. Known secret filenames skipped; this is not a comprehensive secret scanner."}
    return files, texts, report


def parse_runs(state: dict, files: list[dict], texts: dict) -> tuple[list[dict], list[str]]:
    project_id = state["project"]["id"]
    output: dict[str, dict] = {}
    warnings = []
    by_path = {(f["source"], f["path"]): f for f in files if not f.get("missing")}
    unclassified = "question-unclassified"
    output[unclassified] = node(unclassified, "question", "待归类的实验 / Needs mapping", project_id,
                               status="needs_review", description="仅从文件识别的运行。研究动机和 cell 关系需要 agent 核对，不从目录名猜测。")
    for item in files:
        if item.get("missing") or item["id"] not in texts:
            continue
        path = Path(item["path"])
        if path.name not in {"metrics.json", "results.json", "metrics.csv"}:
            continue
        # Avoid silently taking a different metric file as a second/current run.
        # Prefer metrics.json, then results.json, then metrics.csv in each directory.
        priority = ["metrics.json", "results.json", "metrics.csv"]
        available = [name for name in priority if (item["source"], (path.parent / name).as_posix()) in by_path]
        if available and path.name != available[0]:
            warnings.append(f"Additional metric source indexed but not pooled: {item['source']}/{item['path']}; primary is {available[0]}")
            continue
        try:
            if path.suffix == ".csv":
                rows = list(csv.DictReader(io.StringIO(texts[item["id"]])))
                if not rows:
                    continue
                last = {}
                for key, value in rows[-1].items():
                    try:
                        number = float(value)
                        if math.isfinite(number):
                            last[key] = number
                    except (ValueError, TypeError):
                        continue
                payload = {"metrics": last}
                selection = "last CSV row; completion not verified"
            else:
                payload = finite_json(texts[item["id"]])
                selection = "reported JSON metrics"
            if not isinstance(payload, dict):
                raise ValueError("metric root is not an object")
            metrics = numeric_metrics(payload.get("metrics", payload))
            if not metrics:
                continue
            config: dict = {}
            meta: dict = {}
            refs = [evidence_ref(item, selection)]
            for filename in ("run.json", "config.json", "config.toml"):
                relative = (path.parent / filename).as_posix()
                other = by_path.get((item["source"], relative))
                if other and other["id"] in texts:
                    try:
                        parsed = tomllib.loads(texts[other["id"]]) if filename.endswith("toml") else finite_json(texts[other["id"]])
                        if isinstance(parsed, dict):
                            if filename == "run.json":
                                meta.update(parsed)
                                if isinstance(parsed.get("config"), dict):
                                    config.update(parsed["config"])
                            else:
                                config.update(parsed)
                            refs.append(evidence_ref(other))
                    except (ValueError, TypeError) as exc:
                        warnings.append(f"Config parse failed: {item['source']}/{relative}: {exc}")
            flat = flatten(config)
            protocol_sources = [p for p in (meta.get("eval_protocol"), flat.get("eval_protocol"),
                                           payload.get("eval_protocol"), payload.get("protocol")) if p is not None]
            protocol_conflict = len({canonical(p) for p in protocol_sources}) > 1
            eval_protocol = protocol_sources[0] if protocol_sources else None
            seed = meta.get("seed", flat.get("seed", flat.get("training.seed")))
            explicit = meta.get("run_id", payload.get("run_id"))
            logical_key = str(explicit) if explicit is not None else f"{item['source']}:{path.parent.as_posix()}"
            rid = stable_id("run", project_id, logical_key)
            # Seed is replication, not a cell factor. Other unknown fields are retained.
            cell_config = {k: v for k, v in flat.items() if k not in {"seed", "training.seed", "run_id"}}
            cid = stable_id("cell", project_id, canonical(cell_config) if cell_config else "unresolved:" + logical_key)
            previous = state["nodes"].get(rid)
            old_metric_file_id = None
            if previous:
                cid = previous.get("parent_id", cid)
                old_metric_file_id = previous.get("attrs", {}).get("metric_source_file_id")
                if old_metric_file_id is None and previous.get("attrs", {}).get("input_provenance") and previous.get("evidence"):
                    old_metric_file_id = previous["evidence"][0]["file_id"]
            old_cell = state["nodes"].get(cid)
            if cid not in output and not old_cell:
                output[cid] = node(cid, "cell", f"候选条件 {cid[-6:]}", unclassified,
                                   status="needs_review", attrs={"config": cell_config, "assignment": "provisional exact config match; not scientific equivalence"},
                                   description="排除 seed 后配置相同的候选组；不同硬件不会自动合并。", evidence=refs[1:])
            if previous and previous.get("protected"):
                # A scan cannot overwrite human-confirmed corrections.
                output[rid] = previous
            else:
                run_node = copy.deepcopy(previous) if previous else node(rid, "run", str(explicit or path.parent.name or rid), cid)
                run_node.update({"evidence": refs, "status": "completed" if payload.get("status", meta.get("status")) == "completed" else "recorded"})
                run_node.setdefault("attrs", {}).update({"config": flat, "seed": seed, "run_id": explicit,
                    "identity_basis": "recorded run_id" if explicit is not None else "source alias + relative run directory; rename needs reconciliation",
                    "code_revision": meta.get("code_revision"), "dataset_version": meta.get("dataset_version", flat.get("dataset_version")),
                    "metrics": metrics, "metric_selection": selection, "metric_source_file_id": item["id"],
                    "eval_protocol": eval_protocol,
                    "input_provenance": "recorded fields only; current code is NOT assigned as historical training code"})
                if old_metric_file_id and old_metric_file_id != item["id"]:
                    run_node["attrs"]["metric_source_transition"] = {"from": old_metric_file_id, "to": item["id"]}
                    old_refs = [r for r in previous.get("evidence", []) if r["file_id"] == old_metric_file_id]
                    run_node["evidence"] = old_refs + refs
                    old_eid = stable_id("evaluation", rid, old_metric_file_id)
                    old_eval = state["nodes"].get(old_eid)
                    if old_eval and not old_eval.get("protected"):
                        archived = copy.deepcopy(old_eval)
                        archived["status"] = "archived"
                        output[old_eid] = archived
                if run_node["attrs"].get("metric_source_transition"):
                    warnings.append(f"Primary metric source changed: {rid}; run excluded until reviewed")
                    prior_id = run_node["attrs"]["metric_source_transition"]["from"]
                    prior_refs = [r for r in previous.get("evidence", []) if r["file_id"] == prior_id] if previous else []
                    run_node["evidence"] = list({(r["file_id"], r["sha256"]): r
                                                 for r in prior_refs + refs}.values())
                    run_node["status"] = "needs_review"
                    run_node["attrs"]["ingestion_warning"] = "Primary metric source changed; inspect old and new evidence before pooling."
                if protocol_conflict:
                    run_node["status"] = "needs_review"
                    run_node["attrs"]["ingestion_warning"] = "Evaluation protocol fields disagree across metric, run, or config sources."
                    warnings.append(f"Evaluation protocol conflict: {rid}; run excluded until reviewed")
                if old_cell and canonical(old_cell.get("attrs", {}).get("config", {})) != canonical(cell_config):
                    run_node["status"] = "needs_review"
                    run_node["attrs"]["ingestion_warning"] = "Recorded config differs from its existing cell. Preserve identity; reconcile before pooling."
                    warnings.append(f"Config/cell mismatch: {rid}; run excluded until reviewed")
                if rid in output and output[rid] != run_node:
                    run_node["status"] = "needs_review"
                    run_node["attrs"]["ingestion_warning"] = "Multiple source directories claim the same run_id. Identity conflict needs reconciliation."
                    run_node["evidence"] = list({(r["file_id"], r["sha256"]): r for r in output[rid].get("evidence", []) + refs}.values())
                    warnings.append(f"Conflicting recorded run identity: {rid}; run excluded until reviewed")
                output[rid] = run_node
            eid = stable_id("evaluation", rid, item["id"])
            old_eval = state["nodes"].get(eid)
            ev = copy.deepcopy(old_eval) if old_eval else node(eid, "evaluation", "评估 / " + path.name, rid)
            if not ev.get("protected"):
                ev.update({"evidence": [refs[0]], "status": output[rid]["status"],
                           "attrs": {"metrics": metrics, "protocol": eval_protocol,
                                     "selection": selection}})
            output[eid] = ev
        except (ValueError, TypeError, AttributeError) as exc:
            warnings.append(f"Metrics parse failed: {item['source']}/{item['path']}: {exc}")
    # Never overwrite agent-authored semantics of the staging question.
    if unclassified in state["nodes"]:
        output.pop(unclassified, None)
    if len(output) == 1 and unclassified in output:
        output.clear()
    return list(output.values()), warnings


def sync(store: Store, *, max_files: int = MAX_FILES, max_bytes: int = MAX_TOTAL_BYTES) -> dict:
    state = store.load()
    files, texts, report = collect(store, max_files=max_files, max_bytes=max_bytes)
    nodes, parse_warnings = parse_runs(state, files, texts)
    if not report["complete"]:
        nodes = [n for n in nodes if n["id"] not in state["nodes"]]
        report["warnings"].append("Partial scan: existing semantic/run records were not overwritten.")
    report["warnings"] = sorted(set(report["warnings"] + parse_warnings))
    changed = [f["id"] for f in files if f["id"] in state["files"] and state["files"][f["id"]] != f]
    new = [f["id"] for f in files if f["id"] not in state["files"]]
    result = store.commit({"base_revision": state["revision"], "reason": "Read-only source scan and conservative run ingestion",
                           "files": files, "nodes": nodes, "scan": report}, actor="scanner", scanner=True)
    result.update({"new_files": len(new), "changed_files": len(changed), "scan": report,
                   "next": "Read labweft context, inspect evidence, submit a semantic patch. Scanning alone does not establish research intent."})
    return result
