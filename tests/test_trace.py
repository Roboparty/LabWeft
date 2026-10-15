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


class VerifyTests(unittest.TestCase):
    """find|wc -l, sha256sum -c, diff -r against an archive snapshot, git object presence."""

    def test_count_checksum_compare_git(self):
        import hashlib
        import io as _io
        import shutil
        import subprocess
        import tarfile as _tarfile
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "p"
            live = src / "study"
            for i in range(3):
                (live / "collected" / f"cell{i}").mkdir(parents=True)
                (live / "collected" / f"cell{i}" / "cell_result.json").write_text(json.dumps({"success": i}))
            (live / "summary").mkdir()
            (live / "summary" / "FINAL.md").write_text("# Final\n\nold\n")
            (live / "empty" / "a" / "b").mkdir(parents=True)
            with _tarfile.open(src / "study-snapshot.tar.gz", "w:gz") as tf:
                for p in sorted(live.rglob("*")):
                    if p.is_file():
                        tf.add(p, arcname=p.relative_to(live).as_posix())
            (live / "summary" / "FINAL.md").write_text("# Final\n\nnew section added later\n")
            (live / "summary" / "SRS.json").write_text("{}")
            digest = hashlib.sha256((src / "study-snapshot.tar.gz").read_bytes()).hexdigest()
            (src / "study-snapshot.tar.gz.sha256").write_text(f"{digest}  study-snapshot.tar.gz\n")
            (src / "queue.jsonl").write_text('{"id": "p1/a"}\n{"id": "p2/b"}\n{"id": "p1/c"}\n')
            ws = Path(tmp) / "ws"
            tools.t_collect(str(ws), "p", str(src))

            c = tools.t_count(str(ws), "p", path="study", name_glob="cell_result.json")
            self.assertEqual(c["files"], 3)
            (live / "collected" / "__pycache__").mkdir()
            (live / "collected" / "__pycache__" / "x.pyc").write_bytes(b"\0" * 10)
            tools.t_collect(str(ws), "p", str(src))
            c2 = tools.t_count(str(ws), "p", path="study/collected")
            self.assertEqual((c2["files"], c2["files_including_skipped_folders"]), (3, 4))
            d = tools.t_count(str(ws), "p", path="study/empty", what="dirs")
            self.assertEqual(d["dirs"]["total_recursive"], 2)
            a = tools.t_count(str(ws), "p", path="study-snapshot.tar.gz::summary")
            self.assertEqual(a["files"], 1)

            ck = tools.t_checksum(str(ws), "p", "study-snapshot.tar.gz")
            self.assertEqual(ck["verdict"], "match")
            (src / "study-snapshot.tar.gz.sha256").write_text("0" * 64 + "  study-snapshot.tar.gz\n")
            tools.t_collect(str(ws), "p", str(src))
            self.assertEqual(tools.t_checksum(str(ws), "p", "study-snapshot.tar.gz")["verdict"], "mismatch")

            (src / "study" / "summary" / "SHA256SUMS").write_text(
                f"{hashlib.sha256((live / 'summary' / 'SRS.json').read_bytes()).hexdigest()}  SRS.json\n" + "0" * 64 + "  FINAL.md\n" + "1" * 64 + "  GONE.md\n")
            tools.t_collect(str(ws), "p", str(src))
            vl = tools.t_checksum(str(ws), "p", "study/summary/SHA256SUMS")
            self.assertEqual((vl["ok"], vl["mismatch_total"], vl["missing_files"]), (1, 1, ["GONE.md"]))

            cmp_ = tools.t_compare(str(ws), "p", "study", "study-snapshot.tar.gz::")
            self.assertEqual(cmp_["only_in_a"], ["summary/SHA256SUMS", "summary/SRS.json"])
            self.assertEqual(cmp_["content_differs"] + cmp_["size_differs_unhashed"], ["summary/FINAL.md"])

            g = tools.t_grep(str(ws), "p", '"p1/', path="queue.jsonl")
            self.assertEqual(g["matching_lines_total"], 2)

            if shutil.which("git"):
                repo = src / "repo"
                repo.mkdir()
                run = lambda *args: subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True)
                run("init", "-q")
                (repo / "x.txt").write_text("x")
                run("add", "x.txt")
                run("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "first")
                head = run("rev-parse", "HEAD").stdout.strip()
                out = tools.t_git(str(ws), "p", repo="repo", ref=[head[:7], "deadbee"])
                self.assertTrue(out["refs"][0]["exists_in_objects"])
                self.assertFalse(out["refs"][1]["exists_in_objects"])


class ReconcileRoundingTests(unittest.TestCase):
    def test_sd_of_rounded_seed_means_is_derived(self):
        # per-eval rows: seed means 88.00/88.67/88.00 -> exact sample SD 0.3849 (prints 0.38); authors printed 0.39
        rows = ["task,mode,train_seed,eval_seed,sr_pct"]
        for seed, vals in ((3072, (90, 91, 83)), (3073, (90, 89, 87)), (3074, (91, 88, 85))):
            for ev, v in zip((0, 1, 42), vals):
                rows.append(f"pusht,direct,{seed},{ev},{v}")
                rows.append(f"pusht,cem,{seed},{ev},{v - 3}")
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "p"
            (src / "analysis").mkdir(parents=True)
            (src / "analysis" / "PER_EVAL.csv").write_text("\n".join(rows) + "\n")
            (src / "analysis" / "REPORT.md").write_text("# Result\n\n| method | SR |\n|---|---|\n| Direct | 88.22 +/- 0.39 |\n", encoding="utf-8")
            ws = Path(tmp) / "ws"
            tools.t_collect(str(ws), "p", str(src))
            out = tools.t_reconcile(str(ws), "p", number="88.22")
            item = out["occurrences"]["items"][0]
            self.assertEqual(item["state"], "derived")
            self.assertEqual(item["sources"][0]["sd"], "sample")
            self.assertIn("sd_rounding", item["sources"][0])


class AuditCrossDocTests(unittest.TestCase):
    def test_disagreeing_number_flagged_citation_and_short_points_table(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "p"
            res = src / "study" / "results"
            res.mkdir(parents=True)
            (res / "summary.csv").write_text("method,mean\ncem,26.333\ndirect,9.222\n")
            (res / "SWEEP.md").write_text("# Sweep\n\n| m | SR |\n|---|---|\n| cem | 26.33 +/- 1.20 |\n| direct | 9.22 +/- 2.91 |\n", encoding="utf-8")
            (res / "ANALYSIS.md").write_text("# Analysis\n\n| m | SR |\n|---|---|\n| cem | 24.33 +/- 1.20 |\n| direct | 9.22 +/- 2.91 |\n", encoding="utf-8")
            bad = src / "study" / "other_e5.incomplete_do_not_use"
            bad.mkdir()
            (bad / "RESULTS.md").write_text("# E5\n\n| v | mean | sd |\n|---|---|---|\n| a | 57.22 | 3.86 |\n| b | 60.56 | 1.84 |\n", encoding="utf-8")
            (src / "study" / "PAPER_TEXT.md").write_text("# Paper\n\nShared encoder: a `57.22 +/- 3.86`, b `60.56 +/- 1.84`.\n", encoding="utf-8")
            summ = src / "study" / "summary"
            summ.mkdir()
            (summ / "ALIGN_X.json").write_text(json.dumps({"r2": {"pooled": {"n": 6, "r": 0.9}, "demeaned": {"n": 6, "r": 0.8}}}))
            (summ / "align_x_points.csv").write_text("train_seed,epoch,sr\n0,1,80\n0,2,82\n42,1,79\n42,2,81\n")
            (summ / "OTHER_POINTS.csv").write_text("train_seed,epoch,srs\n0,1,1\n0,2,2\n42,1,3\n42,2,4\n7,1,5\n7,2,6\n")
            ws = Path(tmp) / "ws"
            tools.t_collect(str(ws), "p", str(src))
            out = tools.t_audit(str(ws), "p")
            kinds = {f["kind"]: f for f in out["findings"]["items"]}
            self.assertIn("report-number-disagrees", kinds)
            self.assertIn("24.33", kinds["report-number-disagrees"]["evidence"])
            self.assertIn("cites-flagged-study", kinds)
            self.assertEqual(kinds["cites-flagged-study"]["files"][0], "study/PAPER_TEXT.md")
            self.assertIn("table-row-count-mismatch", kinds)
            self.assertIn("'7'", kinds["table-row-count-mismatch"]["evidence"])


class SymlinkTests(unittest.TestCase):
    def test_ls_and_count_follow_symlinked_folders(self):
        import os
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "p"
            real = src / "experiments" / "phase9"
            real.mkdir(parents=True)
            (real / "result.json").write_text(json.dumps({"sr": 0.9}))
            (src / "phases").mkdir()
            try:
                os.symlink("../experiments/phase9", src / "phases" / "phase9", target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("symlinks not permitted on this machine")
            ws = Path(tmp) / "ws"
            tools.t_collect(str(ws), "p", str(src))
            out = tools.t_ls(str(ws), "p", path="phases/phase9")
            self.assertEqual(out["status"], "found")
            self.assertTrue(out["followed_symlinks"])
            self.assertEqual(tools.t_count(str(ws), "p", path="phases/phase9")["files"], 1)


class AuditRound10Tests(unittest.TestCase):
    def test_duplicate_row_declared_hash_and_version_drift(self):
        import hashlib
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "p"
            rep = src / "study" / "report"
            rep.mkdir(parents=True)
            (rep / "REPORT.md").write_text("# R\n\n| arm | a | b | c |\n|---|---|---|---|\n| VIS (1.5) | 71.33 ± 8.19 | 21.11 ± 2.83 | 82.78 |\n"
                                           "| VIS (4.5) | 71.33 ± 8.19 | 21.11 ± 2.83 | 82.78 |\n| QQ | 37.67 ± 3.4 | 18.89 ± 5.9 | 58.11 |\n", encoding="utf-8")
            res = src / "study" / "results"
            res.mkdir()
            (res / "COMPLETION.json").write_text('{"done": 504, "failed": 0}\n')
            (res / "AUDIT.md").write_text("# Audit\n\n- COMPLETION.json sha256 " + "a" * 64 + "\n", encoding="utf-8")
            for i in range(6):
                d = res / "eval" / f"run_s{i}"
                d.mkdir(parents=True)
                (d / "seed_0.json").write_text(json.dumps({"benchmark_version": "v0.7" if i == 3 else "v0.8", "success": 70 + i}))
            ws = Path(tmp) / "ws"
            tools.t_collect(str(ws), "p", str(src))
            kinds = {f["kind"] for f in tools.t_audit(str(ws), "p")["findings"]["items"]}
            self.assertIn("duplicated-table-row", kinds)
            self.assertIn("declared-checksum-mismatch", kinds)
            self.assertIn("result-setting-outlier", kinds)


class TableArithmeticTests(unittest.TestCase):
    def test_macro_and_delta_columns_are_recomputed(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "p"
            src.mkdir()
            (src / "RESULTS.md").write_text(
                "# R\n\n| arm | PushT | Cube | Reacher | Macro |\n|---|---|---|---|---|\n"
                "| a | 80.00 | 90.00 | 70.00 | 80.00 |\n| b | 60.00 | 90.00 | 60.00 | 70.00 |\n"
                "| c | 50.00 | 70.00 | 60.00 | 60.00 |\n| d | 40.00 | 50.00 | 60.00 | 53.00 |\n\n"
                "| task | Base | Ours | Delta |\n|---|---|---|---|\n| x | 80.00 | 85.00 | +5.00 |\n| y | 70.00 | 72.00 | +2.00 |\n"
                "| z | 60.00 | 66.00 | +6.00 |\n| w | 50.00 | 51.00 | +2.00 |\n", encoding="utf-8")
            ws = Path(tmp) / "ws"
            tools.t_collect(str(ws), "p", str(src))
            ev = [f["evidence"] for f in tools.t_audit(str(ws), "p")["findings"]["items"] if f["kind"] == "table-arithmetic"]
            self.assertTrue(any("row 'd'" in e and "Macro" in e for e in ev))
            self.assertTrue(any("row 'w'" in e and "Delta" in e for e in ev))
