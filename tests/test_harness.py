from __future__ import annotations
import copy
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
from research_harness.server import make_server, export_html
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
        self.assertEqual(str(workspace), payload["workspace"])
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

    def test_deleted_file_keeps_original_snapshot(self):
        p = self.root / "notes.md"
        p.write_text("initial evidence")
        sync(self.store)
        file = next(iter(self.store.load()["files"].values()))
        p.unlink()
        sync(self.store)
        self.assertTrue(self.store.load()["files"][file["id"]]["missing"])
        self.assertEqual("initial evidence", self.store.read_blob(file["sha256"]))

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

    def test_skill_install_refuses_user_overwrite(self):
        result = install_skill("codex", self.root, False)
        p = Path(result["installed"][0]) / "SKILL.md"
        p.write_text("User edited this")
        with self.assertRaises(HarnessError):
            install_skill("codex", self.root, False)

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
