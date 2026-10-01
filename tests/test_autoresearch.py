"""Offline lifecycle and evidence regressions; no model credentials or GPU needed."""
from __future__ import annotations

from contextlib import closing
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

from research_harness.autoresearch import Campaign, prepare, validate_spec, worker_lease
from research_harness.backends.shinka import ShinkaBackend, inspect_installation, read_programs, REVISION
from research_harness.store import Store, HarnessError, Conflict, read_json
from research_harness.reasoning import compare
from research_harness.scan import sync
from research_harness.server import export_html


def write_native(directory: Path, count: int, *, changed_code=False):
    directory.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(directory / "programs.sqlite")) as db, db:
        db.execute("CREATE TABLE IF NOT EXISTS programs (id TEXT PRIMARY KEY, code TEXT, parent_id TEXT, generation INTEGER, correct INTEGER, combined_score REAL, public_metrics TEXT, private_metrics TEXT, metadata TEXT, island_idx INTEGER)")
        for gen in range(count):
            db.execute("INSERT OR IGNORE INTO programs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                       (f"native-{gen}", f"def solution(): return {gen}\n", f"native-{gen-1}" if gen else None,
                        gen, int(gen != 1), gen / 10, json.dumps({"success": gen != 1}), "{}",
                        json.dumps({"note": "synthetic native-format fixture", "api_costs": None}), gen % 2))
        if changed_code:
            db.execute("UPDATE programs SET code='different' WHERE id='native-0'")


class FixtureBackend:
    """Controlled native-shaped outputs, explicitly not a Shinka search execution."""
    def __init__(self, before_return=None):
        self.targets = []
        self.before_return = before_return

    def run_batch(self, contract, directory, target):
        self.targets.append(target)
        write_native(directory / "native", target)
        if self.before_return:
            self.before_return()

    def collect(self, directory):
        return read_programs(directory / "native")


class ResearchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.workspace = self.root / "workspace"
        Store(self.workspace).init("Synthetic tests", synthetic=True)
        self.task = self.root / "task"
        self.task.mkdir()
        (self.task / "initial.py").write_text("def solution(): return 0\n")
        (self.task / "evaluate.py").write_text("raise RuntimeError('prepare must not execute task code')\n")
        self.spec = {"id": "test", "question": "Synthetic improvement?", "task_dir": "task",
                     "files": ["initial.py", "evaluate.py"], "models": ["test-model"],
                     "max_generations": 4, "batch_size": 2, "evaluation_timeout_seconds": 10,
                     "evaluation_protocol": "synthetic-v1"}
        prepare(self.workspace, self.spec, spec_directory=self.root)
        self.c = Campaign(self.workspace, "test")

    def tearDown(self):
        self.temp.cleanup()

    def arm(self, token="token"):
        _, state = self.c.load()
        self.c.save(state, "starting", launch_token=token, stop_requested=False)
        return token

    def test_prepare_is_static_idempotent_and_freezes_inputs(self):
        first = Store(self.workspace).load()["revision"]
        prepare(self.workspace, self.spec, spec_directory=self.root)
        self.assertEqual(first, Store(self.workspace).load()["revision"])
        (self.task / "initial.py").write_text("changed source\n")
        self.assertEqual("def solution(): return 0\n", (self.c.directory / "task/initial.py").read_text())
        with self.assertRaisesRegex(HarnessError, "different frozen contract"):
            prepare(self.workspace, self.spec, spec_directory=self.root)

    def test_dry_run_never_imports_backend_or_launches(self):
        with patch.object(ShinkaBackend, "preflight", side_effect=AssertionError("no SDK")), patch("subprocess.Popen", side_effect=AssertionError("no process")):
            self.assertTrue(self.c.start()["dry_run"])
        self.assertEqual("ready", self.c.status()["phase"])

    def test_cli_prepare_and_status_without_optional_dependencies(self):
        cli = Path(__file__).resolve().parents[1] / "labweft.py"
        for args in (["research", "status", str(self.workspace), "test"], ["research", "start", str(self.workspace), "test"]):
            result = subprocess.run([sys.executable, str(cli), *args], capture_output=True, check=True)
            self.assertIsInstance(json.loads(result.stdout), dict)

    def test_real_synthetic_evaluator_baseline_improvement_and_failure(self):
        task = Path(__file__).resolve().parents[1] / "examples/shinka/task"
        program = self.root / "candidate.py"
        cases = [(task / "initial.py", None), (program, "def predict(x): return x*x\n"),
                 (program, "raise RuntimeError('invalid candidate')\n")]
        reports = []
        for index, (candidate, source) in enumerate(cases):
            if source is not None:
                candidate.write_text(source)
            output = self.root / f"eval-{index}"
            subprocess.run([sys.executable, str(task / "evaluate.py"), "--program_path", str(candidate),
                            "--results_dir", str(output)], check=True, capture_output=True)
            reports.append((read_json(output / "correct.json"), read_json(output / "metrics.json")))
        self.assertTrue(reports[0][0]["correct"])
        self.assertGreater(reports[1][1]["combined_score"], reports[0][1]["combined_score"])
        self.assertEqual(1.0, reports[1][1]["combined_score"])
        self.assertFalse(reports[2][0]["correct"])

    def test_source_drift_blocks_execution(self):
        (self.c.directory / "task/evaluate.py").write_text("changed judge")
        with self.assertRaisesRegex(HarnessError, "Frozen task file changed"):
            self.c.start(execute=True)

    def test_no_path_traversal_or_secret_snapshot(self):
        for name in ("../outside", "/absolute", "C:/Windows/test", ".env", "folder/../x", "folder\\file", "credentials.json"):
            spec = {**self.spec, "files": ["initial.py", "evaluate.py", name]}
            with self.subTest(name=name), self.assertRaises(HarnessError):
                validate_spec(spec)
        for key, val in (("max_generations", True), ("batch_size", 0), ("max_api_cost_usd", float("nan")), ("models", [])):
            with self.subTest(key=key), self.assertRaises(HarnessError):
                validate_spec({**self.spec, key: val})

    def test_completed_loop_imports_failures_and_lineage_without_promotion(self):
        fake = FixtureBackend()
        self.c.run(self.arm(), fake)
        self.assertEqual([2, 4], fake.targets)
        self.assertEqual("completed", self.c.status()["phase"])
        state = Store(self.workspace).load()
        runs = [n for n in state["nodes"].values() if n["kind"] == "run"]
        self.assertEqual(4, len(runs))
        self.assertEqual(1, sum(n["attrs"]["backend_correct"] is False for n in runs))
        self.assertEqual(3, len(state["edges"]))
        self.assertFalse(any(n.get("confirmation") for n in state["nodes"].values()))
        self.assertTrue(all(n["attrs"]["cost"]["billed_amount"] is None for n in runs))
        self.assertTrue(all(row["n"] == 0 for row in compare(state)["rows"]))
        self.assertFalse(self.c.collect()["changed"])
        sync(Store(self.workspace))
        self.assertFalse(any(f["missing"] for f in Store(self.workspace).load()["files"].values() if f["source"] == "autoresearch"))
        output = self.root / "map.html"
        export_html(Store(self.workspace), output)
        self.assertIn("Shinka generation", output.read_text(encoding="utf-8"))

    def test_stop_drains_batch_resume_keeps_generation_identity(self):
        fake = FixtureBackend(self.c.stop)
        self.c.run(self.arm(), fake)
        self.assertEqual([2], fake.targets)
        self.assertEqual("paused", self.c.status()["phase"])
        self.assertEqual(2, self.c.status()["completed_generations"])
        fake = FixtureBackend()
        self.c.run(self.arm("second"), fake)
        self.assertEqual([4], fake.targets)
        self.assertEqual(4, len(read_programs(self.c.directory / "native")))

    def test_stop_before_worker_prevents_any_execution(self):
        token = self.arm()
        self.c.stop()
        fake = FixtureBackend()
        self.c.run(token, fake)
        self.assertEqual([], fake.targets)
        self.assertEqual("paused", self.c.status()["phase"])

    def test_incomplete_batch_requires_review_no_retries(self):
        class Partial(FixtureBackend):
            def run_batch(self, contract, directory, target):
                self.targets.append(target)
                write_native(directory / "native", 1)
        fake = Partial()
        self.c.run(self.arm(), fake)
        self.assertEqual([2], fake.targets)
        self.assertEqual("needs_review", self.c.status()["phase"])
        with patch.object(ShinkaBackend, "preflight", return_value={}):
            with self.assertRaisesRegex(HarnessError, "Cannot resume"):
                self.c.start(execute=True, resume=True)

    def test_crash_keeps_records_and_does_not_auto_resume(self):
        def crash():
            raise RuntimeError("fixture interruption")
        with self.assertRaisesRegex(RuntimeError, "fixture interruption"):
            self.c.run(self.arm(), FixtureBackend(crash))
        self.assertEqual("needs_review", self.c.status()["phase"])
        self.assertEqual(2, self.c.collect()["reported_candidates"])

    def test_dead_worker_is_reported_as_ambiguous(self):
        _, state = self.c.load()
        self.c.save(state, "running", active_target=2, launch_token="dead")
        self.assertEqual("needs_review", self.c.status()["effective_phase"])
        self.assertEqual("running", self.c.status()["phase"])

    def test_live_worker_cannot_be_duplicated(self):
        with worker_lease(self.c.directory / "worker.lock"):
            self.assertTrue(self.c.status()["worker_lock_held"])
            with self.assertRaises(Conflict):
                self.c.run("other", FixtureBackend())

    def test_resume_cannot_race_with_a_draining_worker(self):
        _, state = self.c.load()
        self.c.save(state, "paused")
        with worker_lease(self.c.directory / "worker.lock"), patch.object(ShinkaBackend, "preflight", return_value={}):
            with self.assertRaises(Conflict):
                self.c.start(execute=True, resume=True)

    def test_start_is_idempotently_rejected_and_argv_not_shell(self):
        child = types.SimpleNamespace(pid=1234)
        with patch.object(ShinkaBackend, "preflight", return_value={"revision": REVISION}), patch("subprocess.Popen", return_value=child) as popen:
            self.c.start(execute=True)
            with self.assertRaisesRegex(HarnessError, "Cannot start"):
                self.c.start(execute=True)
            self.assertEqual(1, popen.call_count)
            self.assertNotIn("shell", popen.call_args.kwargs)
            self.assertIsInstance(popen.call_args.args[0], list)

    def test_candidate_id_cannot_be_reused_for_other_code(self):
        write_native(self.c.directory / "native", 2)
        self.c.collect()
        before = Store(self.workspace).load()["revision"]
        write_native(self.c.directory / "native", 2, changed_code=True)
        with self.assertRaisesRegex(HarnessError, "identity reused"):
            self.c.collect()
        self.assertEqual(before, Store(self.workspace).load()["revision"])

    def test_missing_schema_or_nonfinite_score_not_success(self):
        write_native(self.c.directory / "native", 1)
        with closing(sqlite3.connect(self.c.directory / "native/programs.sqlite")) as db, db:
            db.execute("UPDATE programs SET combined_score=?, correct=NULL", (float("inf"),))
        records = read_programs(self.c.directory / "native")
        self.assertIsNone(records[0]["combined_score"])
        self.assertIsNone(records[0]["correct"])
        with closing(sqlite3.connect(self.c.directory / "native/programs.sqlite")) as db, db:
            db.execute("DROP TABLE programs")
        with self.assertRaisesRegex(HarnessError, "Unsupported"):
            self.c.collect()


