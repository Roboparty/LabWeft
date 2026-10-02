from __future__ import annotations
import copy
import hashlib
import http.client
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest

from research_harness.store import Store, HarnessError, Conflict, json_write, read_json
from research_harness.scan import sync, node, evidence_ref
from research_harness.reasoning import compare, assess, drift
from research_harness.server import make_server, export_html, export_site
from research_harness.cli import install_skill
from research_harness.demo import create_demo

class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "project"
        self.root.mkdir()
        self.store = Store(self.root)
        self.store.init("Test")

    def tearDown(self):
        self.temp.cleanup()

    def run_file(self, folder="run0", seed=0, success=.5, **updates):
        path = self.root / "results" / folder
        path.mkdir(parents=True, exist_ok=True)
        cfg = {"seed": seed, "history_length": 3, "hardware": "A", "eval_protocol": "v1", "dataset_version": "d1", "train_steps": 100}
        cfg.update(updates)
        json_write(path / "config.json", cfg)
        json_write(path / "metrics.json", {"status": "completed", "metrics": {"success_rate": success}})
        return path

    def test_initialize_is_idempotent(self):
        identity = self.store.load()["project"]["id"]
        self.store.init("Different display label")
        self.assertEqual(identity, self.store.load()["project"]["id"])

    def test_cli_json_is_utf8_when_redirected(self):
        state = self.store.load()
        n = node("question-unicode", "question", "中文问题", state["project"]["id"])
        self.store.commit({"base_revision": state["revision"], "reason": "Unicode output", "nodes": [n]})
        cli = Path(__file__).resolve().parents[1] / "labweft.py"
        result = subprocess.run([sys.executable, str(cli), "context", str(self.root), "--full"],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        payload = json.loads(result.stdout.decode("utf-8"))
        self.assertEqual("中文问题", payload["nodes"]["question-unicode"]["label"])

    def test_bootstrap_can_keep_state_outside_source(self):
        source = Path(self.temp.name) / "readonly-source"
        source.mkdir()
        (source / "README.md").write_text("Synthetic research note", encoding="utf-8")
        workspace = Path(self.temp.name) / "separate-workspace"
        bootstrap = Path(__file__).resolve().parents[1] / "bootstrap.py"
        result = subprocess.run([sys.executable, str(bootstrap), "--project", str(source),
                                 "--workspace", str(workspace), "--agent", "codex"],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        payload = json.loads(result.stdout.decode("utf-8"))
        self.assertEqual(str(workspace.resolve()), payload["workspace"])
        self.assertFalse((source / ".research").exists())
        self.assertFalse((source / ".agents").exists())
        self.assertTrue((workspace / ".agents" / "skills" / "research-harness" / "SKILL.md").is_file())
        state = Store(workspace).load()
        self.assertEqual(["README.md"], [f["path"] for f in state["files"].values()])

    def test_id_survives_workspace_copy(self):
        copy_path = Path(self.temp.name) / "copy"
        shutil.copytree(self.root, copy_path)
        self.assertEqual(Store(copy_path).load()["project"]["id"], self.store.load()["project"]["id"])

    def test_second_scan_is_noop(self):
        self.run_file()
        first = sync(self.store)
        second = sync(self.store)
        self.assertTrue(first["changed"])
        self.assertFalse(second["changed"])
        self.assertEqual(first["revision"], second["revision"])

    def test_scan_note_wording_does_not_create_scientific_revision(self):
        self.run_file()
        sync(self.store)
        state = self.store.load()
        report = copy.deepcopy(state["scan"])
        report["note"] = "Updated explanatory wording only"
        result = self.store.commit({"base_revision": state["revision"], "reason": "Scanner text update",
                                    "scan": report}, actor="scanner", scanner=True)
        self.assertFalse(result["changed"])
        self.assertEqual(state["revision"], self.store.load()["revision"])

    def test_no_invented_historical_commit(self):
        self.run_file()
        sync(self.store)
        runs = [n for n in self.store.load()["nodes"].values() if n["kind"] == "run"]
        self.assertIsNone(runs[0]["attrs"]["code_revision"])
        self.assertEqual("needs_review", next(n for n in self.store.load()["nodes"].values() if n["kind"] == "cell")["status"])

    def test_seed_not_new_cell_hardware_is(self):
        self.run_file("s0", 0)
        self.run_file("s1", 1)
        self.run_file("hardware", 0, hardware="B")
        sync(self.store)
        kinds = list(self.store.load()["nodes"].values())
        self.assertEqual(2, sum(n["kind"] == "cell" for n in kinds))
        self.assertEqual(3, sum(n["kind"] == "run" for n in kinds))

    def test_incremental_folder_addition_keeps_existing_question_and_separates_cells(self):
        self.run_file("baseline-s0", 0)
        sync(self.store)
        state = self.store.load()
        cell = next(n for n in state["nodes"].values() if n["kind"] == "cell")
        question = node("question-incremental", "question", "Synthetic ablation question", state["project"]["id"])
        revised_cell = copy.deepcopy(cell)
        revised_cell["parent_id"] = question["id"]
        self.store.commit({"base_revision": state["revision"], "reason": "Agent maps the initial condition",
                           "nodes": [question, revised_cell]})
        new_folder = self.root / "results" / "new-ablation"
        new_folder.mkdir()
        (new_folder / "PROTOCOL.md").write_text("Synthetic new condition; no result yet", encoding="utf-8")
        sync(self.store)
        self.assertEqual(1, len([n for n in self.store.load()["nodes"].values() if n["kind"] == "run"]))
        self.run_file("baseline-s42", 42, .7)
        self.run_file("new-ablation", 0, .8, hardware="B")
        sync(self.store)
        current = self.store.load()
        self.assertEqual("Synthetic ablation question", current["nodes"][question["id"]]["label"])
        self.assertEqual(question["id"], current["nodes"][cell["id"]]["parent_id"])
        rows = {row["id"]: row for row in compare(current)["rows"]}
        self.assertEqual(2, len(rows))
        self.assertEqual(2, rows[cell["id"]]["n"])
        self.assertAlmostEqual(.6, rows[cell["id"]]["mean"])
        self.assertEqual(1, next(row["n"] for row in rows.values() if row["id"] != cell["id"]))
        self.assertFalse(sync(self.store)["changed"])

    def test_secret_names_not_copied(self):
        (self.root / ".env").write_text("API_KEY=dummy-secret")
        (self.root / "credentials.json").write_text('{"password":"dummy-secret"}')
        (self.root / "safe.md").write_text("research")
        sync(self.store)
        paths = [f["path"] for f in self.store.load()["files"].values()]
        self.assertEqual(["safe.md"], paths)

    def test_symlink_escape_skipped(self):
        outside = Path(self.temp.name) / "outside.txt"
        outside.write_text("do not index")
        try:
            (self.root / "outside.txt").symlink_to(outside)
        except OSError:
            self.skipTest("symlink unsupported")
        sync(self.store)
        self.assertFalse(self.store.load()["files"])

    def test_weights_metadata_only(self):
        (self.root / "not-a-real-checkpoint.pth").write_bytes(b"NEVER DESERIALIZE")
        sync(self.store)
        file = next(iter(self.store.load()["files"].values()))
        self.assertIsNone(file["sha256"])
        self.assertEqual("metadata_only", file["snapshot"])

    def test_invalid_json_warns_without_executing(self):
        d = self.run_file()
        (d / "metrics.json").write_text('{"success_rate":NaN}')
        out = sync(self.store)
        self.assertTrue(any("Metrics parse failed" in w for w in out["scan"]["warnings"]))
        self.assertEqual(0, sum(n["kind"] == "run" for n in self.store.load()["nodes"].values()))

    def test_scan_limit_preserves_unseen_files(self):
        (self.root / "a.md").write_text("a")
        (self.root / "b.md").write_text("b")
        sync(self.store)
        out = sync(self.store, max_files=1)
        self.assertFalse(out["scan"]["complete"])
        self.assertFalse(any(f["missing"] for f in self.store.load()["files"].values()))

    def test_scan_limit_at_directory_boundary_preserves_unseen_files(self):
        (self.root / "a").mkdir()
        (self.root / "b").mkdir()
        (self.root / "a" / "first.md").write_text("first")
        (self.root / "b" / "second.md").write_text("second")
        sync(self.store)
        out = sync(self.store, max_files=1)
        self.assertFalse(out["scan"]["complete"])
        self.assertFalse(any(f["missing"] for f in self.store.load()["files"].values()))

    def test_deleted_file_keeps_original_snapshot(self):
        p = self.root / "notes.md"
        p.write_text("initial evidence")
        sync(self.store)
        file = next(iter(self.store.load()["files"].values()))
        p.unlink()
        sync(self.store)
        self.assertTrue(self.store.load()["files"][file["id"]]["missing"])
        self.assertEqual("initial evidence", self.store.read_blob(file["sha256"]))

    def test_timeline_tracks_source_and_map_changes_without_new_event_format(self):
        source = self.root / "notes.md"
        source.write_text("first", encoding="utf-8")
        sync(self.store)
        state = self.store.load()
        self.assertEqual("added", state["history"][-1]["changes"]["files"][0]["change"])
        module = node("module-timeline", "module", "Initial module", state["project"]["id"])
        self.store.commit({"base_revision": state["revision"], "reason": "Map the module", "nodes": [module]})
        self.assertEqual("added", self.store.load()["history"][-1]["changes"]["nodes"][0]["change"])
        source.write_text("second", encoding="utf-8")
        sync(self.store)
        self.assertEqual("updated", self.store.load()["history"][-1]["changes"]["files"][0]["change"])
        state = self.store.load()
        revised = copy.deepcopy(state["nodes"][module["id"]])
        revised["label"] = "Revised module"
        self.store.commit({"base_revision": state["revision"], "reason": "Rename module", "nodes": [revised]})
        change = self.store.load()["history"][-1]["changes"]["nodes"][0]
        self.assertEqual("updated", change["change"])
        self.assertIn("label", change["fields"])
        state = self.store.load()
        archived = copy.deepcopy(state["nodes"][module["id"]])
        archived["status"] = "archived"
        self.store.commit({"base_revision": state["revision"], "reason": "Retire module", "nodes": [archived]})
        self.assertEqual("archived", self.store.load()["history"][-1]["changes"]["nodes"][0]["change"])
        source.unlink()
        sync(self.store)
        state = self.store.load()
        self.assertEqual("missing", state["history"][-1]["changes"]["files"][0]["change"])
        self.assertEqual(len(state["history"]), state["revision"])
        self.assertFalse(sync(self.store)["changed"])
        self.assertEqual(state["history"], self.store.load()["history"])

    def test_timeline_keeps_module_at_time_of_node_update(self):
        pid = self.store.load()["project"]["id"]
        first = node("module-first", "module", "First", pid)
        second = node("module-second", "module", "Second", pid)
        question = node("question-moving", "question", "Question", first["id"])
        self.store.commit({"base_revision": 0, "reason": "Initial mapping",
                           "nodes": [first, second, question]})
        initial = self.store.load()["history"][-1]["changes"]["nodes"]
        self.assertEqual(first["id"], next(x for x in initial if x["id"] == question["id"])["module_id"])
        moved = copy.deepcopy(question)
        moved["parent_id"] = second["id"]
        self.store.commit({"base_revision": 1, "reason": "Move question", "nodes": [moved]})
        state = self.store.load()
        self.assertEqual(first["id"], next(x for x in state["history"][0]["changes"]["nodes"]
                                                  if x["id"] == question["id"])["module_id"])
        self.assertEqual(second["id"], state["history"][-1]["changes"]["nodes"][0]["module_id"])

    def test_missing_metric_source_excludes_stale_run_from_current_aggregate(self):
        a = self.run_file("a", 0, .4)
        self.run_file("b", 1, .6)
        sync(self.store)
        self.assertEqual(2, compare(self.store.load())["rows"][0]["n"])
        (a / "metrics.json").unlink()
        sync(self.store)
        row = compare(self.store.load())["rows"][0]
        self.assertEqual(1, row["n"])
        self.assertAlmostEqual(.6, row["mean"])
        self.assertTrue(any("Evidence source changed or missing" in w for w in row["warnings"]))

    def test_revision_conflict_no_partial_update(self):
        pid = self.store.load()["project"]["id"]
        patch = {"base_revision": 0, "reason": "first", "nodes": [node("m1", "module", "Module", pid)]}
        self.store.commit(patch)
        with self.assertRaises(Conflict):
            self.store.commit(patch)
        self.assertEqual(1, self.store.load()["revision"])

    def test_invalid_evidence_rejected(self):
        pid = self.store.load()["project"]["id"]
        n = node("q1", "question", "Question", pid, evidence=[{"file_id": "no-file", "sha256": "a" * 64}])
        with self.assertRaises(HarnessError):
            self.store.commit({"base_revision": 0, "reason": "bad ref", "nodes": [n]})
        self.assertEqual(0, self.store.load()["revision"])

    def test_invalid_parent_and_cycle_rejected(self):
        nodes = [node("a", "module", "a", "b"), node("b", "module", "b", "a")]
        with self.assertRaises(HarnessError):
            self.store.commit({"base_revision": 0, "reason": "cycle", "nodes": nodes})

    def test_protected_node_cannot_be_overwritten(self):
        pid = self.store.load()["project"]["id"]
        n = node("m", "module", "User correction", pid)
        self.store.commit({"base_revision": 0, "reason": "initial", "nodes": [n]})
        self.store.confirm("m", "retain this name", "tester")
        state = self.store.load()
        n = copy.deepcopy(state["nodes"]["m"])
        n["label"] = "agent replacement"
        with self.assertRaises(HarnessError):
            self.store.commit({"base_revision": state["revision"], "reason": "replace", "nodes": [n]})
        self.assertEqual("User correction", self.store.load()["nodes"]["m"]["label"])

    def test_agent_cannot_fabricate_confirmation(self):
        pid = self.store.load()["project"]["id"]
        n = node("m", "module", "m", pid, protected=True)
        with self.assertRaises(HarnessError):
            self.store.commit({"base_revision": 0, "reason": "fake human", "nodes": [n]})

    def test_event_corruption_detected(self):
        pid = self.store.load()["project"]["id"]
        self.store.commit({"base_revision": 0, "reason": "initial", "nodes": [node("m", "module", "m", pid)]})
        event_file = self.store.root / "events" / "00000001.json"
        event = read_json(event_file)
        event["reason"] = "changed outside transaction"
        json_write(event_file, event)
        with self.assertRaises(HarnessError):
            self.store.load()

    def test_evidence_snapshot_corruption_detected(self):
        sha = self.store.blob(b"immutable")
        (self.store.root / "blobs" / sha).write_bytes(b"tampered")
        with self.assertRaises(HarnessError):
            self.store.read_blob(sha)

    def test_missing_protocol_not_pooled(self):
        self.run_file(eval_protocol=None)
        sync(self.store)
        rows = compare(self.store.load())["rows"]
        self.assertIsNone(rows[0]["mean"])

    def test_duplicate_seed_not_double_counted(self):
        self.run_file("a", 0)
        self.run_file("retry", 0)
        self.run_file("b", 1, .6)
        sync(self.store)
        row = compare(self.store.load())["rows"][0]
        self.assertEqual(1, row["n"])
        self.assertAlmostEqual(.6, row["mean"])
        self.assertIsNone(row["sd"])

    def test_sample_standard_deviation(self):
        self.run_file("a", 0, .4)
        self.run_file("b", 1, .6)
        sync(self.store)
        row = compare(self.store.load())["rows"][0]
        self.assertAlmostEqual(.5, row["mean"])
        self.assertAlmostEqual(.1414213562, row["sd"])

    def test_compare_selects_only_available_metric_by_default(self):
        path = self.run_file()
        json_write(path / "metrics.json", {"status": "completed", "metrics": {"macro_sr_percent": 68.5}})
        sync(self.store)
        result = compare(self.store.load())
        self.assertEqual("macro_sr_percent", result["metric"])
        self.assertEqual(1, result["rows"][0]["n"])

    def test_default_metric_ignores_stale_result_key(self):
        stale = self.run_file("stale", hardware="A")
        current = self.run_file("current", hardware="B")
        json_write(current / "metrics.json", {"status": "completed", "metrics": {"macro_sr_percent": 68.5}})
        sync(self.store)
        (stale / "metrics.json").unlink()
        sync(self.store)
        result = compare(self.store.load())
        self.assertEqual("macro_sr_percent", result["metric"])
        self.assertEqual(1, sum(row["n"] for row in result["rows"]))

    def test_compare_requires_metric_choice_when_no_default_is_unique(self):
        path = self.run_file()
        json_write(path / "metrics.json", {"status": "completed", "metrics": {"accuracy": .8, "loss": .2}})
        sync(self.store)
        result = compare(self.store.load())
        self.assertEqual(0, result["rows"][0]["n"])
        self.assertTrue(any("specify --metric" in w for w in result["warnings"]))

    def test_cell_config_disagrees_with_runs_not_pooled(self):
        self.run_file("a", 0, .4)
        self.run_file("b", 1, .6)
        sync(self.store)
        state = self.store.load()
        cell = copy.deepcopy(next(n for n in state["nodes"].values() if n["kind"] == "cell"))
        cell["attrs"]["config"]["history_length"] = 99
        self.store.commit({"base_revision": state["revision"], "reason": "Incorrect cell annotation", "nodes": [cell]})
        row = compare(self.store.load())["rows"][0]
        self.assertIsNone(row["mean"])
        self.assertTrue(any("conflicts with the cell" in warning for warning in row["warnings"]))

    def test_agent_semantics_survive_rescan(self):
        self.run_file()
        sync(self.store)
        state = self.store.load()
        cell = next(n for n in state["nodes"].values() if n["kind"] == "cell")
        cell = copy.deepcopy(cell)
        cell["label"] = "Historically confirmed name"
        self.store.commit({"base_revision": state["revision"], "reason": "meaning", "nodes": [cell]})
        sync(self.store)
        self.assertEqual(cell["label"], self.store.load()["nodes"][cell["id"]]["label"])

    def test_multiple_metric_files_not_silently_pooled(self):
        path = self.run_file()
        json_write(path / "results.json", {"status": "completed", "metrics": {"success_rate": .99}})
        out = sync(self.store)
        self.assertTrue(any("Additional metric source" in x for x in out["scan"]["warnings"]))
        self.assertEqual(.5, compare(self.store.load())["rows"][0]["mean"])

    def test_metric_array_is_indexed_without_inventing_a_run(self):
        path = self.run_file()
        json_write(path / "metrics.json", [{"epoch": 1, "top1": 0.3}, {"epoch": 2, "top1": 0.4}])
        out = sync(self.store)
        self.assertTrue(any("JSON metric array indexed as source evidence only" in x
                            for x in out["scan"]["warnings"]))
        self.assertFalse(any(n["kind"] == "run" for n in self.store.load()["nodes"].values()))

    def test_compare_warns_when_cells_reuse_a_training_run(self):
        pid = self.store.load()["project"]["id"]
        entries = []
        for epoch in (1, 2):
            config = {"epoch": epoch, "eval_protocol": "p"}
            cell = node(f"cell-epoch-{epoch}", "cell", f"E{epoch}", pid,
                        attrs={"config": config})
            run = node(f"run-epoch-{epoch}", "run", f"E{epoch} eval", cell["id"],
                       status="completed", attrs={"config": {**config, "seed": 0},
                                                  "seed": 0, "run_id": "same-training-run",
                                                  "eval_protocol": "p", "code_revision": "r1",
                                                  "metrics": {"success_rate": epoch / 10}})
            entries.extend((cell, run))
        self.store.commit({"base_revision": 0, "reason": "Two checkpoint evaluations", "nodes": entries})
        result = compare(self.store.load(), metric="success_rate")
        self.assertTrue(any("recorded run_id values recur across selected cells" in w
                            for w in result["warnings"]))

    def test_archived_cell_is_not_in_current_comparison(self):
        pid = self.store.load()["project"]["id"]
        archived = node("cell-retired", "cell", "Old cell", pid, status="archived",
                        attrs={"config": {"eval_protocol": "p"}})
        run = node("run-retired", "run", "Old run", archived["id"], status="completed",
                   attrs={"config": {"eval_protocol": "p", "seed": 0}, "seed": 0,
                          "eval_protocol": "p", "metrics": {"success_rate": 0.9}})
        self.store.commit({"base_revision": 0, "reason": "Archive old cell", "nodes": [archived, run]})
        self.assertEqual([], compare(self.store.load(), metric="success_rate")["rows"])

    def test_old_results_file_cannot_replace_removed_primary_metric(self):
        path = self.run_file()
        json_write(path / "run.json", {"eval_protocol": "v1"})
        json_write(path / "results.json", {"status": "completed", "eval_protocol": "legacy", "metrics": {"success_rate": .99}})
        sync(self.store)
        (path / "metrics.json").unlink()
        out = sync(self.store)
        self.assertTrue(any("Primary metric source changed" in w for w in out["scan"]["warnings"]))
        self.assertTrue(any("Evaluation protocol conflict" in w for w in out["scan"]["warnings"]))
        state = self.store.load()
        run = next(n for n in state["nodes"].values() if n["kind"] == "run")
        self.assertEqual("needs_review", run["status"])
        self.assertIsNone(compare(state)["rows"][0]["mean"])
        self.assertEqual("archived", next(n for n in state["nodes"].values()
                                          if n["kind"] == "evaluation" and n["label"].endswith("metrics.json"))["status"])
        again = sync(self.store)
        self.assertFalse(again["changed"])
        self.assertEqual("needs_review", next(n for n in self.store.load()["nodes"].values()
                                              if n["kind"] == "run")["status"])

    def test_new_primary_metric_needs_review_even_when_protocol_agrees(self):
        path = self.run_file()
        (path / "metrics.json").unlink()
        json_write(path / "results.json", {"status": "completed", "eval_protocol": "v1",
                                           "metrics": {"success_rate": .5}})
        sync(self.store)
        json_write(path / "metrics.json", {"status": "completed", "eval_protocol": "v1",
                                           "metrics": {"success_rate": .8}})
        out = sync(self.store)
        self.assertTrue(any("Primary metric source changed" in w for w in out["scan"]["warnings"]))
        self.assertFalse(any("Evaluation protocol conflict" in w for w in out["scan"]["warnings"]))
        self.assertIsNone(compare(self.store.load())["rows"][0]["mean"])
        state = self.store.load()
        run = copy.deepcopy(next(n for n in state["nodes"].values() if n["kind"] == "run"))
        run["status"] = "completed"
        run["attrs"].pop("metric_source_transition")
        run["attrs"].pop("ingestion_warning")
        run["evidence"] = [r for r in run["evidence"]
                           if r["file_id"] == run["attrs"]["metric_source_file_id"] or
                           state["files"][r["file_id"]]["path"].endswith(("run.json", "config.json"))]
        self.store.commit({"base_revision": state["revision"], "reason": "Agent checked both metric sources and protocol",
                           "nodes": [run]})
        sync(self.store)  # clears the scanner's old transition warning
        self.assertFalse(sync(self.store)["changed"])
        self.assertAlmostEqual(.8, compare(self.store.load())["rows"][0]["mean"])

    def test_metric_protocol_conflict_without_source_switch_is_excluded(self):
        path = self.run_file()
        json_write(path / "metrics.json", {"status": "completed", "eval_protocol": "legacy",
                                           "metrics": {"success_rate": .9}})
        out = sync(self.store)
        self.assertTrue(any("Evaluation protocol conflict" in w for w in out["scan"]["warnings"]))
        self.assertFalse(any("Primary metric source changed" in w for w in out["scan"]["warnings"]))
        self.assertIsNone(compare(self.store.load())["rows"][0]["mean"])

    def test_unverified_completion_not_pooled(self):
        path = self.run_file()
        json_write(path / "metrics.json", {"metrics": {"success_rate": .99}})
        sync(self.store)
        self.assertIsNone(compare(self.store.load())["rows"][0]["mean"])

    def test_toml_and_csv_are_supported(self):
        directory = self.root / "r"
        directory.mkdir()
        (directory / "config.toml").write_text('seed = 0\neval_protocol = "v1"\n')
        (directory / "metrics.csv").write_text('step,success_rate\n1,0.4\n2,0.5\n')
        sync(self.store)
        run = next(n for n in self.store.load()["nodes"].values() if n["kind"] == "run")
        self.assertEqual(.5, run["attrs"]["metrics"]["success_rate"])
        self.assertEqual("recorded", run["status"])

    def test_changed_config_does_not_silently_relabel_cell(self):
        path = self.run_file()
        sync(self.store)
        state = self.store.load()
        rid = next(n["id"] for n in state["nodes"].values() if n["kind"] == "run")
        old_parent = state["nodes"][rid]["parent_id"]
        cfg = read_json(path / "config.json")
        cfg["train_steps"] = 200
        json_write(path / "config.json", cfg)
        sync(self.store)
        current = self.store.load()["nodes"][rid]
        self.assertEqual(old_parent, current["parent_id"])
        self.assertEqual("needs_review", current["status"])
        self.assertIsNone(compare(self.store.load())["rows"][0]["mean"])

    def test_conflicting_recorded_run_id_not_pooled(self):
        a = self.run_file("a", 0, .4)
        b = self.run_file("b", 0, .6)
        json_write(a / "run.json", {"run_id": "same-recorded-id"})
        json_write(b / "run.json", {"run_id": "same-recorded-id"})
        result = sync(self.store)
        self.assertTrue(any("Conflicting recorded run identity" in w for w in result["scan"]["warnings"]))
        run = next(n for n in self.store.load()["nodes"].values() if n["kind"] == "run")
        self.assertEqual("needs_review", run["status"])

    def test_accepted_claim_requires_immutable_source(self):
        pid = self.store.load()["project"]["id"]
        n = node("claim", "claim", "Unsupported", pid, status="accepted", attrs={"scope": {"dataset": "d1"}})
        with self.assertRaises(HarnessError):
            self.store.commit({"base_revision": 0, "reason": "unsupported", "nodes": [n]})

    def test_prominent_finding_requires_source_and_scope_without_breaking_old_claims(self):
        pid = self.store.load()["project"]["id"]
        legacy = node("claim-legacy", "claim", "Older note", pid)
        self.store.commit({"base_revision": 0, "reason": "legacy claim", "nodes": [legacy]})
        featured = node("claim-main", "claim", "Main finding", pid,
                        attrs={"finding": {"priority": "primary", "type": "effect"}})
        with self.assertRaisesRegex(HarnessError, "direct evidence and scope"):
            self.store.commit({"base_revision": 1, "reason": "no source", "nodes": [featured]})
        self.assertIn("claim-legacy", self.store.load()["nodes"])

    def test_project_timeline_requires_a_real_date_and_direct_source(self):
        (self.root / "milestone.md").write_text("Study completed on 2026-01-20.", encoding="utf-8")
        sync(self.store)
        state = self.store.load()
        source = next(f for f in state["files"].values() if f["path"] == "milestone.md")
        event = node("artifact-milestone", "artifact", "Study completed", state["project"]["id"],
                     attrs={"project_event": {"date": "2026-01-20", "date_precision": "day",
                                              "date_basis": {"zh": "报告明示完成日", "en": "Explicit completion date"},
                                              "related_ids": []}})
        with self.assertRaisesRegex(HarnessError, "direct evidence"):
            self.store.commit({"base_revision": state["revision"], "reason": "unsourced event", "nodes": [event]})
        event["evidence"] = [evidence_ref(source, "completion sentence")]
        event["attrs"]["project_event"]["date"] = "2026-02-30"
        with self.assertRaisesRegex(HarnessError, "Invalid project event date"):
            self.store.commit({"base_revision": state["revision"], "reason": "bad date", "nodes": [event]})
        event["attrs"]["project_event"]["date"] = "2026-01-20"
        self.store.commit({"base_revision": state["revision"], "reason": "sourced milestone", "nodes": [event]})
        self.assertEqual("2026-01-20", self.store.load()["nodes"][event["id"]]["attrs"]["project_event"]["date"])

    def test_study_summary_table_rejects_missing_values(self):
        state = self.store.load()
        study = node("module-study", "module", "Synthetic study", state["project"]["id"],
                     attrs={"study_summary": {"zh": {"columns": ["条件", "成功率"], "rows": [["对照"]]}}})
        with self.assertRaisesRegex(HarnessError, "study_summary rows"):
            self.store.commit({"base_revision": state["revision"], "reason": "partial table", "nodes": [study]})
        study["attrs"]["study_summary"]["zh"]["rows"] = [["对照", "50%"]]
        with self.assertRaisesRegex(HarnessError, "direct evidence"):
            self.store.commit({"base_revision": state["revision"], "reason": "unsourced table", "nodes": [study]})
        (self.root / "table.md").write_text("Synthetic control success: 50%", encoding="utf-8")
        sync(self.store)
        current = self.store.load()
        source = next(f for f in current["files"].values() if f["path"] == "table.md")
        study["evidence"] = [evidence_ref(source, "synthetic control result")]
        self.store.commit({"base_revision": current["revision"], "reason": "sourced table", "nodes": [study]})

    def test_finding_card_requires_sourced_bilingual_claim(self):
        state = self.store.load()
        content = {"value": "+5 pp", "label": "Success change", "context": "Synthetic paired study", "limit": "One seed"}
        finding = node("claim-card", "claim", "Synthetic finding", state["project"]["id"],
                       attrs={"finding_card": {"zh": dict(content), "en": dict(content)}})
        with self.assertRaisesRegex(HarnessError, "sourced claim"):
            self.store.commit({"base_revision": state["revision"], "reason": "unsourced card", "nodes": [finding]})
        (self.root / "card.md").write_text("Synthetic paired difference: +5 pp, one seed.", encoding="utf-8")
        sync(self.store)
        current = self.store.load()
        source = next(f for f in current["files"].values() if f["path"] == "card.md")
        finding["evidence"] = [evidence_ref(source, "paired difference")]
        del finding["attrs"]["finding_card"]["en"]["limit"]
        with self.assertRaisesRegex(HarnessError, "Invalid finding card content"):
            self.store.commit({"base_revision": current["revision"], "reason": "partial card", "nodes": [finding]})
        finding["attrs"]["finding_card"]["en"]["limit"] = "One seed"
        self.store.commit({"base_revision": current["revision"], "reason": "sourced card", "nodes": [finding]})
        self.assertEqual("+5 pp", self.store.load()["nodes"][finding["id"]]["attrs"]["finding_card"]["zh"]["value"])

    def test_source_text_not_executed(self):
        marker = self.root / "EXECUTED"
        (self.root / "evil.py").write_text(f'from pathlib import Path\nPath({str(marker)!r}).write_text("bad")')
        sync(self.store)
        self.assertFalse(marker.exists())

    def test_offline_export_escapes_script_injection(self):
        pid = self.store.load()["project"]["id"]
        n = node("m", "module", '</script><script>alert(1)</script>', pid)
        self.store.commit({"base_revision": 0, "reason": "test escaping", "nodes": [n]})
        output = Path(self.temp.name) / "out.html"
        export_html(self.store, output)
        text = output.read_text(encoding="utf-8")
        self.assertNotIn('</script><script>alert(1)</script>', text)
        self.assertIn('\\u003c/script\\u003e', text)
        self.assertNotIn('src="/app.js"', text)

    def test_offline_export_includes_unreferenced_indexed_text(self):
        (self.root / "unmapped.md").write_text("Unmapped source content", encoding="utf-8")
        sync(self.store)
        item = next(f for f in self.store.load()["files"].values() if f["path"] == "unmapped.md")
        output = Path(self.temp.name) / "with-evidence.html"
        export_html(self.store, output, include_evidence=True)
        payload = output.read_text(encoding="utf-8").partition(
            '<script id="snapshot-data" type="application/json">')[2].partition("</script>")[0]
        self.assertEqual("Unmapped source content", json.loads(payload)["evidence_texts"][item["sha256"]])

    def test_export_site_keeps_project_snapshots_separate_and_switchable(self):
        other_root = Path(self.temp.name) / "other-project"
        other = Store(other_root)
        other.init("Other study")
        (self.root / "alpha.md").write_text("Alpha-only evidence", encoding="utf-8")
        (other_root / "beta.md").write_text("Beta-only evidence", encoding="utf-8")
        sync(self.store)
        sync(other)
        output = Path(self.temp.name) / "site"
        result = export_site([self.root, other_root], output, include_evidence=True)
        self.assertEqual(str((output / "index.html").resolve()), result["index"])
        pages = [output / "index.html", *[Path(item["page"]) for item in result["projects"]]]
        payloads = []
        for page in pages:
            html = page.read_text(encoding="utf-8")
            self.assertIn('id="project-switcher"', html)
            packed = html.partition('<script id="snapshot-data" type="application/json">')[2].partition("</script>")[0]
            payloads.append(json.loads(packed))
        self.assertEqual(self.store.load()["project"]["id"], payloads[0]["project"]["id"])
        self.assertEqual({"alpha.md"}, {f["path"] for f in payloads[1]["files"].values()})
        self.assertEqual({"beta.md"}, {f["path"] for f in payloads[2]["files"].values()})
        self.assertEqual(["projects/test.html", "projects/other-study.html"],
                         [link["href"] for link in payloads[0]["site_links"]])
        self.assertEqual(["test.html", "other-study.html"],
                         [link["href"] for link in payloads[2]["site_links"]])
        self.assertNotIn("Beta-only evidence", pages[1].read_text(encoding="utf-8"))
        with self.assertRaisesRegex(HarnessError, "Unsafe"):
            export_html(self.store, output / "unsafe.html", site_links=[
                {"id": self.store.load()["project"]["id"], "name": "Test", "href": "javascript:alert(1).html"}])

    def test_skill_install_refuses_user_overwrite(self):
        result = install_skill("codex", self.root, False)
        p = Path(result["installed"][0]) / "SKILL.md"
        p.write_text("User edited this")
        with self.assertRaises(HarnessError):
            install_skill("codex", self.root, False)

    def test_skill_installer_upgrades_unchanged_managed_content(self):
        result = install_skill("codex", self.root, False)
        skill = Path(result["installed"][0])
        old = b"Older bundled Skill text\n"
        (skill / "SKILL.md").write_bytes(old)
        marker = read_json(skill / "INSTALL_MANIFEST.json")
        marker["managed"]["SKILL.md"] = hashlib.sha256(old).hexdigest()
        json_write(skill / "INSTALL_MANIFEST.json", marker)
        install_skill("codex", self.root, False)
        source_skill = Path(__file__).resolve().parents[1] / "research_harness" / "skill" / "research-harness" / "SKILL.md"
        self.assertEqual(source_skill.read_bytes(), (skill / "SKILL.md").read_bytes())
        self.assertEqual(hashlib.sha256(source_skill.read_bytes()).hexdigest(),
                         read_json(skill / "INSTALL_MANIFEST.json")["managed"]["SKILL.md"])

    def test_installer_does_not_touch_agents_md(self):
        p = self.root / "AGENTS.md"
        p.write_text("Do not replace")
        install_skill("codex", self.root, False)
        self.assertEqual("Do not replace", p.read_text())
        self.assertTrue((self.root / ".agents/skills/research-harness/SKILL.md").exists())

class DecisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name) / "demo"
        create_demo(cls.root)
        cls.store = Store(cls.root)
        cls.state = cls.store.load()
        cls.proposal = read_json(cls.store.root / "proposal-covered.json")

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_hardware_coverage_is_inherited(self):
        out = assess(self.state, self.proposal)
        self.assertEqual("covered_by_confirmed_scope", out["outcome"])
        self.assertFalse(out["automatic_execution"])
        self.assertTrue(out["replication"])

    def test_changed_protocol_reopens_not_automatic_training(self):
        proposal = copy.deepcopy(self.proposal)
        proposal["config"]["eval_protocol"] = "v2"
        out = assess(self.state, proposal)
        self.assertEqual("needs_review_not_automatic_new_experiment", out["outcome"])
        self.assertFalse(out["coverage"])

    def test_new_factor_requires_scope_review(self):
        proposal = copy.deepcopy(self.proposal)
        proposal["config"]["batch_size"] = 512
        self.assertFalse(assess(self.state, proposal)["coverage"])

    def test_unknown_hardware_not_covered(self):
        proposal = copy.deepcopy(self.proposal)
        proposal["config"]["hardware"] = "GPU-C"
        self.assertFalse(assess(self.state, proposal)["coverage"])

    def test_missing_context_not_treated_as_equal(self):
        proposal = copy.deepcopy(self.proposal)
        del proposal["config"]["precision"]
        self.assertFalse(assess(self.state, proposal)["coverage"])

    def test_user_confirmation_required(self):
        state = copy.deepcopy(self.state)
        state["nodes"]["decision-hardware"]["protected"] = False
        self.assertFalse(assess(state, self.proposal)["coverage"])

    def test_changed_source_does_not_silently_rewrite_decision(self):
        state = copy.deepcopy(self.state)
        ref = state["nodes"]["decision-hardware"]["evidence"][0]
        state["files"][ref["file_id"]]["sha256"] = "b" * 64
        out = assess(state, self.proposal)
        self.assertFalse(out["coverage"])
        self.assertEqual(self.state["nodes"]["decision-hardware"], state["nodes"]["decision-hardware"])

    def test_demo_noop_scan(self):
        before = self.store.load()["revision"]
        sync(self.store)
        self.assertEqual(before, self.store.load()["revision"])

class ServerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(self.temp.name)
        self.store.init("HTTP test")
        self.server = make_server(self.store, 0, "unit-test-token")
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def request(self, path, **headers):
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=4)
        conn.request("GET", path, headers=headers)
        response = conn.getresponse()
        status, body = response.status, response.read()
        conn.close()
        return status, body

    def test_api_requires_token(self):
        self.assertEqual(403, self.request("/api/state")[0])
        self.assertEqual(200, self.request("/api/state", **{"X-Research-Token": "unit-test-token"})[0])

    def test_invalid_host_blocked(self):
        self.assertEqual(403, self.request("/api/state", **{"Host": "attacker.example", "X-Research-Token": "unit-test-token"})[0])

    def test_unknown_evidence_cannot_traverse(self):
        self.assertEqual(400, self.request("/api/evidence?sha=../../etc/passwd", **{"X-Research-Token": "unit-test-token"})[0])

    def test_cross_site_read_blocked(self):
        self.assertEqual(403, self.request("/api/state", **{"Sec-Fetch-Site": "cross-site", "X-Research-Token": "unit-test-token"})[0])

if __name__ == "__main__":
    unittest.main()
