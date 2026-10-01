"""Instant, portable replay of the saved synthetic research-tree example."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

from .scan import node
from .server import export_html
from .store import Store, HarnessError, atomic_write, canonical

FIXTURE = Path(__file__).parent / "fixtures" / "research_tree.json"
MARKER = "builtin-research-tree-demo"


def create_research_tree_demo(root: str | Path) -> dict:
    root = Path(root).expanduser().resolve()
    store = Store(root)
    raw = FIXTURE.read_bytes()
    fixture_sha = hashlib.sha256(raw).hexdigest()
    fixture = json.loads(raw)
    existing = store.exists()
    if existing:
        state = store.load()
        marker = state["nodes"].get(MARKER, {})
        if (not state["project"].get("synthetic") or
                marker.get("attrs", {}).get("fixture_sha256") != fixture_sha):
            raise HarnessError("Use a new/empty directory for this research-tree example; existing research or a different demo is preserved")
    else:
        if root.exists() and any(root.iterdir()):
            raise HarnessError("Demo needs a new/empty directory; existing files are never overwritten")
        if fixture.get("schema_version") != 1 or fixture.get("fixture_id") != "research-tree-v1":
            raise HarnessError("Unsupported built-in research-tree fixture")
        # Check every bundled snapshot before creating a workspace or writing records.
        for sha, text in fixture["blobs"].items():
            if hashlib.sha256(text.encode("utf-8")).hexdigest() != sha:
                raise HarnessError("Built-in demonstration evidence hash mismatch")
        state = store.init("研究树示例 · 已保存结果回放", synthetic=True)
        for text in fixture["blobs"].values():
            store.blob(text.encode("utf-8"))
        nodes = copy.deepcopy(fixture["nodes"])
        for item in nodes:
            if item["parent_id"] == "$project":
                item["parent_id"] = state["project"]["id"]
            if item["id"] == "study-forest":
                item["description"] = "已保存评测的回放；本次生成未执行实验或调用模型。 " + item["description"]
                item["attrs"]["scope"]["preview_mode"] = "saved_result_replay"
                for lang, summary in item["attrs"].get("study_summary", {}).items():
                    summary["intro"] = ("已保存结果回放；本次未运行评测。 " if lang == "zh" else "Saved result replay; no new evaluation. ") + summary["intro"]
        provenance = {"fixture_id": fixture["fixture_id"], "fixture_sha256": fixture_sha,
                      "source_date": fixture["source_date"], "source_event_hash": fixture["source_event_hash"],
                      "proposal_source": "preset", "evaluation_origin": "saved actual CPU evaluation",
                      "new_cpu_evaluations": 0, "new_model_calls": 0, "shinka_invoked": False,
                      "local_commands_removed": True, **fixture["counts"]}
        blob = (canonical(provenance) + "\n").encode()
        sha = store.blob(blob)
        file = {"id": "builtin-demo-provenance", "source": "builtin-demo", "path": "replay-provenance.json",
                "sha256": sha, "size": len(blob), "snapshot": "text_snapshot", "missing": False}
        nodes.append(node(MARKER, "artifact", "内置研究树示例来源", "study-forest", attrs=provenance,
                          evidence=[{"file_id": file["id"], "sha256": sha, "locator": "Saved result replay provenance"}]))
        store.commit({"base_revision": state["revision"], "reason": "Replay bundled synthetic CPU results; no experiments or model calls executed",
                      "nodes": nodes, "edges": fixture["edges"], "files": [*fixture["files"], file]},
                     actor="builtin-demo:replay", scanner=True)
        atomic_write(root / "README.md", "# Research-tree preview / 研究树预览\n\n"
                     "This workspace replays bundled, saved CPU measurements of preset candidates. "
                     "Generating or reopening it does not run experiments, Shinka or model calls.\n\n"
                     "本空间回放预设候选的已保存CPU评测；本次生成不执行评测、不调用Shinka或模型。\n"
                     "37 candidates, 6 subtrees, 49 saved evaluations, 4 invalid candidates retained.\n\n"
                     "Open `.research/map.html`, or run `labweft serve WORKSPACE --port 0 --open`.\n")
    output = export_html(store, store.root / "map.html", include_evidence=True)
    return {"workspace": str(root), "output": str(output), "existing": existing, "synthetic": True,
            "mode": "saved_result_replay", **fixture["counts"], "new_cpu_evaluations": 0,
            "new_model_calls": 0, "shinka_invoked": False}
