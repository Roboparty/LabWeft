import json
import statistics
import tempfile
import unittest
from pathlib import Path

from research_harness.store import Store
from research_harness.trace import analyze, index, ledger, mcp, navigate, probe, tools
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
    (root / "configs" / "base.yaml").write_text("optim:\n  lr: 0.0003\n  batch_size: 256\nmodel: intact\n")
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

    def test_round6_reconcile_names_replicates_and_flags_mixed_sd(self):
        out = analyze.reconcile(self.con, path="REPORT.md", limit=50)
        self.assertIn("mixed_sd_conventions", out["report"])
        pm = [n for n in out["numbers"]["items"] if n["kind"] == "mean±sd"]
        unit = pm[0]["sources"][0].get("replicate_unit") or {}
        self.assertEqual(sorted(map(str, unit.get("pooled", {}).get("seed", []))), ["7", "8", "9"])
        self.assertIn("rh", pm[0]["sources"][0].get("levels", {}))

    def test_round6_local_grep_and_pattern_hits(self):
        out = tools.t_grep(str(self.ws), "proj", "Main result|Sweep report")
        self.assertEqual(out["mode"], "regex")
        self.assertTrue(any(h["path"] == "REPORT.md" for h in out["hits"]))
        read = tools.t_read(str(self.ws), "proj", "REPORT.md", pattern="unrelated number")
        hits = [l for l in read["lines"] if l.get("hit")]
        self.assertEqual(len(hits), 1)
        self.assertGreater(len(read["lines"]), 1)  # context lines are kept but not marked

    def test_round6_validity_offers_unflagged_alternative(self):
        import shutil
        base = self.src / "supplement"
        for name in ("mechanism_goal_7local_e5.incomplete_do_not_use", "mechanism_goal_7local_rawgoal"):
            (base / name).mkdir(parents=True)
            (base / name / "README.md").write_text("# study\n", encoding="utf-8")
            (base / name / "result.json").write_text('{"success_rate": 0.5}', encoding="utf-8")
        ws2 = self.ws.parent / "ws2"
        tools.t_collect(str(ws2), "proj", str(self.src))
        con = index.connect(ws2, "proj")
        try:
            v = navigate.validity(con)
        finally:
            con.close()
        flagged = [a for a in v["flagged_areas"]["items"] if a["area"].endswith("incomplete_do_not_use")]
        self.assertTrue(flagged)
        alts = [a["study"] for a in flagged[0].get("unflagged_alternatives", [])]
        self.assertIn("mechanism_goal_7local_rawgoal", alts)

    def test_round7_audit_finds_planted_inconsistencies(self):
        import shutil
        base = self.src / "study"
        for seed, lr in ((1, "5e-4"), (2, "5e-4"), (3, "1e-3")):
            run = base / f"train{seed}"
            run.mkdir(parents=True)
            steps = "\n".join(f"[Epoch 0/1] step {i}/500" for i in range(100, 501 if seed != 2 else 301, 100))
            done = "\nModel saved to weights_epoch_1.pt" if seed != 2 else ""
            (run / "train.log").write_text(f"python train.py optimizer.lr={lr} seed={seed}\n{steps}{done}\n", encoding="utf-8")
            (run / "result.json").write_text(json.dumps({"seed": seed, "successes": 80 + seed, "episode_successes": [1, 0] * 60,
                                                         "note": "x" * 200}), encoding="utf-8")
        shutil.copy(base / "train1" / "result.json", base / "train3" / "result.json")  # a copied replicate
        (base / "summary.json").write_text(json.dumps({"cells": [{"macro": [95.0], "tasks": {"a": 90.0, "b": 92.0}}]}), encoding="utf-8")
        (base / "table.csv").write_text("task,epoch,sr\na,1,80.5\na,2,85.1\na,3,0.871\na,4,88.2\na,5,89.0\n", encoding="utf-8")
        ws2 = self.ws.parent / "ws-audit"
        tools.t_collect(str(ws2), "proj", str(self.src))
        out = tools.t_audit(str(ws2), "proj", scope="study")
        kinds = out["by_kind"]
        self.assertEqual(kinds.get("identical-replicate-content"), 1, out)
        self.assertEqual(kinds.get("truncated-run"), 1, out)
        self.assertEqual(kinds.get("setting-outlier"), 1, out)
        self.assertEqual(kinds.get("aggregate-mismatch"), 1, out)
        self.assertEqual(kinds.get("scale-outlier"), 1, out)
        trunc = next(f for f in out["findings"]["items"] if f["kind"] == "truncated-run")
        self.assertTrue(trunc["files"][0].endswith("train2/train.log"))

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


class NavigateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        src = base / "proj"
        study = src / "supplement" / "mech_multitask_e5.incomplete_do_not_use" / "results"
        study.mkdir(parents=True)
        (study / "AUDIT.json").write_text(json.dumps({"status": "complete", "control_cells": 36}))
        (src / "supplement" / "mech_multitask_e5.incomplete_do_not_use" / "README_CN.md").write_text("# Multitask mechanism\n", encoding="utf-8")
        runs = src / "study" / "collected" / "h204" / "independent_2x" / "train3072"
        runs.mkdir(parents=True)
        (runs / "result.json").write_text(json.dumps({"eval_episodes": [1, 2, 3, 4], "episode_successes": [1, 0, 1, 1]}))
        other = src / "study" / "collected" / "h201" / "shared" / "train3072"
        other.mkdir(parents=True)
        (other / "result.json").write_text(json.dumps({"eval_episodes": [4, 3, 2, 1], "episode_successes": [0, 1, 1, 0]}))
        (src / "study" / "run_fixed.py").write_text("VARIANTS = {'independent_2x': 2, 'shared': 1}\nif __name__ == '__main__':\n    pass\n")
        (src / "study" / "aggregate_results.py").write_text("NAMES = ['independent_2x', 'shared']\nif __name__ == '__main__':\n    pass\n")
        self.ws = base / "ws"
        tools.t_collect(str(self.ws), "p", str(src))

    def tearDown(self):
        self.tmp.cleanup()

    def test_ls_and_brief(self):
        out = tools.t_ls(str(self.ws), "p", "supplement")
        entry = out["entries"]["items"][0]
        self.assertTrue(entry["dir"].endswith("incomplete_do_not_use/") and entry["flag"])
        brief = tools.t_brief(str(self.ws), "p")
        self.assertTrue(any(f["area"].endswith("incomplete_do_not_use") for f in brief["flagged_studies"]))

    def test_validity_flags_contradiction_with_declared_status(self):
        out = tools.t_validity(str(self.ws), "p")
        area = out["flagged_areas"]["items"][0]
        kinds = {c["kind"] for c in area["contradictions"]}
        self.assertIn("flagged-but-declares-complete", kinds)
        self.assertIn("claims-more-results-than-indexed", kinds)

    def test_inferred_producer_and_host_hints(self):
        out = tools.t_provenance(str(self.ws), "p", "study/collected/h204/independent_2x/train3072/result.json")
        self.assertEqual(out["inferred_producers"][0]["file"], "study/run_fixed.py")
        self.assertEqual([h["token"] for h in out["host_hints"]], ["h204"])
        d = tools.t_provenance(str(self.ws), "p", "study/collected")
        self.assertEqual(d["kind"], "directory")
        self.assertEqual(d["host_hints_below"], ["h201", "h204"])

    def test_pair_aligns_by_episode_id(self):
        out = tools.t_pair(str(self.ws), "p", "study/collected/h204/independent_2x/train3072/result.json",
                           "study/collected/h201/shared/train3072/result.json")
        self.assertEqual(out["aligned"], "by eval_episodes")
        # ep1: 1/0, ep2: 0/1, ep3: 1/1, ep4: 1/0
        self.assertEqual((out["both"], out["only_a"], out["only_b"], out["neither"]), (1, 2, 1, 0))

    def test_read_json_path(self):
        out = tools.t_read(str(self.ws), "p", "supplement/mech_multitask_e5.incomplete_do_not_use/results/AUDIT.json", json_path="status")
        self.assertEqual(out["value"], "complete")
        miss = tools.t_read(str(self.ws), "p", "supplement/mech_multitask_e5.incomplete_do_not_use/results/AUDIT.json", json_path="$.nope")
        self.assertEqual(miss["status"], "not_found")
        self.assertIn("status", miss["top_level_keys"])


class FindTests(unittest.TestCase):
    def test_find_phrase_windows_in_one_call(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "p"
            (src / "docs").mkdir(parents=True)
            (src / "docs" / "README_CN.md").write_text("# Study\n\nOld Table IV is superseded.\nNew table: 87.56 +/- 0.38\n", encoding="utf-8")
            (src / "docs" / "COPY.md").write_text("# Study\n\nOld Table IV is superseded.\nNew table: 87.56 +/- 0.38\n", encoding="utf-8")
            ws = Path(tmp) / "ws"
            tools.t_collect(str(ws), "p", str(src))
            out = tools.t_find(str(ws), "p", ["table iv", "87.56"], context=1)
            first, second = out["results"]
            self.assertEqual(first["match"], "phrase")
            self.assertEqual(len(first["hits"]), 1)  # identical copies collapse
            self.assertTrue(any("superseded" in line for line in first["hits"][0]["window"]))
            self.assertEqual(second["hits"][0]["line"], 4)


class BulkTests(unittest.TestCase):
    def test_bulk_binary_directory_is_summarized(self):
        from research_harness.trace import probe as P
        old = P.BULK_MIN_FILES
        P.BULK_MIN_FILES = 50
        try:
            with tempfile.TemporaryDirectory() as tmp:
                src = Path(tmp) / "p"
                imgs = src / "datasets" / "imgs"
                imgs.mkdir(parents=True)
                for i in range(60):
                    (imgs / f"{i:04d}.png").write_bytes(b"\x89PNG")
                (src / "README.md").write_text("# x\n")
                out = Path(tmp) / "o.jsonl"
                kinds = [k for k, *_ in P.walk(str(src), [], 0)]
                self.assertEqual(kinds.count("bulk"), 1)
                self.assertEqual(kinds.count("file"), 1)
        finally:
            P.BULK_MIN_FILES = old
