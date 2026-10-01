"""Explicit, opt-in research execution with durable boundaries and evidence import.

The scanner and HTTP server never call this module. Local files are not a sandbox;
task evaluators and candidate code must run in an appropriately isolated environment.
"""
from __future__ import annotations

from contextlib import contextmanager
import copy
import hashlib
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import uuid

from .backends.shinka import REVISION, ShinkaBackend
from .scan import node, sensitive_name
from .store import (Store, HarnessError, Conflict, atomic_write, canonical, digest,
                    json_write, local_lock, now, read_json, stable_id)

ID = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}\Z")
MAX_INPUT_BYTES = 5 * 1024 * 1024


@contextmanager
def worker_lease(path: Path):
    """OS-owned single-worker lock, released by process death on Windows/POSIX."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as stream:
        if path.stat().st_size == 0:
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise Conflict("A worker already holds this research activity") from exc
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def validate_spec(spec: dict) -> dict:
    if not isinstance(spec, dict):
        raise HarnessError("Research specification must be an object")
    required = {"id", "question", "task_dir", "files", "models", "max_generations",
                "evaluation_timeout_seconds", "evaluation_protocol"}
    optional = {"instructions", "batch_size", "max_evaluation_jobs", "num_islands", "max_api_cost_usd"}
    if required - spec.keys() or spec.keys() - required - optional:
        raise HarnessError(f"Invalid specification fields; missing={sorted(required - spec.keys())}, unknown={sorted(spec.keys() - required - optional)}")
    out = {"instructions": "Only evolve initial.py. Do not modify the evaluator or its inputs.",
           "batch_size": 2, "max_evaluation_jobs": 1, "num_islands": 2, "max_api_cost_usd": None, **spec}
    if not isinstance(out["id"], str) or not ID.fullmatch(out["id"]):
        raise HarnessError("Activity id must contain only letters, digits, underscores or hyphens")
    for key in ("question", "task_dir", "instructions", "evaluation_protocol"):
        if not isinstance(out[key], str) or not out[key].strip():
            raise HarnessError(f"{key} must be nonempty text")
    for key in ("max_generations", "batch_size", "max_evaluation_jobs", "num_islands", "evaluation_timeout_seconds"):
        if type(out[key]) is not int or out[key] < 1:
            raise HarnessError(f"{key} must be a positive integer")
    if out["max_generations"] < 2:
        raise HarnessError("At least two generations are required: baseline zero plus one proposal")
    cap = out["max_api_cost_usd"]
    if cap is not None and (type(cap) not in (int, float) or not 0 < cap < float("inf")):
        raise HarnessError("max_api_cost_usd must be positive or null (unknown/unbounded monetary estimate)")
    if not isinstance(out["models"], list) or not out["models"] or any(not isinstance(x, str) or not x.strip() for x in out["models"]):
        raise HarnessError("Explicit model identifiers are required; no default provider is selected")
    paths = out["files"]
    if not isinstance(paths, list) or any(not isinstance(x, str) for x in paths) or len(set(paths)) != len(paths):
        raise HarnessError("files must be a unique list of relative paths")
    if not {"initial.py", "evaluate.py"} <= set(paths):
        raise HarnessError("files must include initial.py and evaluate.py")
    for name in paths:
        path = PurePosixPath(name)
        if (not name or "\\" in name or ":" in name or path.is_absolute() or
                path.as_posix() != name or any(p in (".", "..") or p.startswith(".") or sensitive_name(p) for p in path.parts)):
            raise HarnessError(f"Unsafe or sensitive task file: {name}")
    canonical(out)
    return out


class Campaign:
    def __init__(self, workspace: str | Path, activity_id: str):
        if not isinstance(activity_id, str) or not ID.fullmatch(activity_id):
            raise HarnessError("Invalid activity id")
        self.store = Store(workspace)
        self.id = activity_id
        self.directory = self.store.root / "autoresearch" / activity_id
        if self.directory.is_symlink() or self.directory.parent.is_symlink():
            raise HarnessError("Research activity cannot be a symlink")

    @property
    def control(self) -> Path:
        return self.directory / "control.lock"

    def load(self) -> tuple[dict, dict]:
        if not (self.directory / "state.json").exists():
            raise HarnessError("Unknown or incompletely prepared research activity")
        contract = read_json(self.directory / "contract.json")
        state = read_json(self.directory / "state.json")
        if digest(contract) != state["contract_sha256"]:
            raise HarnessError("Frozen research contract changed")
        if contract["project_id"] != self.store.load()["project"]["id"]:
            raise HarnessError("Activity belongs to a different research workspace")
        return contract, state

    def verify_inputs(self, contract: dict) -> None:
        task = self.directory / "task"
        for name, expected in contract["input_sha256"].items():
            path = task / name
            if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(task.resolve()):
                raise HarnessError(f"Frozen task file missing or redirected: {name}")
            if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                raise HarnessError(f"Frozen task file changed: {name}")

    def save(self, state: dict, phase: str, **values) -> dict:
        state = {**state, **values, "phase": phase, "updated_at": now()}
        json_write(self.directory / "state.json", state)
        return state

    def status(self) -> dict:
        contract, state = self.load()
        active = False
        try:
            with worker_lease(self.directory / "worker.lock"):
                pass
        except Conflict:
            active = True
        effective = state["phase"]
        if effective == "running" and not active:
            effective = "needs_review"
        return {**state, "effective_phase": effective, "worker_lock_held": active,
                "activity_id": self.id, "backend": "shinka", "question": contract["question"],
                "max_generations": contract["max_generations"],
                "stop_behavior": "Drain the current bounded batch; do not kill evaluators",
                "qualification": "Backend reports only; independent scientific qualification required"}

    def start(self, *, execute: bool = False, resume: bool = False) -> dict:
        contract, _ = self.load()
        self.verify_inputs(contract)
        if not execute:
            return {"dry_run": True, "contract": contract,
                    "next": "Pass --execute only within your authorized compute/model scope. No task code has run."}
        installed = ShinkaBackend().preflight()
        with local_lock(self.control):
            contract, state = self.load()
            permitted = "paused" if resume else "ready"
            if state["phase"] != permitted:
                raise HarnessError(f"Cannot {'resume' if resume else 'start'} from {state['phase']}; never retry an ambiguous launch")
            with worker_lease(self.directory / "worker.lock"):
                pass
            self.verify_inputs(contract)
            token = uuid.uuid4().hex
            state = self.save(state, "starting", launch_token=token, stop_requested=False,
                              installation=installed, resume_count=state.get("resume_count", 0) + int(resume))
            command = [sys.executable, "-m", "research_harness.research_worker", str(self.store.workspace), self.id, token]
            try:
                with (self.directory / "worker.log").open("ab") as log:
                    child = subprocess.Popen(command, cwd=Path(__file__).resolve().parent.parent,
                                             stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                             creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                                             start_new_session=os.name != "nt")
                self.save(state, "starting", worker_pid=child.pid)
            except OSError as exc:
                self.save(state, "needs_review", error=f"Launch outcome requires review: {exc}")
                raise
        return self.status()

    def stop(self) -> dict:
        with local_lock(self.control):
            _, state = self.load()
            if state["phase"] in {"starting", "running"}:
                self.save(state, state["phase"], stop_requested=True)
            elif state["phase"] == "ready":
                self.save(state, "paused", stop_requested=True)
        return self.status()

    def run(self, token: str, backend=None) -> None:
        """Worker entry; a crash in an unfinished batch is deliberately not resumable."""
        backend = backend or ShinkaBackend()
        with worker_lease(self.directory / "worker.lock"):
            try:
                while True:
                    with local_lock(self.control):
                        contract, state = self.load()
                        if state.get("launch_token") != token or state["phase"] not in {"starting", "running"}:
                            raise HarnessError("Stale or duplicate worker launch")
                        self.verify_inputs(contract)
                        if state["stop_requested"]:
                            self.save(state, "paused", active_target=None)
                            break
                        completed = state["completed_generations"]
                        if completed >= contract["max_generations"]:
                            self.save(state, "completed", active_target=None)
                            break
                        target = min(contract["max_generations"], max(2, completed + contract["batch_size"]))
                        # Persist intent before any upstream code or model call.
                        self.save(state, "running", active_target=target, worker_pid=os.getpid())
                    backend.run_batch(contract, self.directory, target)
                    self.verify_inputs(contract)
                    records = backend.collect(self.directory)
                    generations = {p["generation"] for p in records}
                    with local_lock(self.control):
                        _, state = self.load()
                        if generations != set(range(target)):
                            self.save(state, "needs_review", error="Native batch returned without exactly the expected generation coverage; no automatic retry")
                            break
                        self.save(state, "running", completed_generations=target, active_target=None)
                    self.collect(records=records)
                self.collect()
            except BaseException as exc:
                with local_lock(self.control):
                    if (self.directory / "state.json").exists():
                        state = read_json(self.directory / "state.json")
                        if state.get("launch_token") == token:
                            self.save(state, "needs_review", error=f"{type(exc).__name__}: {exc}")
                raise

    def collect(self, *, records: list[dict] | None = None) -> dict:
        # Serialize status projection with lifecycle updates, including concurrent
        # manual collect and worker collect. Never overwrite a newer status snapshot.
        with local_lock(self.control):
            return self._collect(records=records)

    def _collect(self, *, records: list[dict] | None = None) -> dict:
        contract, runtime = self.load()
        self.verify_inputs(contract)
        records = ShinkaBackend().collect(self.directory) if records is None else records
        if any(p["generation"] >= contract["max_generations"] for p in records):
            raise HarnessError("Native result exceeds the frozen generation limit")
        by_id = {p["id"]: p for p in records}
        if len(by_id) != len(records):
            raise HarnessError("Duplicate native program identity")
        scope = {"evaluation_protocol": contract["evaluation_protocol"], "contract_sha256": digest(contract)}
        question_id = stable_id("research", self.id)
        # Optimistic store revision retry is only for this deterministic evidence projection.
        for attempt in range(3):
            state = self.store.load()
            files, nodes, edges = [], [], []

            def snapshot(key: str, value: dict) -> list[dict]:
                raw = (canonical(value) + "\n").encode()
                sha = self.store.blob(raw)
                fid = stable_id("research-file", self.id, key)
                files.append({"id": fid, "source": "autoresearch", "path": f"{self.id}/{key}.json",
                              "size": len(raw), "sha256": sha, "snapshot": "text_snapshot", "missing": False})
                return [{"file_id": fid, "sha256": sha, "locator": "full backend report; not independent qualification"}]

            nodes.append(node(question_id, "question", contract["question"], state["project"]["id"],
                              attrs={"role": "auto_research", "backend": "shinka", "activity_id": self.id,
                                     "scope": scope, "runtime": runtime},
                              evidence=snapshot("contract-and-status", {"contract": contract, "runtime": runtime})))
            for program in records:
                native_id = program["id"]
                cid = stable_id("shinka-cell", self.id, native_id)
                rid = stable_id("shinka-run", self.id, native_id)
                eid = stable_id("shinka-evaluation", self.id, native_id)
                old = state["nodes"].get(cid)
                if old and old["attrs"]["code_sha256"] != program["code_sha256"]:
                    raise HarnessError("Native candidate identity reused for different code")
                ev = snapshot(native_id, {"backend": "shinka", "scope": scope, "program": program})
                attrs = {"backend_program_id": native_id, "generation": program["generation"],
                         "code_sha256": program["code_sha256"], "island": program["island_idx"], "scope": scope}
                nodes.append(node(cid, "cell", f"Shinka generation {program['generation']} · {native_id[:8]}",
                                  question_id, attrs=attrs, evidence=ev))
                # Never feed search scores into the existing training-seed statistical comparator.
                report = {"backend_correct": program["correct"], "search_score": program["combined_score"],
                          "public_metrics": program["public_metrics"], "private_metrics": program["private_metrics"],
                          "independent_verification": "not_performed", "data_release_eligible": False,
                          "cost": {"billed_amount": None, "raw_backend_metadata": program["metadata"]}}
                nodes.append(node(rid, "run", "Backend evaluation report", cid, attrs={**attrs, **report}, evidence=ev))
                nodes.append(node(eid, "evaluation", "Unqualified Shinka result", rid,
                                  status="provisional", attrs={**scope, **report}, evidence=ev))
                parent = program["parent_id"]
                if parent in by_id and parent != native_id:
                    edges.append({"id": stable_id("shinka-lineage", self.id, native_id, parent),
                                  "source": cid, "target": stable_id("shinka-cell", self.id, parent),
                                  "relation": "derived_from"})
                elif parent:
                    nodes[-3]["attrs"]["unresolved_parent_id"] = parent
            try:
                result = self.store.commit({"base_revision": state["revision"], "reason": "Collect Shinka backend reports without scientific promotion",
                                            "files": files, "nodes": nodes, "edges": edges}, actor="backend:shinka", scanner=True)
                return {**result, "activity_id": self.id, "reported_candidates": len(records),
                        "independently_qualified_candidates": 0}
            except Conflict:
                if attempt == 2:
                    raise
        raise AssertionError("Unreachable")


def prepare(workspace: str | Path, spec: dict, *, spec_directory: Path) -> dict:
    spec = validate_spec(copy.deepcopy(spec))
    campaign = Campaign(workspace, spec["id"])
    project = campaign.store.load()["project"]
    source = (spec_directory / spec["task_dir"]).resolve()
    contents = {}
    for name in spec["files"]:
        path = source / name
        if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(source):
            raise HarnessError(f"Task file missing or outside task directory: {name}")
        if path.stat().st_size > MAX_INPUT_BYTES:
            raise HarnessError("Task snapshot is for small source/config files; retain large data externally")
        contents[name] = path.read_bytes()
        if sum(map(len, contents.values())) > MAX_INPUT_BYTES:
            raise HarnessError("Task inputs exceed the 5 MiB snapshot limit")
    contract = {**spec, "task_dir": "task", "schema_version": 1, "backend": "shinka",
                "backend_revision": REVISION, "project_id": project["id"],
                "input_sha256": {name: hashlib.sha256(raw).hexdigest() for name, raw in contents.items()}}
    with local_lock(campaign.store.root / "autoresearch-prepare.lock"):
        if campaign.directory.exists():
            previous, _ = campaign.load()
            if previous != contract:
                raise HarnessError("Activity id already exists with a different frozen contract; use a new id")
            campaign.verify_inputs(previous)
        else:
            campaign.directory.mkdir(parents=True)
            atomic_write(campaign.directory.parent / ".gitignore", "*\n!.gitignore\n")
            for name, raw in contents.items():
                atomic_write(campaign.directory / "task" / name, raw)
            json_write(campaign.directory / "contract.json", contract)
            campaign.save({"contract_sha256": digest(contract), "completed_generations": 0,
                           "stop_requested": False, "created_at": now()}, "ready")
    campaign.collect(records=[])
    return campaign.status()


def add_cli(subparsers) -> None:
    parser = subparsers.add_parser("research", help="Opt-in Shinka research; ordinary scan/serve remain read-only")
    actions = parser.add_subparsers(dest="research_action", required=True)
    p = actions.add_parser("prepare", help="Freeze small task inputs without executing them or contacting models")
    p.add_argument("workspace")
    p.add_argument("spec", type=Path)
    for action in ("start", "resume", "status", "stop", "collect"):
        p = actions.add_parser(action)
        p.add_argument("workspace")
        p.add_argument("activity_id")
        if action in {"start", "resume"}:
            p.add_argument("--execute", action="store_true", help="Launch authorized code execution and model calls; default only previews")


def dispatch(args) -> dict:
    if args.research_action == "prepare":
        return prepare(args.workspace, read_json(args.spec), spec_directory=args.spec.resolve().parent)
    campaign = Campaign(args.workspace, args.activity_id)
    if args.research_action in {"start", "resume"}:
        return campaign.start(execute=args.execute, resume=args.research_action == "resume")
    return getattr(campaign, args.research_action)()
