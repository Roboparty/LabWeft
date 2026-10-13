import json
import statistics
import tempfile
import unittest
from pathlib import Path

from research_harness.store import Store
from research_harness.trace import analyze, index, ledger, mcp, probe, tools
from research_harness.trace.analyze import name_tokens, split_kv_list


def make_project(root: Path) -> dict:
    """Synthetic project: an encoded-name ablation (aw x rh x 3 seeds), a task table, a launcher and a report."""
    values = {}
    for aw in ("0.1", "0.3"):
        for rh in ("1", "5"):
            for s in (7, 8, 9):
                run = root / "results" / "sweep" / f"aw{aw}_lw0.1_rh{rh}_s{s}"
                run.mkdir(parents=True)
                sr = 80 + (10 if aw == "0.3" else 0) + (2 if rh == "5" else 0) + s - 8
                values.setdefault((aw, rh), []).append(sr)
                (run / "result.json").write_text(json.dumps({"successes": sr, "episodes": 100, "seed": s,
                                                             "solver_args": f"num_candidates=64,noise_scale={aw}"}))
    rows = ["task,train_seed,success_rate,method"]
    for task in ("cube", "pusht"):
        for seed in (1, 2, 3):
            for method in ("base", "ours"):
                rows.append(f"{task},{seed},{0.5 + 0.1 * seed + (0.2 if method == 'ours' else 0):.2f},{method}")
    (root / "results" / "tables").mkdir(parents=True)
    (root / "results" / "tables" / "final.csv").write_text("\n".join(rows) + "\n")
    (root / "scripts").mkdir()
    (root / "scripts" / "sweep.sh").write_text("#!/bin/bash\npython train.py --config configs/base.yaml --output_dir results/sweep/aw0.1_lw0.1_rh1_s7\n")
    (root / "configs").mkdir()
    (root / "configs" / "base.yaml").write_text("optim:\n  lr: 0.0003\n  batch_size: 256\nmodel: demo\n")
    a = values[("0.3", "5")]
    b = values[("0.1", "1")]
    report = ("# Sweep report\n\n## Main result\n\n"
              f"| cell | SR |\n|---|---|\n| aw0.3 rh5 | {statistics.fmean(a):.2f} ± {statistics.stdev(a):.2f} |\n"
              f"| aw0.1 rh1 | {statistics.fmean(b):.2f} ± {statistics.pstdev(b):.2f} |\n"
              "\nAn unrelated number 12.345 appears here.\n")
    (root / "REPORT.md").write_text(report, encoding="utf-8")
    (root / "secrets.env").write_text("API_KEY=sk-should-not-be-read\n")
    import io as _io
    import tarfile as _tarfile
    note = "# Bundled comparison\n\nSpatial Lite has 2.817M parameters versus 21.144M.\n".encode()
    with _tarfile.open(root / "bundle.tgz", "w:gz") as tf:
        info = _tarfile.TarInfo("./docs/COMPARISON.md")
        info.size = len(note)
        tf.addfile(info, _io.BytesIO(note))
    return values


class TraceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.src = base / "project"
        self.src.mkdir()
        self.values = make_project(self.src)
        self.ws = base / "ws"
        tools.t_collect(str(self.ws), "proj", str(self.src))
        self.con = index.connect(self.ws, "proj")
        self.addCleanup(self.con.close)

    def tearDown(self):
        self.con.close()
        self.tmp.cleanup()

    def test_name_tokens_and_kv_lists(self):
        keyed, tags = name_tokens("min_n128_sg0.25_rh1_s7")
        self.assertEqual(keyed, {"n": "128", "sg": "0.25", "rh": "1", "s": "7"})
        self.assertEqual(tags, ["min"])
        self.assertEqual(name_tokens("eval_seed_42")[0], {"eval_seed": "42"})
        self.assertEqual(split_kv_list("num_candidates=64,noise_scale=0.5"), {"num_candidates": "64", "noise_scale": "0.5"})

    def test_probe_is_read_only_and_skips_secrets(self):
        with self.assertRaises(SystemExit):
            probe.main(["--root", str(self.src), "--out", str(self.src / "x.jsonl")])
        row = self.con.execute("SELECT status, reason FROM files WHERE path = 'secrets.env'").fetchone()
        self.assertEqual((row["status"], row["reason"]), ("skipped", "sensitive_name"))
        self.assertIsNone(self.con.execute("SELECT 1 FROM facts WHERE json LIKE '%sk-should%'").fetchone())

    def test_overview_coverage_is_complete(self):
        out = analyze.overview(self.con)
        self.assertEqual(out["coverage"]["status"], "complete")
        self.assertIn("result", out["roles"])

    def test_experiments_recover_factors_from_run_names(self):
        out = analyze.experiments(self.con, limit=50)
        sweep = next(s for s in out["studies"]["items"] if s["source"].startswith("results/sweep"))
        keys = {f["key"] for f in sweep["factors"]}
        aliases = {a for f in sweep["factors"] for a in f["aliases"]}
        # `aw` in the run name and `noise_scale` in the result file are one factor; the file is the stronger authority.
        self.assertIn("solver_args.noise_scale", keys)
        self.assertIn("aw", aliases)
        self.assertIn("rh", keys)
        self.assertNotIn("lw", keys)  # constant in the run names
        self.assertEqual(sweep["cells"], 4)
        self.assertEqual(sweep["replicates_per_cell"], {3: 4})
        self.assertIn("seed", sweep["replicate_keys"])
        axes = {a["factor"] for a in sweep["controlled_axes"]}
        self.assertTrue({"solver_args.noise_scale", "rh"} <= axes)
        best = sweep["top_cells"][0]
        self.assertEqual((best["levels"]["solver_args.noise_scale"], best["levels"]["rh"]), ("0.3", "5"))
        self.assertAlmostEqual(best["stats"]["mean"], statistics.fmean(self.values[("0.3", "5")]))

    def test_experiments_table_rows_keep_task_as_context(self):
        out = analyze.experiments(self.con, limit=50)
        table = next(s for s in out["studies"]["items"] if s["source"].endswith("final.csv"))
        roles = {f["key"]: f["role"] for f in table["factors"]}
        self.assertEqual(roles.get("task"), "context")
        self.assertEqual(roles.get("method"), "treatment")
        self.assertEqual(table["replicate_keys"], ["train_seed"])

    def test_reconcile_detects_sd_conventions_and_unsourced(self):
        out = analyze.reconcile(self.con, path="REPORT.md", limit=50)
        items = out["numbers"]["items"]
        pm = [n for n in items if n["kind"] == "mean±sd"]
        self.assertEqual([n["state"] for n in pm], ["derived", "derived"])
        self.assertEqual(pm[0]["sd_conventions"], ["sample"])
        self.assertEqual(pm[1]["sd_conventions"], ["population"])
        stray = next(n for n in items if n["number"] == "12.345")
        self.assertEqual(stray["state"], "unsourced")

    def test_provenance_and_xrefs(self):
        out = analyze.provenance(self.con, "results/sweep/aw0.1_lw0.1_rh1_s7/result.json")
        self.assertEqual(out["status"], "found")
        self.assertIn("scripts/sweep.sh", {p["file"] for p in out["producers"]})
        x = analyze.xrefs(self.con, "base.yaml")
        self.assertIn("scripts/sweep.sh", {r["from"] for r in x["refs"]["items"]})

    def test_not_found_only_when_exhaustive(self):
        self.assertEqual(analyze.search(self.con, "zz-no-such-token")["status"], "not_found")
        self.con.execute  # read-only connection; simulate partial coverage through result()
        partial = {"complete": False}
        orig = analyze.meta
        analyze.meta = lambda con: partial
        try:
            self.assertEqual(analyze.search(self.con, "zz-no-such-token")["status"], "unknown")
        finally:
            analyze.meta = orig

    def test_fetch_propose_apply_and_obligations(self):
        Store(self.ws).init("proj")
        sweep = next(s for s in analyze.experiments(self.con, limit=50)["studies"]["items"] if s["source"].startswith("results/sweep"))
        fetched = tools.t_fetch(str(self.ws), "proj", study=sweep["id"], sync=True)
        self.assertEqual(fetched["fetched"], 12)
        self.assertEqual(fetched["changed_since_probe"], [])
        prop = tools.t_propose(str(self.ws), "proj", sweep["id"], eval_protocol="synthetic-v1")
        self.assertEqual(prop["missing_evidence_paths"], [])
        patch = prop["patch"]
        self.assertEqual(sum(n["kind"] == "run" for n in patch["nodes"]), 12)
        store = Store(self.ws)
        store.commit(patch)
        led = ledger.obligations(self.ws, limit=100)
        codes = led["by_code"]
        self.assertNotIn("locator-unresolved", codes)
        self.assertNotIn("missing-evidence", codes)
        self.assertNotIn("metric-not-in-cited-evidence", codes)
        cells = [i for i in led["obligations"]["items"] if i["kind"] == "cell"]
        self.assertTrue(cells and all(i["status"] == "ready" for i in cells), cells)

    def test_archive_members_are_searchable_and_readable(self):
        out = analyze.search(self.con, "Spatial Lite parameters")
        paths = [r["path"] for r in out["results"]["items"]]
        self.assertIn("bundle.tgz::docs/COMPARISON.md", paths)
        read = tools.t_read(str(self.ws), "proj", "bundle.tgz::docs/COMPARISON.md", start=3, lines=1)
        self.assertIn("2.817M", read["lines"][0]["text"])
        self.assertTrue(read["origin"].startswith("probe snapshot"))

    def test_locator_resolution(self):
        self.assertEqual(ledger.resolve_locator('{"a": {"b": [1, 2]}}', "$.a.b[1]"), ("resolved", 2))
        self.assertEqual(ledger.resolve_locator('{"a": 1}', "$.a.c")[0], "unresolved")
        self.assertEqual(ledger.resolve_locator("x,y\n1,2\n", "row:2,col:y"), ("resolved", "2"))
        self.assertEqual(ledger.resolve_locator("a\nb\nc\n", "lines 2-3"), ("resolved", "b\nc"))
        self.assertEqual(ledger.resolve_locator("a\n", "lines 4-5")[0], "unresolved")

    def test_mcp_roundtrip(self):
        init = mcp.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}}, str(self.ws))
        self.assertEqual(init["result"]["serverInfo"]["name"], "labweft-trace")
        listed = mcp.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, str(self.ws))
        names = {t["name"] for t in listed["result"]["tools"]}
        self.assertIn("trace_experiments", names)
        call = mcp.handle({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                           "params": {"name": "trace_xrefs", "arguments": {"source": "proj", "token": "base.yaml"}}}, str(self.ws))
        self.assertFalse(call["result"]["isError"])
        bad = mcp.handle({"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                          "params": {"name": "trace_read", "arguments": {"source": "proj", "path": "../etc/passwd"}}}, str(self.ws))
        self.assertTrue(bad["result"]["isError"])


if __name__ == "__main__":
    unittest.main()