class BackendContractTests(unittest.TestCase):
    def test_unpinned_installation_rejected_without_import(self):
        dist = types.SimpleNamespace(version="0.0.7", read_text=lambda name: None)
        with patch("importlib.metadata.distribution", return_value=dist):
            with self.assertRaisesRegex(HarnessError, "requires upstream revision"):
                inspect_installation()

    def test_adapter_calls_public_runner_with_absolute_budget_and_no_hidden_models(self):
        captured = {}
        class Config:
            def __init__(self, **kwargs):
                self.values = kwargs
        class Runner:
            def __init__(self, **kwargs):
                captured.update(kwargs)
            def run(self):
                captured["ran"] = True
        modules = {"shinka.core": types.SimpleNamespace(EvolutionConfig=Config, ShinkaEvolveRunner=Runner),
                   "shinka.database": types.SimpleNamespace(DatabaseConfig=Config),
                   "shinka.launch": types.SimpleNamespace(LocalJobConfig=Config)}
        contract = {"question": "test", "instructions": "test", "models": ["explicit-model"],
                    "evaluation_timeout_seconds": 65, "max_api_cost_usd": 1.5,
                    "num_islands": 2, "max_evaluation_jobs": 1}
        with patch.dict(sys.modules, modules), patch.object(ShinkaBackend, "preflight", return_value={}):
            ShinkaBackend().run_batch(contract, Path("/task"), 6)
        self.assertTrue(captured["ran"])
        self.assertEqual(6, captured["evo_config"].values["num_generations"])
        self.assertEqual(1.5, captured["evo_config"].values["max_api_costs"])
        self.assertIsNone(captured["evo_config"].values["embedding_model"])
        self.assertIsNone(captured["evo_config"].values["meta_rec_interval"])
        self.assertEqual("00:01:05", captured["job_config"].values["time"])


if __name__ == "__main__":
    unittest.main()
