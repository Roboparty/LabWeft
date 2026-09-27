"""Synthetic fixture for interface and regression tests; NOT research evidence."""
from __future__ import annotations
import copy
from pathlib import Path
from .store import Store, HarnessError, json_write, atomic_write
from .scan import sync, node, evidence_ref
from .server import export_html


def create_demo(root: Path) -> dict:
    root = Path(root).expanduser().resolve()
    store = Store(root)
    if store.exists():
        if not store.load()["project"].get("synthetic"):
            raise HarnessError("Refusing to replace a real workspace with a demo")
        return {"workspace": str(root), "existing": True, "synthetic": True}
    if root.exists() and any(root.iterdir()):
        raise HarnessError("Demo needs a new/empty directory; existing files are never overwritten")
    root.mkdir(parents=True, exist_ok=True)
    (root / "code").mkdir()
    atomic_write(root / "code" / "policy.py", '''"""Synthetic, illustrative model interface; no real training is performed."""\n\nclass HistoryEncoder:\n    def __init__(self, history_length=3):\n        self.history_length = history_length\n\n    def encode(self, observations):\n        return observations[-self.history_length:] if self.history_length else observations[-1:]\n\n\ndef auxiliary_objective(prediction, target, weight):\n    # Purely illustrative. Do not interpret demo numbers as outputs of this function.\n    return weight * sum((p - t) ** 2 for p, t in zip(prediction, target))\n''')
    atomic_write(root / "README.md", "# Synthetic policy study / 合成演示\n\nAll metrics are hand-authored fixtures. No training was executed.\n所有数值、代码版本标识、确认记录都是演示数据，不来自任何真实科研项目。\n")
    atomic_write(root / "research-notes.md", """# Synthetic research notes

This is a UI and state-management fixture, not scientific evidence.

## Questions
Q-history: What changes when history_length moves from 0 to 3?
Q-aux: With history enabled, what is the incremental effect of prediction_weight=0.1?
Q-hardware: Should a new hardware-only ablation be recommended again?

## Demonstration-only researcher decision
The synthetic researcher has already reviewed GPU-A and GPU-B under the same
implementation, dataset, precision, budget and evaluation protocol. For this
fixture only, they accept reuse of the hardware judgment for the explicitly
recorded scope. This note does NOT establish statistical equivalence and does
not apply to real hardware or any real research project.

Reopen if implementation, precision, data, effective budget, or evaluation
protocol changes, or new contradictory evidence appears. A new training seed
is replication, not a reason to repeat the hardware ablation.
""")
    variants = [
        ("C0", 0, 0.0, "GPU-A", [0.63, 0.65, 0.64]),
        ("C1", 3, 0.0, "GPU-A", [0.71, 0.73, 0.72]),
        ("C2", 3, 0.1, "GPU-A", [0.74, 0.76, 0.75]),
        ("C3", 3, 0.1, "GPU-B", [0.73, 0.75, 0.75]),
    ]
    for cname, history, aux, hw, values in variants:
        for seed, result in enumerate(values):
            directory = root / "results" / f"{cname}-seed-{seed}"
            directory.mkdir(parents=True)
            config = {"history_length": history, "prediction_weight": aux, "hardware": hw,
                      "dataset_version": "toy-v1", "eval_protocol": "heldout-v1", "train_steps": 20000,
                      "precision": "fp32", "implementation_id": "synthetic-policy-v1", "seed": seed}
            json_write(directory / "config.json", config)
            json_write(directory / "run.json", {"run_id": f"synthetic-{cname}-{seed}", "seed": seed,
                       "code_revision": "SYNTHETIC-CODE-v1-NOT-A-GIT-COMMIT", "dataset_version": "toy-v1",
                       "eval_protocol": "heldout-v1", "status": "completed"})
            json_write(directory / "metrics.json", {"status": "completed", "metrics": {"success_rate": result},
                       "synthetic": True, "note": "Hand-authored fixture. No training performed."})
    store.init("Policy Study / 科研项目演示", synthetic=True)
    store.set_sources({"project": str(root)})
    sync(store)
    state = store.load()
    pid = state["project"]["id"]
    note_file = next(f for f in state["files"].values() if f["path"] == "research-notes.md")
    note_refs = [evidence_ref(note_file)]
    additions = [
        node("module-representation", "module", "表征与历史输入", pid, attrs={"order": 0}, description="梳理输入信息与策略表征的关系。所有结果均为合成示例。"),
        node("module-objective", "module", "预测目标与训练", pid, attrs={"order": 1}, description="区分目标函数改变、运行事实与可支持的结论。"),
        node("module-runtime", "module", "环境与可复用判断", pid, attrs={"order": 2}, description="环境信息一直保留；被已有证据覆盖的差异，不再无理由重复验证。"),
        node("question-history", "question", "历史输入是否提供增益？", "module-representation", status="provisional",
             description="比较 C0 与 C1，仅研究当前设定下 history_length 的变化。这里的实验数值是演示数据，不构成真实科学结论。", evidence=note_refs),
        node("question-aux", "question", "辅助预测目标是否必要？", "module-objective", status="provisional",
             description="复用 C1 作为基线，与 C2 比较。不能从有历史条件下的结果推广到无历史条件。", evidence=note_refs,
             attrs={"next_action": "先检查要支持的结论。只有要声称不依赖历史输入时，才讨论额外 cell；不自动把矩阵填满。"}),
        node("question-hardware", "question", "不同硬件需要再做消融吗？", "module-runtime", status="accepted",
             description="展示历史判断的复用机制。范围内硬件变化不自动触发新实验；相关实质条件改变时重新检查。", evidence=note_refs),
    ]
    cells = [n for n in state["nodes"].values() if n["kind"] == "cell"]
    mapped = {}
    for c in cells:
        cfg = c["attrs"]["config"]
        name = "C0" if cfg["history_length"] == 0 else "C1" if cfg["prediction_weight"] == 0 else "C2" if cfg["hardware"] == "GPU-A" else "C3"
        mapped[name] = c["id"]
        n = copy.deepcopy(c)
        n.update({"label": {"C0": "C0 · 基础策略", "C1": "C1 · 加入历史", "C2": "C2 · 加入预测目标", "C3": "C3 · 已有硬件对照"}[name],
                  "parent_id": "question-history" if name in {"C0", "C1"} else "question-aux" if name == "C2" else "question-hardware",
                  "status": "completed", "description": "合成数据中的一个明确实验条件。下方三个 run 分别对应三个独立 seed。"})
        additions.append(n)
    staging = copy.deepcopy(state["nodes"]["question-unclassified"])
    staging["status"] = "archived"
    additions.append(staging)
    c2 = next(c for c in cells if c["id"] == mapped["C2"])
    required = {k: v for k, v in c2["attrs"]["config"].items() if k != "hardware"}
    scope = {"required_context": required, "covered_values": {"hardware": ["GPU-A", "GPU-B"]}, "replication_keys": ["seed"]}
    hardware_refs = list(note_refs)
    for run in state["nodes"].values():
        if run["kind"] == "run" and run["parent_id"] in {mapped["C2"], mapped["C3"]}:
            hardware_refs.extend(run.get("evidence", []))
    hardware_refs = list({(r["file_id"], r["sha256"]): r for r in hardware_refs}.values())
    additions += [
        node("claim-aux", "claim", "当前有历史设定下的增量作用", "question-aux", status="provisional", evidence=note_refs,
             evidence_ids=[mapped["C1"], mapped["C2"]],
             description="示例数据中 C2 均值高于 C1。只能描述当前条件，不等于已证明一般必要性；不把演示数字用于任何真实论文。",
             attrs={"scope": {"dataset": "toy-v1", "history_length": 3, "metric": "success_rate"}}),
        node("decision-hardware", "decision", "硬件差异：范围内复用已有判断", "question-hardware", status="accepted", evidence=hardware_refs,
             evidence_ids=[mapped["C2"], mapped["C3"]],
             description="演示用人工决策：同一实现、精度、数据、预算与评估协议下，GPU-A / GPU-B 已检查。后续不因为只换了这两个硬件就再次提出消融。",
             attrs={"action": "reuse", "question_id": "question-hardware", "scope": scope,
                    "reopen_if": "实现、精度、数据、训练预算或评估协议改变；出现新冲突证据。新 seed 只属于重复验证，不自动触发硬件消融。"}),
    ]
    edges = [
        {"id": "edge-history", "source": mapped["C1"], "target": mapped["C0"], "relation": "compares"},
        {"id": "edge-aux", "source": mapped["C2"], "target": mapped["C1"], "relation": "compares"},
        {"id": "edge-hardware", "source": mapped["C3"], "target": mapped["C2"], "relation": "compares"},
    ]
    store.commit({"base_revision": state["revision"], "reason": "Synthetic semantic mapping: research questions, cells, evidence and bounded decisions",
                  "nodes": additions, "edges": edges}, actor="demo-fixture")
    store.confirm("decision-hardware", "合成示例中的人工确认；仅用于测试有范围的历史复用，不是实际硬件结论。", "synthetic-reviewer")
    proposal = {"question_id": "question-hardware", "config": {**required, "hardware": "GPU-B", "seed": 7}}
    json_write(root / ".research" / "proposal-covered.json", proposal)
    changed = copy.deepcopy(proposal)
    changed["config"]["eval_protocol"] = "heldout-v2"
    json_write(root / ".research" / "proposal-changed-protocol.json", changed)
    export_html(store, root / ".research" / "map.html", include_evidence=True)
    return {"workspace": str(root), "synthetic": True, "runs": 12, "cells": 4,
            "map": str(root / ".research" / "map.html"), "next": "labweft serve " + str(root) + " --open"}
